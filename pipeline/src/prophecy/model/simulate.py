"""Seat-level Monte Carlo simulation.

For each simulation:
1. Statewide primaries = a poll-aggregator posterior draw for election day, plus a
   systematic polling error (Student-t) common to all seats.
2. Seat primaries for ALP / Coalition / Greens / Others swing on the logit scale from
   the seat's previous result, plus correlated regional effects and seat noise, then
   are re-centred so seats average (vote-weighted) to the statewide figure.
3. One Nation's seat share is statewide ONP x the seat's relative federal-2025 ONP
   strength (ONP barely contested the previous state election).
4. Independents persist from the previous result with a random decay.
5. An exclusion count with simulated preference flows decides each seat.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl
from scipy.special import expit, logit

from prophecy.model.preferences import BLOCS, IDX, count, draw_weights, two_party

SWING_BLOCS = ["ALP", "COAL", "GRN", "OTH"]


@dataclass
class SimConfig:
    n_per_draw: int = 5
    seed: int = 20261128
    # Systematic (industry-wide) polling error, in points, Student-t with df below.
    # PROVISIONAL: to be replaced by the historical final-poll error table.
    poll_error_sd: dict[str, float] = field(
        default_factory=lambda: {"ALP": 2.0, "COAL": 2.0, "GRN": 1.2, "ONP": 2.5}
    )
    poll_error_df: float = 5.0
    region_sd: float = 0.06  # logit, per region x party
    seat_sd: dict[str, float] = field(
        default_factory=lambda: {"ALP": 0.12, "COAL": 0.12, "GRN": 0.18, "OTH": 0.25, "ONP": 0.25}
    )
    ind_decay_mean: float = -0.2  # log scale: independents retain ~80% on average
    ind_decay_sd: float = 0.4


@dataclass
class SeatInputs:
    districts: list[str]
    regions: list[str]
    weight: np.ndarray  # formal votes, D
    base: np.ndarray  # D x B previous primaries (fractions)
    onp_index: np.ndarray  # D, seat ONP strength relative to state (1 = average)
    coal_party: list[str]  # LIB or NAT per seat
    incumbent: list[str]  # party holding the seat now


def build_inputs(primary: pl.DataFrame, districts: pl.DataFrame, federal: pl.DataFrame,
                 regions: pl.DataFrame, holders: dict[str, str] | None = None) -> SeatInputs:
    names = sorted(districts["district"].to_list())
    bloc_votes = primary.group_by("district", "bloc").agg(pl.col("votes").sum())
    base = np.zeros((len(names), len(BLOCS)))
    for d, b, v in bloc_votes.iter_rows():
        base[names.index(d), IDX[b]] += v
    base /= base.sum(axis=1, keepdims=True)

    coal = (
        primary.filter(pl.col("party").is_in(["LIB", "NAT"]))
        .sort("votes", descending=True)
        .group_by("district", maintain_order=True)
        .first()
    )
    coal_party = dict(coal.select("district", "party").iter_rows())

    fed = federal.filter(pl.col("bloc") == "ONP").select("district", "pct", "votes")
    fed_total = federal.group_by("district").agg(pl.col("votes").sum().alias("total"))
    fed = fed.join(fed_total, on="district")
    state_onp = fed["votes"].sum() / fed["total"].sum() * 100
    onp_index = np.array([
        float(fed.filter(pl.col("district") == d)["pct"][0]) / state_onp
        if d in fed["district"].to_list() else 1.0
        for d in names
    ])

    region_map = dict(regions.iter_rows())
    held = dict(districts.select("district", "elected_party").iter_rows())
    if holders:
        held.update(holders)
    return SeatInputs(
        districts=names,
        regions=[region_map[d] for d in names],
        weight=np.array([float(districts.filter(pl.col("district") == d)["formal"][0]) for d in names]),
        base=base,
        onp_index=onp_index,
        coal_party=[coal_party.get(d, "LIB") for d in names],
        incumbent=[held[d] for d in names],
    )


def _recentre(p_logit: np.ndarray, weight: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Shift each simulation's logits so the vote-weighted mean share equals target.

    p_logit: S x D, target: S (fraction). Vectorised bisection on the shift.
    """
    lo = np.full(p_logit.shape[0], -6.0)
    hi = np.full(p_logit.shape[0], 6.0)
    w = weight / weight.sum()
    for _ in range(40):
        mid = (lo + hi) / 2
        mean = expit(p_logit + mid[:, None]) @ w
        too_high = mean > target
        hi = np.where(too_high, mid, hi)
        lo = np.where(too_high, lo, mid)
    return p_logit + ((lo + hi) / 2)[:, None]


