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

from prophecy.model.preferences import BLOCS, IDX, count, draw_exhaust, draw_weights, two_party

SWING_BLOCS = ["ALP", "COAL", "GRN", "OTH"]
COAL_SPLIT_SD = 0.6  # logit: spread of the Liberal-National split in a three-cornered contest


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
    # Correlation of the parties' polling errors (order ``poll_error_corr_parties``);
    # absent: independent errors.
    poll_error_corr: list[list[float]] | None = None
    poll_error_corr_parties: list[str] = field(default_factory=list)
    # Persistent poll lean (points, polls minus result) subtracted from the aggregate.
    poll_bias: dict[str, float] = field(default_factory=dict)
    region_sd: float = 0.06  # logit, per region x party
    seat_sd: dict[str, float] = field(
        default_factory=lambda: {"ALP": 0.12, "COAL": 0.12, "GRN": 0.18, "OTH": 0.25, "ONP": 0.25}
    )
    # Student-t degrees of freedom of seat noise per party (absent: Gaussian), and the
    # regression to the mean of seat swings on the seat's centred logit share (absent: 0).
    # Both estimated from past elections by ``prophecy.model.swing_fit``.
    seat_df: dict[str, float] = field(default_factory=dict)
    seat_beta: dict[str, float] = field(default_factory=dict)
    ind_decay_mean: float = -0.2  # log scale: independents retain ~80% on average
    ind_decay_sd: float = 0.4
    # Candidate effects on the logit primary vote of the party concerned (priors, in line
    # with Australian estimates of 1-2 points; not estimable from our 2014-22 data).
    retire_effect: float = -0.08  # sitting member not recontesting: lost personal vote
    sophomore_effect: float = 0.05  # first-term member recontesting: personal vote gained
    ind_prior_sd: float = 0.35  # log-scale spread around a curated independent's prior
    ind_sophomore_log: float = 0.15  # first-term independent recontesting (~+16%)
    ind_retire_log: float = -1.2  # sitting independent retiring: ~70% of their vote leaves


@dataclass
class SeatInputs:
    districts: list[str]
    regions: list[str]
    weight: np.ndarray  # formal votes, D
    base: np.ndarray  # D x B previous primaries (fractions)
    onp_index: np.ndarray  # D, seat ONP strength relative to state (1 = average)
    coal_party: list[str]  # LIB or NAT per seat
    incumbent: list[str]  # party holding the seat now
    # Candidate adjustments (filled by apply_candidates; neutral by default).
    retiring: np.ndarray | None = None  # D x B: 1 where that bloc's sitting member retires
    sophomore: np.ndarray | None = None  # D x B: 1 where a first-term member recontests
    contest: np.ndarray | None = None  # D x B bool: bloc has a candidate (None = all)
    ind_prior: np.ndarray | None = None  # D: expected IND share (fraction), NaN = none
    new_ind: np.ndarray | None = None  # D: first-time independents on the ballot
    new_ind_pool: np.ndarray | None = None  # earlier first-time independents' shares (fractions)
    # Three-cornered contests: the Liberal share of the Coalition vote last time where a
    # Liberal and a National both stand (0.5 when only one stood), NaN elsewhere.
    lib_share: np.ndarray | None = None
    notes: dict[str, list[str]] = field(default_factory=dict)


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
    state_onp = fed["votes"].sum() / fed["total"].sum() * 100 if fed.height else 1.0
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


