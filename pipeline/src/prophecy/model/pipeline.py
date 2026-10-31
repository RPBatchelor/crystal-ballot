"""End-to-end steps shared by the live forecast and historical backtests."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import polars as pl

from prophecy import DATA_DIR
from prophecy.ingest.vec import canonical_district
from prophecy.jurisdictions import Election
from prophecy.model.aggregate import AggregateFit, fit, summarise
from prophecy.model.preferences import (
    BLOCS,
    IDX,
    apply_onp_targets,
    calibrate_to_results,
    estimate_weights,
    two_party,
)
from prophecy.model.simulate import SeatInputs, SimConfig, build_inputs
from prophecy.schema.parties import bloc

PROCESSED = DATA_DIR / "processed"
RUNS = DATA_DIR.parent / "runs"
# Preference distributions are only published for 2022; earlier elections reuse their
# structure, re-calibrated to that election's own seat results.
FLOW_SOURCE = "vic-2022"
ONP_START = 3.0  # ONP's starting level (%) when the previous Assembly barely had it


def start_shares(previous: Election) -> dict[str, float]:
    """Previous election's statewide bloc shares as the aggregator's anchor."""
    share = pl.read_csv(PROCESSED / previous.election_id / "primary.csv").group_by("bloc").agg(
        pl.col("votes").sum()
    )
    total = share["votes"].sum()
    s = {b: 100 * v / total for b, v in share.iter_rows()}
    # ONP: its actual share where it contested broadly, else a vague low starting level.
    onp = s.get("ONP", 0.0) if s.get("ONP", 0.0) >= 1.0 else ONP_START
    return {"ALP": s["ALP"], "COAL": s["COAL"], "GRN": s["GRN"], "ONP": onp,
            "OTH": 100 - s["ALP"] - s["COAL"] - s["GRN"] - onp}


def run_aggregate(election: Election, previous: Election, polls: pl.DataFrame,
                  out_dir: Path, run_dir: Path, log: Callable[[str], None] = print,
                  **sample_kw) -> AggregateFit:
    start = start_shares(previous)
    f = fit(polls, previous, election, start, **sample_kw)
    diag = {k: v for k, v in f.diagnostics.items() if k != "report"}
    log(f"diagnostics: {diag}")
    if diag["max_rhat"] > 1.01 or diag["divergences"] > 0:
        log("WARNING: sampler diagnostics failed thresholds")
    # Persist draws first so post-processing failures never require a refit.
    run_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(run_dir / "aggregate_draws.npz", shares=f.shares.astype(np.float32),
                        parties=np.array(f.parties))
    out_dir.mkdir(parents=True, exist_ok=True)
    f.house.write_csv(out_dir / "house_effects.csv")
    (out_dir / "aggregate_meta.json").write_text(json.dumps(
        {"diagnostics": diag, "start_share": start, "pollsters": f.pollsters,
         "dynamics": {k: [round(float(x), 4) for x in np.ravel(np.median(v, axis=0))]
                      for k, v in f.params.items()},
         "parties": f.parties, "weeks": [w.isoformat() for w in f.weeks]}, indent=1))
    summarise(f, polls).write_csv(out_dir / "poll_trend.csv")
    return f


SWING_FLOOR = {"ALP": 3.0, "COAL": 3.0, "GRN": 1.5}  # points, for the no-polls prior


def swing_prior(election: Election, previous: Election, out_dir: Path, run_dir: Path,
                polls: pl.DataFrame | None = None, n_draws: int = 4000, seed: int = 20261128,
                log: Callable[[str], None] = print) -> None:
    """Stand-in for the poll aggregate when an election had too few public polls to fit
    it (none for the ACT in 2024; two for the NT): a centre plus a swing drawn from the
    jurisdiction's own election-to-election changes (root mean square, floored), saved
    in the aggregator's format. The centre is the previous result, or for each party the
    average of the polls of the last year that report it."""
    code = election.jurisdiction.lower()
    hist = (pl.read_csv(PROCESSED / f"election_results_{code}.csv", try_parse_dates=True)
            .filter(pl.col("year") < election.date.year).sort("year"))
    start = start_shares(previous)
    parties = ["ALP", "COAL", "GRN", "OTH"]
    start = {"ALP": start["ALP"], "COAL": start["COAL"], "GRN": start["GRN"],
             "OTH": start["OTH"] + start["ONP"]}
    used = []
    if polls is not None and polls.height:
        from datetime import timedelta

        recent = polls.filter(pl.col("field_end") >= election.date - timedelta(days=365))
        for p in parties[:-1]:
            v = recent[p].drop_nulls() if p in recent.columns else pl.Series([])
            if len(v):
                start[p] = float(v.mean())
                used.append(p)
        start["OTH"] = 100 - sum(start[p] for p in parties[:-1])
    # The government's vote tends to fall: shift its centre by the average change in
    # governing parties' primary votes at earlier elections (unless polls set it).
    gov = governing_bloc(previous)
    shift = government_swing(election.date) if gov and gov not in used else 0.0
    if shift:
        start[gov] += shift
        start["OTH"] -= shift
        log(f"no polls for the governing party ({gov}): centre shifted {shift:+.1f} points")
    rng = np.random.default_rng(seed)
    shares = np.zeros((n_draws, 1, len(parties)))
    sd = {}
    for k, p in enumerate(parties[:-1]):
        changes = hist[p].diff().drop_nulls().to_numpy()
        rms = float(np.sqrt(np.mean(changes ** 2))) if len(changes) else 0.0
        sd[p] = round(max(rms, SWING_FLOOR[p]), 2)
        shares[:, 0, k] = start[p] + rng.normal(0, sd[p], n_draws)
    shares[:, 0, :-1] = np.clip(shares[:, 0, :-1], 0.5, None)
    shares[:, 0, -1] = np.clip(100 - shares[:, 0, :-1].sum(axis=1), 1.0, None)
    shares[:, 0, :] *= 100 / shares[:, 0, :].sum(axis=1, keepdims=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(run_dir / "aggregate_draws.npz", shares=shares.astype(np.float32),
                        parties=np.array(parties))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "aggregate_meta.json").write_text(json.dumps(
        {"no_polls": True, "poll_average_for": used, "start_share": start, "swing_sd": sd,
         "government": gov, "government_shift": shift,
         "swing_from": hist["year"].to_list()}, indent=1))
    log(f"too few polls: centre {({k: round(v, 1) for k, v in start.items()})} "
        f"(poll average for {used or 'none'}, else previous result) "
        f"plus swing sd {sd} (from {len(hist)} past results)")


GOV_SHRINK = 10  # pseudo-elections shrinking the average government swing toward zero


def governing_bloc(election: Election) -> str | None:
    """ALP or COAL, whichever won more seats at ``election`` (None if neither)."""
    path = PROCESSED / election.election_id / "districts.csv"
    if not path.exists():
        return None
    d = pl.read_csv(path, infer_schema_length=None)
    party = "elected_party" if "elected_party" in d.columns else None
    if party is None:  # Hare-Clark: one row per division, members listed in members.csv
        m = PROCESSED / election.election_id / "members.csv"
        if not m.exists():
            return None
        parties = pl.read_csv(m)["party"].to_list()
    else:
        parties = [x for v in d[party].to_list() for x in str(v).split("; ")]
    n = {"ALP": 0, "COAL": 0}
    for x in parties:
        b = bloc(x)
        if b in n:
            n[b] += 1
    return max(n, key=n.get) if max(n.values()) > 0 else None


def government_swing(before) -> float:
    """Average change in the governing bloc's primary vote (points) at elections before
    ``before``, in every jurisdiction, shrunk toward zero."""
    from prophecy.jurisdictions import in_jurisdiction

    changes = []
    for j in ("VIC", "NSW", "QLD", "WA", "SA", "TAS", "ACT", "NT", "FED"):
        path = PROCESSED / f"election_results_{j.lower()}.csv"
        if not path.exists():
            continue
        res = {r["year"]: r for r in pl.read_csv(path, try_parse_dates=True).iter_rows(named=True)}
        els = [e for e in in_jurisdiction(j) if e.date < before and e.date.year in res]
        for prev, e in zip(els, els[1:]):
            g = governing_bloc(prev)
            a, b = res[prev.date.year].get(g), res[e.date.year].get(g)
            if g and a is not None and b is not None:
                changes.append(b - a)
    if not changes:
        return 0.0
    return round(float(np.sum(changes) / (len(changes) + GOV_SHRINK)), 2)


def load_draws(run_dir: Path) -> tuple[np.ndarray, list[str]]:
    agg = np.load(run_dir / "aggregate_draws.npz")
    return agg["shares"], [str(p) for p in agg["parties"]]


def seat_inputs(previous: Election, boundaries: str, onp_geography: bool,
                log: Callable[[str], None] = print,
                election: Election | None = None) -> SeatInputs:
    from prophecy.ingest.federal_xwalk import district_regions, federal_by_state_district

    base_dir = PROCESSED / previous.election_id
    primary = pl.read_csv(base_dir / "primary.csv")
    districts = pl.read_csv(base_dir / "districts.csv")
    canon = pl.col("district").map_elements(canonical_district, return_dtype=pl.String)
    # Derived tables are cached in data/processed (committed) so the forecast runs
    # without the large raw boundary/booth downloads (e.g. in CI).
    regions_path = PROCESSED / f"regions_{boundaries}.csv"
    if regions_path.exists():
        regions = pl.read_csv(regions_path)
    else:
        regions = district_regions(boundaries).with_columns(canon)
        regions.write_csv(regions_path)
    if onp_geography:
        federal_path = base_dir / "federal2025_by_district.csv"
        if federal_path.exists():
            federal = pl.read_csv(federal_path)
        else:
            federal = federal_by_state_district(boundaries=boundaries).with_columns(canon)
            federal.write_csv(federal_path)
        missing = set(districts["district"]) - set(federal["district"])
        if missing:
            log(f"WARNING: no federal booths matched for {sorted(missing)}")
    else:
        federal = pl.DataFrame(schema={"district": pl.String, "bloc": pl.String,
                                       "votes": pl.Int64, "pct": pl.Float64})
    missing_regions = set(districts["district"]) - set(regions["district"])
    if missing_regions:
        raise ValueError(f"No region for districts {sorted(missing_regions)} in {boundaries}")
    by_dir = PROCESSED / f"{previous.election_id}-by-elections"
    holders = {}
    if by_dir.exists():
        holders = dict(pl.read_csv(by_dir / "districts.csv").select("district", "elected_party").iter_rows())
    inputs = build_inputs(primary, districts, federal, regions, holders)
    if election is not None:
        if by_dir.exists():
            byelection_adjust(inputs, by_dir, PROCESSED / election.election_id / "poll_trend.csv",
                              previous, log)
        inputs = attach_candidates(inputs, election, previous, log)
    return inputs


BYELECTION_PERSISTENCE = 0.5  # share of a by-election's excess local swing carried forward
BYELECTION_BLOCS = ("ALP", "COAL", "GRN")


def byelection_adjust(inputs: SeatInputs, by_dir: Path, trend_path: Path, previous: Election,
                      log: Callable[[str], None] = print) -> None:
    """Shift seat baselines by the by-election swing beyond the statewide poll movement.

    Only used where Labor, the Coalition and the Greens all contested both the previous
    general election and the by-election: when a major party sits out, its vote spills
    to the others and the primaries are not comparable.
    """
    if not trend_path.exists():
        return
    trend = pl.read_csv(trend_path, try_parse_dates=True, infer_schema_length=None)
    by_primary = pl.read_csv(by_dir / "primary.csv")
    by_districts = pl.read_csv(by_dir / "districts.csv", try_parse_dates=True)
    # Statewide change is measured from the previous election's actual result.
    w = inputs.weight / inputs.weight.sum()
    start = {b: 100 * float(inputs.base[:, IDX[b]] @ w) for b in BYELECTION_BLOCS}
    for r in by_districts.iter_rows(named=True):
        name = r["district"]
        if name not in inputs.districts:
            continue
        d = inputs.districts.index(name)
        shares = dict(by_primary.filter(pl.col("district") == name).group_by("bloc")
                      .agg(pl.col("pct").sum()).iter_rows())
        if any(shares.get(b, 0) < 1 or inputs.base[d, IDX[b]] < 0.01 for b in BYELECTION_BLOCS):
            log(f"by-election {name}: skipped (a major party did not contest)")
            continue
        at = trend.filter((pl.col("date") <= r["date"]) & pl.col("ALP").is_not_null()).tail(1).row(0, named=True)
        moves = []
        for b in BYELECTION_BLOCS:
            local = shares[b] - 100 * inputs.base[d, IDX[b]]
            statewide = at[b] - start[b]
            excess = local - statewide
            inputs.base[d, IDX[b]] = max(0.002, inputs.base[d, IDX[b]] + BYELECTION_PERSISTENCE * excess / 100)
            moves.append(f"{b} {excess:+.1f}")
        inputs.base[d] /= inputs.base[d].sum()
        note = (f"by-election {r['date']}: swing beyond statewide polls {', '.join(moves)} pts "
                f"(half carried forward)")
        inputs.notes.setdefault(name, []).append(note)
        log(note.replace("by-election", f"by-election {name}"))


def attach_candidates(inputs: SeatInputs, election: Election, previous: Election,
                      log: Callable[[str], None] = print) -> SeatInputs:
    """Member status and ballot from the curated files, when they exist."""
    from prophecy import CURATED_DIR
    from prophecy.model.simulate import apply_candidates

    members_path = CURATED_DIR / f"members_{election.election_id}.csv"
    cands_path = CURATED_DIR / f"candidates_{election.election_id}.csv"
    members = pl.read_csv(members_path, infer_schema_length=None) if members_path.exists() else None
    cands = pl.read_csv(cands_path, infer_schema_length=None) if cands_path.exists() else None
    inputs = apply_candidates(inputs, members, cands, sophomore_since=previous.date.year)
    n_ret = int(inputs.retiring.sum()) if inputs.retiring is not None else 0
    n_soph = int(inputs.sophomore.sum()) if inputs.sophomore is not None else 0
    n_cand = cands["district"].n_unique() if cands is not None and cands.height else 0
    log(f"candidates: {n_ret} retiring, {n_soph} first-term recontesting, "
        f"ballot known for {n_cand} seats")
    return inputs


def flow_weights(previous: Election, inputs: SeatInputs,
                 log: Callable[[str], None] = print) -> np.ndarray:
    """Luce weights from the DoPs, tilted so replaying ``previous`` reproduces its seat
    2CPs, then ONP flows from polls."""
    transfers = pl.read_csv(PROCESSED / FLOW_SOURCE / "dop_transfers.csv").filter(
        pl.col("count") > 0
    ).with_columns(
        pl.col("from_party").map_elements(bloc, return_dtype=pl.String).alias("from_bloc"),
        pl.col("to_party").map_elements(bloc, return_dtype=pl.String).alias("to_bloc"),
    )
    tcp = pl.read_csv(PROCESSED / previous.election_id / "tcp.csv")
    alp_tcp = np.full(len(inputs.districts), np.nan)
    for i, name in enumerate(inputs.districts):
        t = tcp.filter(pl.col("district") == name)
        if set(t["bloc"]) == {"ALP", "COAL"}:
            alp_tcp[i] = t.filter(pl.col("bloc") == "ALP")["pct"][0]
    flows, calib = calibrate_to_results(estimate_weights(transfers), inputs.base, alp_tcp)
    log(f"flow calibration ({previous.election_id}): {calib}")
    return apply_onp_targets(flows)


def ind_fraction(inputs: SeatInputs) -> float:
    """Independents' share of Others+IND at the previous election."""
    w = inputs.weight / inputs.weight.sum()
    ind, oth = inputs.base[:, IDX["IND"]] @ w, inputs.base[:, IDX["OTH"]] @ w
    return float(ind / (ind + oth))


