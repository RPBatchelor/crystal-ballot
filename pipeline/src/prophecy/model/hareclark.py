"""Seat simulation for Hare-Clark multi-member divisions (Tasmanian House of Assembly).

Each division elects several members by proportional representation: a candidate with a
quota (1 / (seats + 1) of the formal vote) is elected and their surplus passes on; when
no one has a quota the lowest is excluded and their ballots pass on. Nearly all ballots
stay within a party's ticket while it has candidates in the count, so the count is
simulated at the level of *units*: one per party, which can win several seats and keeps
its surplus, and one per independent candidate (one seat at most). A unit leaves the
count when excluded, or when it is an independent elected; its ballots then go to the
other units by bloc preference flows (with some exhausting).

For each simulation:

1. Statewide primaries: an aggregator draw plus systematic polling error (as for the
   single-member model).
2. Division shares of Labor, Liberal, Greens and Others swing on the logit scale from the
   previous result, with division noise, re-centred to the statewide figures.
3. Independents: each candidate on the ballot keeps their own previous vote in the
   division, with random decay (none for a sitting independent). A sitting member who
   has left their party takes part of their old personal vote (Hare-Clark counts every
   candidate, so it is observed directly) to their new party or as an independent. New
   independents start from a small share.
4. The Others bloc is split among minor parties on the ballot in proportion to their
   previous vote (or a small share for a new party).
5. The count above decides the seats.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import polars as pl
from scipy.special import expit, logit

from prophecy import DATA_DIR
from prophecy.jurisdictions import Election
from prophecy.model.preferences import BLOCS, IDX, draw_weights, estimate_weights
from prophecy.model.simulate import SimConfig, _recentre, statewide_shares
from prophecy.schema.parties import bloc

PROCESSED = DATA_DIR / "processed"
SWING_BLOCS = ["ALP", "COAL", "GRN", "OTH"]
NEW_PARTY_SHARE = 0.015  # a minor party with no previous vote in the division
NEW_IND_SHARE = 0.01  # an independent with no previous vote in the division
NEW_IND_SD = 0.8  # log-scale spread for a new independent (most poll little, a few well)
DEFECTOR_PERSONAL_VOTE = 0.5  # share of a sitting member's old personal vote they keep
EXHAUST = 0.1  # exhaustion weight (Luce scale, rows of the flow weights sum to 1)
SAME_BLOC = 0.15  # flow weight between two independents or two minor parties
DIVISION_SD = 0.35  # log scale: a new party's strength from division to division


@dataclass
class Unit:
    label: str  # party code, or the independent's name
    party: str  # party code ('IND' for independents)
    bloc: str
    weight: float  # within-bloc share basis: previous vote (fraction), or a default
    sitting_ind: bool = False
    new: bool = False  # no previous vote in this division
    new_party: bool = False  # a party not on the previous ballot anywhere


@dataclass
class DivisionInputs:
    division: str
    seats: int
    formal: float
    base: np.ndarray  # B, previous bloc shares (fractions), defectors' votes moved out
    units: list[Unit]
    notes: list[str] = field(default_factory=list)


def _swing_bloc(b: str) -> str:
    """One Nation is not polled in Tasmania: any minor party swings with Others."""
    return b if b in ("ALP", "COAL", "GRN", "IND") else "OTH"


def _units(division: str, ballot: pl.DataFrame, previous: pl.DataFrame,
           log: Callable[[str], None]) -> tuple[list[Unit], np.ndarray, list[str]]:
    """Units on the ballot, the previous bloc shares they swing from, and notes."""
    prev = previous.filter(pl.col("district") == division)
    formal = prev["votes"].sum()
    base = np.zeros(len(BLOCS))
    for b, v in prev.group_by("bloc").agg(pl.col("votes").sum()).iter_rows():
        base[IDX[_swing_bloc(b)]] += v / formal
    party_prev = dict(prev.filter(pl.col("party") != "IND").group_by("party")
                      .agg(pl.col("votes").sum() / formal).iter_rows())
    cand_prev = {r["candidate"]: r for r in prev.iter_rows(named=True)}
    notes: list[str] = []
    units: dict[str, Unit] = {}
    ind_moved = 0.0  # previous independents' votes not standing again
    for r in ballot.iter_rows(named=True):
        name, party, b = r["candidate"], r["party"], _swing_bloc(r["bloc"])
        before = cand_prev.get(name)
        if party != "IND":
            if party not in units:
                units[party] = Unit(party, party, b, party_prev.get(party, NEW_PARTY_SHARE),
                                    new=party not in party_prev)
        if before is not None and before["party"] != party and before["party"] != "IND" and r["sitting"]:
            # Sitting member standing for a different party, or as an independent.
            moved = DEFECTOR_PERSONAL_VOTE * before["votes"] / formal
            base[IDX[_swing_bloc(before["bloc"])]] -= moved
            base[IDX[b]] += moved
            notes.append(f"sitting member {name} elected for {before['party']}, standing for {party}")
            if party != "IND":
                units[party].weight += moved
                units[party].new = False
                continue
            units[name] = Unit(name, "IND", "IND", moved, sitting_ind=False)
            continue
        if party == "IND":
            if before is not None and before["party"] == "IND":
                units[name] = Unit(name, "IND", "IND", before["votes"] / formal, sitting_ind=bool(r["sitting"]))
            else:
                units[name] = Unit(name, "IND", "IND", NEW_IND_SHARE, new=True)
    # Independents who stood last time but not now: their vote leaves the IND bloc.
    standing = set(ballot["candidate"].to_list())
    for c, r in cand_prev.items():
        if r["party"] == "IND" and c not in standing:
            ind_moved += r["votes"] / formal
    base[IDX["IND"]] = max(base[IDX["IND"]] - ind_moved, 0.0)
    base[IDX["OTH"]] += ind_moved
    base = np.clip(base, 0, None)
    base /= base.sum()
    return list(units.values()), base, notes


def tas_inputs(election: Election, previous: Election,
               log: Callable[[str], None] = print) -> list[DivisionInputs]:
    """Divisions with the ballot (public at nominations, weeks before polling day) and
    the previous result. Sitting members are those marked on the ballot."""
    prev = pl.read_csv(PROCESSED / previous.election_id / "primary.csv")
    ballot = pl.read_csv(PROCESSED / election.election_id / "primary.csv")
    if "sitting" not in ballot.columns:
        # Elections ACT does not mark sitting members: take the previous election's
        # winners (casual vacancies are filled from the same party, so rarely matter).
        won = set(prev.filter(pl.col("elected"))["candidate"].to_list())
        ballot = ballot.with_columns(pl.col("candidate").is_in(list(won)).alias("sitting"))
    seats = dict(pl.read_csv(PROCESSED / election.election_id / "districts.csv")
                 .select("district", "seats").iter_rows())
    out = []
    prev_parties = set(prev["party"].to_list())
    for division in sorted(seats):
        units, base, notes = _units(division, ballot.filter(pl.col("district") == division), prev, log)
        for u in units:
            u.new_party = u.party != "IND" and u.party not in prev_parties
        out.append(DivisionInputs(division, seats[division],
                                  float(prev.filter(pl.col("district") == division)["votes"].sum()),
                                  base, units, notes))
        for n in notes:
            log(f"{division}: {n}")
    log(f"{election.jurisdiction} inputs: {len(out)} divisions, {sum(d.seats for d in out)} seats, "
        f"{sum(u.party == 'IND' for d in out for u in d.units)} independents standing")
    return out


# Federal divisions covering each jurisdiction whose own counts give no preference
# flows (Tasmania's are the same boundaries as its state divisions).
FEDERAL_DIVISIONS = {
    "TAS": ["Bass", "Braddon", "Clark", "Denison", "Franklin", "Lyons"],
    "ACT": ["Bean", "Canberra", "Fenner", "Fraser"],
    "NT": ["Lingiari", "Solomon"],
}


def tas_flows(election: Election, log: Callable[[str], None] = print) -> np.ndarray:
    """Bloc preference flows from the full distributions of preferences in the
    jurisdiction's federal divisions at the two federal elections before ``election``
    (for the territories and Tasmania, and for states whose previous election published
    no distribution, such as South Australia before 2022)."""
    from prophecy.jurisdictions import in_jurisdiction

    feds = [e for e in in_jurisdiction("FED") if e.date < election.date
            and (PROCESSED / e.election_id / "dop_transfers.csv").exists()][-2:]
    def divisions(fed: Election) -> list[str]:
        if election.jurisdiction in FEDERAL_DIVISIONS:
            return FEDERAL_DIVISIONS[election.jurisdiction]
        d = pl.read_csv(PROCESSED / fed.election_id / "districts.csv")
        return d.filter(pl.col("state") == election.jurisdiction)["district"].to_list()

    transfers = pl.concat([
        pl.read_csv(PROCESSED / e.election_id / "dop_transfers.csv")
        .filter(pl.col("district").is_in(divisions(e)))
        .with_columns(pl.lit(e.election_id).alias("e"), pl.col("district") + "-" + e.election_id)
        .select("district", "count", "from_party", "to_party", "votes")
        for e in feds
    ]).with_columns(
        pl.col("from_party").map_elements(bloc, return_dtype=pl.String).alias("from_bloc"),
        pl.col("to_party").map_elements(bloc, return_dtype=pl.String).alias("to_bloc"),
    )
    w = estimate_weights(transfers)
    log(f"flows from federal {election.jurisdiction} distributions: {[e.election_id for e in feds]}, {transfers.height} transfers")
    return w


def hare_clark(votes: np.ndarray, unit_bloc: np.ndarray, cap: np.ndarray, seats: int,
               flows: np.ndarray, exhaust: float = EXHAUST) -> np.ndarray:
    """Seats won by each unit, per simulation.

    votes: S x U first-preference shares; unit_bloc: U bloc indices; cap: U most seats a
    unit can win (1 for an independent); flows: S x B x B Luce weights.
    """
    S, U = votes.shape
    q = 1.0 / (seats + 1)
    V = votes.astype(float).copy()
    won = np.zeros((S, U), dtype=int)
    active = V > 0
    left = np.full(S, seats)
    member = np.zeros((U, len(BLOCS)))
    member[np.arange(U), unit_bloc] = 1.0
    rows = np.arange(S)

    def transfer(s: np.ndarray, u: np.ndarray, amount: np.ndarray) -> None:
        """Move ``amount`` from unit u to the continuing units, by bloc then by vote."""
        if len(s) == 0:
            return
        act = active[s]
        Vb = (V[s] * act) @ member  # s x B continuing votes by bloc
        present = (act.astype(float) @ member) > 0
        f = flows[s, unit_bloc[u], :] * present  # s x B
        denom = f.sum(axis=1) + exhaust
        to_unit = f[:, unit_bloc] / denom[:, None] * act * V[s] / np.maximum(Vb[:, unit_bloc], 1e-12)
        V[s] += amount[:, None] * to_unit

    for _ in range(4 * U + seats + 5):
        go = left > 0
        if not go.any():
            break
        best = np.argmax(np.where(active, V, -np.inf), axis=1)
        best_v = V[rows, best]
        n_active = active.sum(axis=1)
        elect = go & ((best_v >= q) | (n_active <= left))
        exclude = go & ~elect & (n_active > 0)

        s = np.nonzero(elect)[0]
        if len(s):
            u = best[s]
            won[s, u] += 1
            left[s] -= 1
            V[s, u] = np.maximum(V[s, u] - q, 0.0)
            done = (won[s, u] >= cap[u]) | (V[s, u] <= 1e-9)
            sd, ud = s[done], u[done]
            surplus = V[sd, ud].copy()
            V[sd, ud] = 0.0
            active[sd, ud] = False
            transfer(sd, ud, surplus)

        s = np.nonzero(exclude)[0]
        if len(s):
            u = np.argmin(np.where(active[s], V[s], np.inf), axis=1)
            amount = V[s, u].copy()
            V[s, u] = 0.0
            active[s, u] = False
            transfer(s, u, amount)
    return won


@dataclass
class TasResult:
    divisions: list[DivisionInputs]
    statewide: np.ndarray  # S x B (%)
    seats: dict[str, np.ndarray]  # division -> S x U seats won
    shares: dict[str, np.ndarray]  # division -> S x U first-preference shares


def simulate_tas(divisions: list[DivisionInputs], agg_draws: np.ndarray, agg_parties: list[str],
                 flow_weights: np.ndarray, cfg: SimConfig | None = None,
                 new_party_pool: np.ndarray | None = None,
                 new_ind_pool: np.ndarray | None = None) -> TasResult:
    """``new_party_pool`` / ``new_ind_pool``: earlier new parties' and first-time
    independents' shares (``prophecy.model.hareclark_pools``). Without them a new party
    gets a fixed small weight and a new independent a lognormal around 1%."""
    cfg = cfg or SimConfig()
    rng = np.random.default_rng(cfg.seed)
    state = statewide_shares(agg_draws, agg_parties, cfg, rng)
    S, D = state.shape[0], len(divisions)
    weight = np.array([d.formal for d in divisions])
    w = weight / weight.sum()
    base = np.array([d.base for d in divisions])  # D x B
    base_state = base.T @ w

    # A separate stream for the new-entrant draws keeps the others unchanged.
    rng_new = np.random.default_rng(cfg.seed + 2)
    # Each new party's strength: one draw per simulation for the whole jurisdiction.
    party_strength: dict[str, np.ndarray] = {}
    if new_party_pool is not None and len(new_party_pool):
        for party in sorted({u.party for d in divisions for u in d.units if u.new_party}):
            party_strength[party] = new_party_pool[rng_new.integers(0, len(new_party_pool), size=S)]

    # Independents, candidate by candidate.
    ind_shares: list[np.ndarray] = []
    for d in divisions:
        cols = []
        for u in d.units:
            if u.party != "IND":
                continue
            if u.new and new_ind_pool is not None and len(new_ind_pool):
                x = new_ind_pool[rng_new.integers(0, len(new_ind_pool), size=S)] * np.exp(
                    rng_new.normal(0, 0.3, size=S))
            elif u.new:
                x = u.weight * np.exp(rng.normal(-NEW_IND_SD ** 2 / 2, NEW_IND_SD, size=S))
            else:
                decay = 0.0 if u.sitting_ind else cfg.ind_decay_mean
                x = u.weight * np.exp(decay + rng.normal(0, cfg.ind_decay_sd, size=S))
            cols.append(np.clip(x, 0, 0.6))
        ind_shares.append(np.stack(cols, axis=1) if cols else np.zeros((S, 0)))
    ind_total = np.stack([x.sum(axis=1) for x in ind_shares], axis=1)  # S x D
    ind_state = ind_total @ w

    bloc_share = np.zeros((S, D, len(BLOCS)))
    targets = {b: state[:, IDX[b]] / 100 for b in ("ALP", "COAL", "GRN")}
    targets["OTH"] = np.clip(state[:, IDX["OTH"]] / 100 - ind_state, 0.005, None)
    for b in SWING_BLOCS:
        k = IDX[b]
        b0 = np.clip(base[:, k], 0.002, 0.98)
        swing = logit(targets[b]) - logit(np.clip(base_state[k], 0.002, 0.98))
        noise = rng.normal(0, cfg.seat_sd[b], size=(S, D))
        p = logit(b0)[None, :] + swing[:, None] + noise
        bloc_share[:, :, k] = expit(_recentre(p, weight, targets[b]))

    flows = draw_weights(flow_weights, S, rng)
    for b in ("IND", "OTH"):
        flows[:, IDX[b], IDX[b]] = SAME_BLOC
    flows /= flows.sum(axis=2, keepdims=True)

    seats_out, shares_out = {}, {}
    for i, d in enumerate(divisions):
        units = d.units
        U = len(units)
        V = np.zeros((S, U))
        k_ind = 0
        for b in SWING_BLOCS:
            idx = [j for j, u in enumerate(units) if u.bloc == b]
            if not idx:
                continue
            wts = np.tile([units[j].weight for j in idx], (S, 1))
            for c, j in enumerate(idx):
                if units[j].party in party_strength:
                    wts[:, c] = party_strength[units[j].party] * np.exp(
                        rng_new.normal(0, DIVISION_SD, size=S))
            V[:, idx] = bloc_share[:, i, IDX[b]][:, None] * wts / wts.sum(axis=1, keepdims=True)
        for j, u in enumerate(units):
            if u.party == "IND":
                V[:, j] = ind_shares[i][:, k_ind]
                k_ind += 1
        V /= V.sum(axis=1, keepdims=True)
        unit_bloc = np.array([IDX[u.bloc] for u in units])
        cap = np.array([1 if u.party == "IND" else d.seats for u in units])
        seats_out[d.division] = hare_clark(V, unit_bloc, cap, d.seats, flows)
        shares_out[d.division] = V
    return TasResult(divisions, state, seats_out, shares_out)


def party_seats(res: TasResult) -> dict[str, np.ndarray]:
    """S x divisions seats by party label (independents pooled as 'IND')."""
    labels = sorted({u.party for d in res.divisions for u in d.units})
    out = {p: np.zeros((next(iter(res.seats.values())).shape[0], len(res.divisions)), dtype=int) for p in labels}
    for i, d in enumerate(res.divisions):
        for j, u in enumerate(d.units):
            out[u.party][:, i] += res.seats[d.division][:, j]
    return out


def summarise_tas(res: TasResult) -> dict:
    by = party_seats(res)
    total = {p: x.sum(axis=1) for p, x in by.items()}
    n = sum(d.seats for d in res.divisions)
    majority = n // 2 + 1
    q = lambda x: [float(v) for v in np.quantile(x, [0.05, 0.25, 0.5, 0.75, 0.95])]
    lib, alp = total.get("LIB", 0), total.get("ALP", 0)
    divisions = []
    for i, d in enumerate(res.divisions):
        dist = {p: x[:, i] for p, x in by.items() if x[:, i].any()}
        divisions.append({
            "district": d.division, "seats": d.seats, "notes": d.notes,
            "expected": {p: round(float(x.mean()), 2) for p, x in dist.items()},
            "seat_probs": {p: {str(k): round(float(np.mean(x == k)), 4) for k in range(d.seats + 1)
                               if np.mean(x == k) > 0} for p, x in dist.items()},
            "units": [{"label": u.label, "party": u.party,
                       "share": [round(float(v) * 100, 1) for v in
                                 np.quantile(res.shares[d.division][:, j], [0.1, 0.5, 0.9])],
                       "p_seat": round(float(np.mean(res.seats[d.division][:, j] > 0)), 4)}
                      for j, u in enumerate(d.units)],
        })
    return {
        "n_sims": int(res.statewide.shape[0]),
        "seats_total": n,
        "majority": majority,
        "outcome": {
            "lib_majority": float(np.mean(lib >= majority)),
            "alp_majority": float(np.mean(alp >= majority)),
            "hung": float(np.mean((lib < majority) & (alp < majority))),
            "lib_most_seats": float(np.mean(lib > alp)),
            "alp_most_seats": float(np.mean(alp > lib)),
        },
        "seats": {p: q(x) for p, x in total.items()},
        "statewide_primary": {b: [round(float(v), 1) for v in np.quantile(res.statewide[:, k], [0.05, 0.5, 0.95])]
                              for k, b in enumerate(BLOCS)},
        "divisions": divisions,
    }


def score_tas(res: TasResult, members: pl.DataFrame) -> dict:
    """Seat-count accuracy against the members elected."""
    by = party_seats(res)
    actual = {(r[0], r[1]): r[2] for r in members.group_by("district", "party").len().iter_rows()}
    parties = sorted(set(by) | {p for _, p in actual})
    S = next(iter(by.values())).shape[0]
    rows, brier, exact, abs_err = [], [], [], []
    for i, d in enumerate(res.divisions):
        for p in parties:
            x = by[p][:, i] if p in by else np.zeros(S, dtype=int)
            a = actual.get((d.division, p), 0)
            probs = np.bincount(x, minlength=d.seats + 1) / S
            brier.append(float(((probs - (np.arange(len(probs)) == a)) ** 2).sum()))
            exact.append(float(probs[a]) if a < len(probs) else 0.0)
            abs_err.append(abs(float(np.median(x)) - a))
            if x.any() or a:
                rows.append({"division": d.division, "party": p, "actual": a,
                             "median": float(np.median(x)), "mean": round(float(x.mean()), 2),
                             "p_actual": round(float(probs[a]) if a < len(probs) else 0.0, 3)})
    totals = {}
    for p in parties:
        x = by[p].sum(axis=1) if p in by else np.zeros(S, dtype=int)
        a = sum(v for (_, pp), v in actual.items() if pp == p)
        lo, hi = np.quantile(x, [0.05, 0.95])
        totals[p] = {"actual": a, "median": float(np.median(x)), "p90": [float(lo), float(hi)],
                     "covered_90": bool(lo <= a <= hi)}
    return {
        "n_divisions": len(res.divisions),
        "seat_brier": round(float(np.mean(brier)), 4),
        "mean_p_actual_seats": round(float(np.mean(exact)), 4),
        "median_abs_error": round(float(np.mean(abs_err)), 3),
        "seats": totals,
        "by_division": rows,
    }