@dataclass
class SimResult:
    inputs: SeatInputs
    statewide: np.ndarray  # S x B statewide primaries (%), after polling error
    seat_primary: np.ndarray  # S x D x B (fractions)
    winner: np.ndarray  # S x D bloc index
    final: np.ndarray  # S x D x B final-count shares
    weights: np.ndarray  # S x B x B flow weights
    tpp_alp_coal: np.ndarray  # S


def simulate(inputs: SeatInputs, agg_draws: np.ndarray, agg_parties: list[str],
             flow_weights: np.ndarray, cfg: SimConfig | None = None) -> SimResult:
    """agg_draws: draws x parties election-day shares (%) from the aggregator."""
    cfg = cfg or SimConfig()
    rng = np.random.default_rng(cfg.seed)
    D = len(inputs.districts)
    draws = np.repeat(agg_draws, cfg.n_per_draw, axis=0)
    S = draws.shape[0]

    # 1. Statewide shares with systematic polling error, in model bloc order.
    state = np.zeros((S, len(BLOCS)))
    for k, p in enumerate(agg_parties):
        state[:, IDX[p]] = draws[:, k]
    scale = np.sqrt((cfg.poll_error_df - 2) / cfg.poll_error_df)
    for p, sd in cfg.poll_error_sd.items():
        state[:, IDX[p]] += sd * scale * rng.standard_t(cfg.poll_error_df, size=S)
    modelled = [IDX[p] for p in agg_parties]
    state[:, modelled] = np.clip(state[:, modelled], 0.3, None)
    state = 100 * state / state.sum(axis=1, keepdims=True)

    w = inputs.weight / inputs.weight.sum()
    base_state = inputs.base.T @ w  # B, previous statewide shares
    region_names = sorted(set(inputs.regions))
    region_idx = np.array([region_names.index(r) for r in inputs.regions])

    seat = np.zeros((S, D, len(BLOCS)))

    # 4. Independents: persist with random decay.
    ind = inputs.base[:, IDX["IND"]][None, :] * np.exp(
        rng.normal(cfg.ind_decay_mean, cfg.ind_decay_sd, size=(S, D))
    )
    seat[:, :, IDX["IND"]] = ind
    ind_state = ind @ w  # S

    # 2. Logit swing for ALP, COAL, GRN, OTH (OTH target excludes independents).
    targets = {b: state[:, IDX[b]] / 100 for b in ("ALP", "COAL", "GRN")}
    targets["OTH"] = np.clip(state[:, IDX["OTH"]] / 100 - ind_state, 0.005, None)
    for b in SWING_BLOCS:
        k = IDX[b]
        base = np.clip(inputs.base[:, k], 0.002, 0.98)
        swing = logit(targets[b]) - logit(np.clip(base_state[k], 0.002, 0.98))
        region_eff = rng.normal(0, cfg.region_sd, size=(S, len(region_names)))[:, region_idx]
        noise = rng.normal(0, cfg.seat_sd[b], size=(S, D))
        p = logit(base)[None, :] + swing[:, None] + region_eff + noise
        seat[:, :, k] = expit(_recentre(p, inputs.weight, targets[b]))

    # 3. One Nation from federal geography.
    onp = inputs.onp_index[None, :] * np.exp(rng.normal(0, cfg.seat_sd["ONP"], size=(S, D)))
    onp *= (state[:, IDX["ONP"]] / 100 / (onp @ w))[:, None]
    seat[:, :, IDX["ONP"]] = np.clip(onp, 0, 0.9)

    seat /= seat.sum(axis=2, keepdims=True)

    # 5. Preference count.
    flows = draw_weights(flow_weights, S, rng)
    winner, final = count(seat, flows)
    # Statewide 2PP: split the simulated independent vote back out of "Others", since
    # independents' preferences differ from minor parties'.
    tpp_primary = state / 100
    tpp_primary[:, IDX["IND"]] = np.minimum(ind_state, tpp_primary[:, IDX["OTH"]])
    tpp_primary[:, IDX["OTH"]] -= tpp_primary[:, IDX["IND"]]
    tpp = two_party(tpp_primary, flows, "ALP", "COAL")
    return SimResult(inputs, state, seat, winner, final, flows, tpp)