def add_tpp_trend(shares: np.ndarray, parties: list[str], flows: np.ndarray, trend_path: Path,
                  ind_frac: float) -> None:
    """Add model-implied ALP-v-Coalition 2PP (median, 90%) to the weekly trend file."""
    trend = pl.read_csv(trend_path, try_parse_dates=True, infer_schema_length=None)
    trend = trend.drop([c for c in trend.columns if c.startswith("tpp_alp_vs_coal")])
    n_draws = shares.shape[0]
    flows_s = np.repeat(flows[None], n_draws, axis=0)
    med, lo, hi = [], [], []
    for w in range(trend.height):
        prim = np.zeros((n_draws, len(BLOCS)))
        for k, p in enumerate(parties):
            prim[:, IDX[p]] = shares[:, w, k] / 100
        prim[:, IDX["IND"]] = prim[:, IDX["OTH"]] * ind_frac
        prim[:, IDX["OTH"]] *= 1 - ind_frac
        q = np.quantile(two_party(prim, flows_s, "ALP", "COAL"), [0.5, 0.05, 0.95])
        med.append(round(float(q[0]), 2))
        lo.append(round(float(q[1]), 2))
        hi.append(round(float(q[2]), 2))
    trend.with_columns(
        pl.Series("tpp_alp_vs_coal", med), pl.Series("tpp_alp_vs_coal_lo", lo),
        pl.Series("tpp_alp_vs_coal_hi", hi),
    ).write_csv(trend_path)