def apply_candidates(inputs: SeatInputs, members: pl.DataFrame | None,
                     candidates: pl.DataFrame | None, sophomore_since: int) -> SeatInputs:
    """Attach member status (retirements, first-term members) and the ballot.

    members: district, party, first_elected, status (recontesting/retiring/vacant).
    candidates: district, party (code), name, [prior_share] for independents. Once
    nominations close, a bloc with no candidate in a seat gets no vote there.
    """
    D, B = len(inputs.districts), len(BLOCS)
    idx = {d: i for i, d in enumerate(inputs.districts)}
    retiring = np.zeros((D, B))
    sophomore = np.zeros((D, B))
    notes: dict[str, list[str]] = {}
    if members is not None:
        for r in members.iter_rows(named=True):
            i = idx.get(r["district"])
            if i is None:
                continue
            # Effects apply to the party the member was elected for: a defector's
            # personal vote at the last election was cast for that party.
            elected_bloc = _bloc(inputs.incumbent[i] if r["party"] == "IND" else r["party"])
            if r["status"] in ("retiring", "vacant"):
                retiring[i, IDX[elected_bloc]] = 1
                notes.setdefault(r["district"], []).append(f"sitting member not recontesting ({r['status']})")
            elif str(r["first_elected"])[:4].isdigit() and int(str(r["first_elected"])[:4]) >= sophomore_since:
                sophomore[i, IDX[_bloc(r["party"])]] = 1
                notes.setdefault(r["district"], []).append(f"first-term member recontesting (since {r['first_elected']})")
    contest = None
    ind_prior = np.full(D, np.nan)
    if candidates is not None and candidates.height:
        contest = np.zeros((D, B), dtype=bool)
        for r in candidates.iter_rows(named=True):
            i = idx.get(r["district"])
            if i is None:
                continue
            b = _bloc(r["party"])
            contest[i, IDX[b]] = True
            share = r.get("prior_share")
            if b == "IND" and share is not None and not np.isnan(float(share)):
                ind_prior[i] = np.nansum([ind_prior[i], float(share) / 100])
        # Seats not yet on the ballot file keep everyone in contention.
        listed = set(candidates["district"].to_list())
        for d, i in idx.items():
            if d not in listed:
                contest[i] = True
    inputs.retiring, inputs.sophomore, inputs.contest, inputs.ind_prior = retiring, sophomore, contest, ind_prior
    for d, ns in notes.items():
        inputs.notes.setdefault(d, []).extend(ns)
    return inputs


def _bloc(code: str) -> str:
    from prophecy.schema.parties import bloc

    return bloc(code)


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


def _seat_noise(rng: np.random.Generator, df: float | None, size: tuple[int, int]) -> np.ndarray:
    """Standard seat noise: Student-t with ``df`` degrees of freedom (scale 1), or normal."""
    return rng.standard_t(df, size=size) if df else rng.standard_normal(size)


def _candidate_adj(inputs: SeatInputs, k: int, cfg: SimConfig) -> np.ndarray:
    adj = np.zeros(len(inputs.districts))
    if inputs.retiring is not None:
        adj += cfg.retire_effect * inputs.retiring[:, k]
    if inputs.sophomore is not None:
        adj += cfg.sophomore_effect * inputs.sophomore[:, k]
    return adj


@dataclass
class SimResult:
    inputs: SeatInputs
    statewide: np.ndarray  # S x B statewide primaries (%), after polling error
    seat_primary: np.ndarray  # S x D x B (fractions)
    winner: np.ndarray  # S x D bloc index
    final: np.ndarray  # S x D x B final-count shares
    weights: np.ndarray  # S x B x B flow weights
    tpp_alp_coal: np.ndarray  # S
    coal_label: np.ndarray | None = None  # S x D Coalition party where both stand, else None


def statewide_shares(agg_draws: np.ndarray, agg_parties: list[str], cfg: SimConfig,
                     rng: np.random.Generator) -> np.ndarray:
    """Statewide primaries (%) per simulation, in model bloc order: each aggregator draw
    repeated ``n_per_draw`` times, less the poll bias, plus a systematic polling error."""
    draws = np.repeat(agg_draws, cfg.n_per_draw, axis=0)
    S = draws.shape[0]
    state = np.zeros((S, len(BLOCS)))
    for k, p in enumerate(agg_parties):
        state[:, IDX[p]] = draws[:, k]
    scale = np.sqrt((cfg.poll_error_df - 2) / cfg.poll_error_df)
    for p, b in cfg.poll_bias.items():
        if p in agg_parties:
            state[:, IDX[p]] -= b
    corr_parties = [p for p in cfg.poll_error_corr_parties if p in agg_parties] if cfg.poll_error_corr else []
    if corr_parties:
        # Multivariate t: correlated normals over one shared chi-square scale.
        idx = [cfg.poll_error_corr_parties.index(p) for p in corr_parties]
        c = np.asarray(cfg.poll_error_corr)[np.ix_(idx, idx)]
        sds = np.array([cfg.poll_error_sd[p] for p in corr_parties])
        z = rng.standard_normal((S, len(corr_parties))) @ np.linalg.cholesky(c).T
        mix = np.sqrt(cfg.poll_error_df / rng.chisquare(cfg.poll_error_df, size=S))
        for j, p in enumerate(corr_parties):
            state[:, IDX[p]] += sds[j] * scale * z[:, j] * mix
    for p, sd in cfg.poll_error_sd.items():
        if p in agg_parties and p not in corr_parties:  # e.g. ONP is not modelled in cycles where it wasn't polled
            state[:, IDX[p]] += sd * scale * rng.standard_t(cfg.poll_error_df, size=S)
    modelled = [IDX[p] for p in agg_parties]
    state[:, modelled] = np.clip(state[:, modelled], 0.3, None)
    return 100 * state / state.sum(axis=1, keepdims=True)