def seat_labels(res: SimResult) -> np.ndarray:
    """Winner as a party label per sim and seat (Coalition split into LIB/NAT)."""
    labels = np.array(BLOCS, dtype=object)[res.winner]
    coal = np.array(res.inputs.coal_party, dtype=object)[None, :].repeat(labels.shape[0], 0)
    return np.where(labels == "COAL", coal, labels)


def summarise(res: SimResult) -> dict:
    labels = seat_labels(res)
    S, D = labels.shape
    parties = ["ALP", "LIB", "NAT", "GRN", "ONP", "IND", "OTH"]
    seats = {p: (labels == p).sum(axis=1) for p in parties}
    coal = seats["LIB"] + seats["NAT"]
    majority = D // 2 + 1
    outcome = {
        "alp_majority": float(np.mean(seats["ALP"] >= majority)),
        "coal_majority": float(np.mean(coal >= majority)),
        "hung": float(np.mean((seats["ALP"] < majority) & (coal < majority))),
        "alp_most_seats": float(np.mean(seats["ALP"] > coal)),
        "coal_most_seats": float(np.mean(coal > seats["ALP"])),
    }
    q = lambda x: [float(v) for v in np.quantile(x, [0.05, 0.25, 0.5, 0.75, 0.95])]
    seat_dist = {p: q(seats[p]) for p in parties}
    seat_dist["COAL"] = q(coal)
    hist = {p: np.bincount(seats[p], minlength=D + 1).tolist() for p in ["ALP", "GRN", "ONP", "IND"]}
    hist["COAL"] = np.bincount(coal, minlength=D + 1).tolist()

    per_seat = []
    for d, name in enumerate(res.inputs.districts):
        probs = {p: float(np.mean(labels[:, d] == p)) for p in parties}
        prim = res.seat_primary[:, d, :] * 100
        per_seat.append({
            "district": name,
            "region": res.inputs.regions[d],
            "incumbent": res.inputs.incumbent[d],
            "probs": {p: round(v, 4) for p, v in probs.items() if v > 0},
            "primary": {b: [round(float(v), 1) for v in np.quantile(prim[:, k], [0.1, 0.5, 0.9])]
                        for k, b in enumerate(BLOCS)},
        })
    return {
        "n_sims": int(S),
        "majority": majority,
        "outcome": outcome,
        "seats": seat_dist,
        "seat_hist": hist,
        "statewide_primary": {b: [round(float(v), 1) for v in np.quantile(res.statewide[:, k], [0.05, 0.5, 0.95])]
                              for k, b in enumerate(BLOCS)},
        "tpp_alp": [round(float(v), 1) for v in np.quantile(res.tpp_alp_coal, [0.05, 0.5, 0.95])],
        "districts": per_seat,
    }