def default_config(n_per_draw: int = 5) -> SimConfig:
    """Simulation settings, with polling error calibrated from history when available."""
    cfg = SimConfig(n_per_draw=n_per_draw)
    path = PROCESSED / "poll_error_vic.json"
    if path.exists():
        err = json.loads(path.read_text(encoding="utf-8"))
        cfg.poll_error_sd.update({k: v for k, v in err["sd"].items() if k in cfg.poll_error_sd})
        cfg.poll_bias = err.get("bias", {})
    return cfg


# --------------------------------------------------------------------------------------
# Federal (House of Representatives)
# --------------------------------------------------------------------------------------

def federal_inputs(election: Election, previous: Election,
                   log: Callable[[str], None] = print) -> SeatInputs:
    """Seat inputs on ``election``'s boundaries from the AEC notional baseline.

    States act as the correlated regions; One Nation's geography is its own notional
    previous vote (it contested every seat); sitting members and the ballot come from
    the nominations (public weeks before polling day).
    """
    from prophecy.model.simulate import apply_candidates

    nd = PROCESSED / f"{election.election_id}-notional"
    primary = pl.read_csv(nd / "primary.csv")
    districts = pl.read_csv(nd / "districts.csv")
    ballot = pl.read_csv(nd / "ballot.csv")
    regions = districts.select("district", pl.col("state").alias("region"))
    onp_geo = primary.select("district", "bloc", "votes", "pct")
    inputs = build_inputs(primary, districts, onp_geo, regions)

    # Members: sitting member's party and whether they were first elected last time.
    prev_primary = pl.read_csv(PROCESSED / previous.election_id / "primary.csv")
    new_last_time = set(
        prev_primary.filter(pl.col("elected") & ~pl.col("sitting"))["candidate"].to_list())
    rows = []
    for r in districts.iter_rows(named=True):
        sit = ballot.filter((pl.col("district") == r["district"]) & pl.col("sitting"))
        if sit.height:
            m = sit.row(0, named=True)
            rows.append({"district": r["district"], "party": m["party"], "status": "recontesting",
                         "first_elected": str(previous.date.year) if m["name"] in new_last_time else "earlier"})
        else:
            rows.append({"district": r["district"], "party": r["elected_party"], "status": "retiring",
                         "first_elected": "earlier"})
    members = pl.DataFrame(rows)
    inputs = apply_candidates(inputs, members, ballot, sophomore_since=previous.date.year)
    log(f"federal inputs: {len(inputs.districts)} seats, {int(inputs.retiring.sum())} retiring, "
        f"{int(inputs.sophomore.sum())} first-term recontesting")
    return inputs