def simulate(inputs: SeatInputs, agg_draws: np.ndarray, agg_parties: list[str],
             flow_weights: np.ndarray, cfg: SimConfig | None = None,
             exhaust: np.ndarray | None = None) -> SimResult:
    """agg_draws: draws x parties election-day shares (%) from the aggregator.

    exhaust: per-bloc exhaustion weights under optional preferential voting (NSW).
    """
    cfg = cfg or SimConfig()
    rng = np.random.default_rng(cfg.seed)
    D = len(inputs.districts)
    state = statewide_shares(agg_draws, agg_parties, cfg, rng)
    S = state.shape[0]

    w = inputs.weight / inputs.weight.sum()
    base_state = inputs.base.T @ w  # B, previous statewide shares
    region_names = sorted(set(inputs.regions))
    region_idx = np.array([region_names.index(r) for r in inputs.regions])

    seat = np.zeros((S, D, len(BLOCS)))

    # 4. Independents: persist with random decay, or around a curated prior where a
    #    notable independent is on the ballot.
    # Sitting independents keep their vote (no decay); first-term ones gain; when a
    # sitting independent retires most of their personal vote goes with them.
    decay = np.full(D, cfg.ind_decay_mean)
    if inputs.retiring is not None and inputs.sophomore is not None:
        k = IDX["IND"]
        sitting_ind = np.array([_bloc(h) == "IND" for h in inputs.incumbent])
        decay = np.where(sitting_ind, 0.0, decay)
        decay = np.where(inputs.sophomore[:, k] > 0, cfg.ind_sophomore_log, decay)
        decay = np.where(inputs.retiring[:, k] > 0, cfg.ind_retire_log, decay)
    ind = inputs.base[:, IDX["IND"]][None, :] * np.exp(
        decay[None, :] + rng.normal(0, cfg.ind_decay_sd, size=(S, D))
    )
    if inputs.ind_prior is not None and np.isfinite(inputs.ind_prior).any():
        has = np.isfinite(inputs.ind_prior)
        prior = np.nan_to_num(inputs.ind_prior)[None, :] * np.exp(
            rng.normal(0, cfg.ind_prior_sd, size=(S, D)))
        ind = np.where(has[None, :], prior, ind)
    if inputs.new_ind is not None and inputs.new_ind_pool is not None:
        # First-time independents on the ballot (not curated): resampled from what such
        # candidates polled before. A separate stream keeps the other draws unchanged.
        from prophecy.model.new_candidates import draw

        n_new = inputs.new_ind.copy()
        if inputs.ind_prior is not None:
            n_new[np.isfinite(inputs.ind_prior)] = 0
        ind = ind + draw(n_new, inputs.new_ind_pool, S, np.random.default_rng(cfg.seed + 1))
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
        noise = cfg.seat_sd[b] * _seat_noise(rng, cfg.seat_df.get(b), (S, D))
        l0 = logit(base)
        rtm = cfg.seat_beta.get(b, 0.0) * (l0 - l0 @ w)  # strong seats swing back
        p = (l0 + rtm)[None, :] + swing[:, None] + region_eff + noise + _candidate_adj(inputs, k, cfg)[None, :]
        seat[:, :, k] = expit(_recentre(p, inputs.weight, targets[b]))

    # 3. One Nation from federal geography (only when ONP is modelled this cycle).
    if "ONP" in agg_parties:
        onp = inputs.onp_index[None, :] * np.exp(rng.normal(0, cfg.seat_sd["ONP"], size=(S, D)))
        onp *= (state[:, IDX["ONP"]] / 100 / (onp @ w))[:, None]
        seat[:, :, IDX["ONP"]] = np.clip(onp, 0, 0.9)

    if inputs.contest is not None:
        seat *= inputs.contest[None, :, :]
    seat /= seat.sum(axis=2, keepdims=True)

    # 5. Preference count.
    flows = draw_weights(flow_weights, S, rng)
    ex = draw_exhaust(exhaust, S, rng) if exhaust is not None else None
    winner, final = count(seat, flows, ex)
    # Statewide 2PP: split the simulated independent vote back out of "Others", since
    # independents' preferences differ from minor parties'.
    tpp_primary = state / 100
    tpp_primary[:, IDX["IND"]] = np.minimum(ind_state, tpp_primary[:, IDX["OTH"]])
    tpp_primary[:, IDX["OTH"]] -= tpp_primary[:, IDX["IND"]]
    tpp = two_party(tpp_primary, flows, "ALP", "COAL", ex)
    coal_label = None
    if inputs.lib_share is not None and np.isfinite(inputs.lib_share).any():
        # Which Coalition party leads the Coalition vote: the previous split, with a
        # wide spread on the logit scale (candidates and campaigns vary).
        r = np.random.default_rng(cfg.seed + 3)
        split = np.clip(np.nan_to_num(inputs.lib_share, nan=0.5), 0.02, 0.98)
        lib = expit(logit(split)[None, :] + r.normal(0, COAL_SPLIT_SD, size=(S, D))) > 0.5
        coal_label = np.where(lib, "LIB", "NAT").astype(object)
        coal_label[:, ~np.isfinite(inputs.lib_share)] = None
    return SimResult(inputs, state, seat, winner, final, flows, tpp, coal_label)