def federal_flows(previous: Election, log: Callable[[str], None] = print) -> np.ndarray:
    """Flows from the previous election's full AEC distributions, calibrated on its
    actual seat results (its own boundaries)."""
    src = PROCESSED / previous.election_id
    transfers = pl.read_csv(src / "dop_transfers.csv").with_columns(
        pl.col("from_party").map_elements(bloc, return_dtype=pl.String).alias("from_bloc"),
        pl.col("to_party").map_elements(bloc, return_dtype=pl.String).alias("to_bloc"),
    )
    primary = pl.read_csv(src / "primary.csv")
    districts = pl.read_csv(src / "districts.csv")
    names = sorted(districts["district"].to_list())
    base = np.zeros((len(names), len(BLOCS)))
    for d, b, v in primary.group_by("district", "bloc").agg(pl.col("votes").sum()).iter_rows():
        base[names.index(d), IDX[b]] += v
    base /= base.sum(axis=1, keepdims=True)
    tcp = pl.read_csv(src / "tcp.csv")
    alp_tcp = np.full(len(names), np.nan)
    for (d,), t in tcp.group_by("district"):
        if set(t["bloc"]) == {"ALP", "COAL"}:
            alp_tcp[names.index(d)] = t.filter(pl.col("bloc") == "ALP")["pct"][0]
    flows, calib = calibrate_to_results(estimate_weights(transfers), base, alp_tcp)
    log(f"flow calibration ({previous.election_id}): {calib}")
    return flows