TPP_STEP = 0.5  # percentage points per bin of the published 2PP histogram


def seat_labels(res: SimResult) -> np.ndarray:
    """Winner as a party label per sim and seat (Coalition split into LIB/NAT)."""
    labels = np.array(BLOCS, dtype=object)[res.winner]
    coal = np.array(res.inputs.coal_party, dtype=object)[None, :].repeat(labels.shape[0], 0)
    if res.coal_label is not None:
        coal = np.where(res.coal_label != None, res.coal_label, coal)  # noqa: E711 (object array)
    return np.where(labels == "COAL", coal, labels)


def summary_parties(res: SimResult) -> list[str]:
    """Party labels a forecast reports seats for."""
    parties = ["ALP", "LIB", "NAT", "GRN", "ONP", "IND", "OTH"]
    for merged in ("LNP", "CLP"):  # Queensland's and the NT's merged Coalition parties
        if merged in res.inputs.coal_party:
            parties.insert(3, merged)
    return parties


def sim_arrays(res: SimResult) -> dict[str, np.ndarray]:
    """Every simulation, for the site to condition on: winner per seat (index into
    ``parties``), statewide primaries (%) by bloc, and the ALP v Coalition 2PP."""
    labels = seat_labels(res)
    parties = summary_parties(res)
    unknown = set(np.unique(labels)) - set(parties)
    if unknown:
        raise ValueError(f"Seat winners outside the reported parties: {sorted(unknown)}")
    winners = np.zeros(labels.shape, dtype=np.uint8)
    for k, p in enumerate(parties):
        winners[labels == p] = k
    return {
        "winners": winners,
        "parties": np.array(parties),
        "districts": np.array(res.inputs.districts),
        "blocs": np.array(BLOCS),
        "statewide": res.statewide.astype(np.float32),
        "tpp": res.tpp_alp_coal.astype(np.float32),
    }


def summarise(res: SimResult) -> dict:
    labels = seat_labels(res)
    S, D = labels.shape
    parties = summary_parties(res)
    seats = {p: (labels == p).sum(axis=1) for p in parties}
    coal = sum(seats[p] for p in ("LIB", "NAT", "LNP", "CLP") if p in seats)
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
    # Coalition seats minus Labor seats, and the two together (how big a win, and which
    # combinations of seats are likely), for the site's margin histogram and heatmap.
    margin = coal - seats["ALP"]
    lo = int(margin.min())
    joint, joint_n = np.unique(np.stack([seats["ALP"], coal], axis=1), axis=0, return_counts=True)
    tpp_lo = float(np.floor(res.tpp_alp_coal.min()))
    tpp_bins = np.floor((res.tpp_alp_coal - tpp_lo) / TPP_STEP).astype(int)

    per_seat = []
    for d, name in enumerate(res.inputs.districts):
        probs = {p: float(np.mean(labels[:, d] == p)) for p in parties}
        prim = res.seat_primary[:, d, :] * 100
        per_seat.append({
            "district": name,
            "region": res.inputs.regions[d],
            "incumbent": res.inputs.incumbent[d],
            "notes": res.inputs.notes.get(name, []),
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
        "seat_margin": {"min": lo, "counts": np.bincount(margin - lo).tolist()},
        "seat_joint": [[int(a), int(c), int(n)] for (a, c), n in zip(joint, joint_n)],
        "tpp_hist": {"min": tpp_lo, "step": TPP_STEP, "counts": np.bincount(tpp_bins).tolist()},
        "districts": per_seat,
    }
