"""Fit the Bayesian poll aggregator (stan/poll_aggregator.stan)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import polars as pl

from prophecy.jurisdictions import Election
from prophecy.model import stan_model

PARTIES = ["ALP", "COAL", "GRN", "ONP", "OTH"]  # OTH (incl. independents) is the reference
# Prior sd of week-1 log-ratios: major parties are anchored firmly to the previous
# result; ONP (which barely contested recent Assembly elections) starts vague.
START_SD = {"ALP": 0.05, "COAL": 0.05, "GRN": 0.08, "ONP": 0.6}
MIN_PRIMARY_SUM = 90  # polls reporting undecideds inside the primaries are excluded


def modelled_parties(polls: pl.DataFrame) -> list[str]:
    """Parties to model: ONP only when some poll in the cycle reports it."""
    has_onp = "ONP" in polls.columns and polls["ONP"].drop_nulls().len() > 0
    return [p for p in PARTIES if p != "ONP" or has_onp]
DESIGN_EFFECT = 1.5  # online/panel polls are not simple random samples
MRP_DESIGN_EFFECT = 4.0  # MRP models carry larger model/post-stratification design effect
MAX_N_EFF = 2000.0  # cap single-poll effective sample size so one large MRP cannot dominate
DEFAULT_N = 1000
# Prior ALP 2PP preference flow share & Beta concentration for non-major blocs in joint 2PP likelihood.
TPP_FLOW_PRIOR = {"GRN": (0.82, 40.0), "ONP": (0.32, 10.0), "OTH": (0.48, 15.0)}


@dataclass
class AggregateFit:
    parties: list[str]
    weeks: list[date]  # week-start dates, index 0 = previous election
    shares: np.ndarray  # draws x weeks x parties (%)
    house: pl.DataFrame  # pollster x party house effects (median, 90% interval)
    params: dict[str, np.ndarray]
    diagnostics: dict
    pollsters: list[str]


def summarise(f: AggregateFit, polls: pl.DataFrame) -> pl.DataFrame:
    """Weekly posterior median and 90% interval per party.

    A party's trend is only reported from its first separately-reported poll (before
    that, e.g. One Nation inside "Others", it is weakly identified) to the latest poll.
    """
    last_poll = polls["field_end"].max()
    first_seen = {
        p: polls.filter(pl.col(p).is_not_null())["field_start"].min() for p in f.parties[:-1]
    }
    rows = []
    for w, wk in enumerate(f.weeks):
        if wk > last_poll + timedelta(days=6):
            break
        row: dict = {"date": wk}
        for k, p in enumerate(f.parties):
            visible = p == "OTH" or (first_seen[p] is not None and wk >= first_seen[p] - timedelta(days=7))
            draws = f.shares[:, w, k]
            row[p] = round(float(np.median(draws)), 2) if visible else None
            row[f"{p}_lo"] = round(float(np.quantile(draws, 0.05)), 2) if visible else None
            row[f"{p}_hi"] = round(float(np.quantile(draws, 0.95)), 2) if visible else None
        rows.append(row)
    return pl.DataFrame(rows, infer_schema_length=None)


def prepare(polls: pl.DataFrame, previous: Election, election: Election,
            start_share: dict[str, float], parties: list[str]) -> tuple[dict, list[str], list[date]]:
    """Build Stan data from the polls table (one row per poll)."""
    if "primary_sum" in polls.columns:
        polls = polls.filter(pl.col("primary_sum").is_null() | (pl.col("primary_sum") >= MIN_PRIMARY_SUM))
    n_weeks = (election.date - previous.date).days // 7 + 1
    weeks = [previous.date + timedelta(weeks=w) for w in range(n_weeks)]
    polls = polls.with_columns(
        (pl.col("field_start") + (pl.col("field_end") - pl.col("field_start")) / 2).alias("mid")
    ).filter(pl.col("mid") > previous.date)
    pollsters = sorted(polls["pollster"].unique().to_list())
    pidx = {p: i + 1 for i, p in enumerate(pollsters)}

    K = len(parties)
    K1 = K - 1
    J = len(pollsters)
    poll_w_start, poll_w_end, poll_pollster, poll_n_eff, poll_m = [], [], [], [], []
    poll_parties, poll_y = [], []
    tpp_poll, tpp_y = [], []
    reporting_by_party: list[set[int]] = [set() for _ in range(K1)]

    for r in polls.iter_rows(named=True):
        w_start = max(1, min(n_weeks, (r["field_start"] - previous.date).days // 7 + 1))
        w_end = max(w_start, min(n_weeks, (r["field_end"] - previous.date).days // 7 + 1))
        deff = MRP_DESIGN_EFFECT if "mrp" in str(r["pollster"]).lower() else DESIGN_EFFECT
        n_eff = min((r["sample_size"] or DEFAULT_N) / deff, MAX_N_EFF)
        p_idx = pidx[r["pollster"]]
        obs_k, obs_y = [], []
        # Others is the reference category and never observed directly: the K-1 other
        # shares carry all the information (and ONP is only used when reported).
        for k, party in enumerate(parties[:-1], start=1):
            if r.get(party) is not None:
                obs_k.append(k)
                obs_y.append(float(r[party]))
                reporting_by_party[k - 1].add(p_idx)
        if not obs_k:
            continue
        m = len(obs_k)
        poll_w_start.append(w_start)
        poll_w_end.append(w_end)
        poll_pollster.append(p_idx)
        poll_n_eff.append(float(n_eff))
        poll_m.append(m)
        poll_parties.append(obs_k + [0] * (K1 - m))
        poll_y.append(obs_y + [0.0] * (K1 - m))
        tpp_val = r.get("tpp_alp_vs_coal")
        if tpp_val is not None and 5.0 <= float(tpp_val) <= 95.0:
            tpp_poll.append(len(poll_w_start))
            tpp_y.append(float(tpp_val))

    house_slot = np.zeros((K1, J), dtype=int)
    for k in range(K1):
        for slot, j in enumerate(sorted(reporting_by_party[k]), start=1):
            house_slot[k, j - 1] = slot
    start = np.array([start_share[p] for p in parties], dtype=float)
    start = 100 * start / start.sum()
    tpp_flow_prior = [TPP_FLOW_PRIOR.get(p, (0.50, 10.0))[0] for p in parties[2:]]
    tpp_flow_conc = [TPP_FLOW_PRIOR.get(p, (0.50, 10.0))[1] for p in parties[2:]]
    data = {
        "K": K, "T": n_weeks, "J": J, "M": len(poll_w_start),
        "poll_w_start": poll_w_start, "poll_w_end": poll_w_end,
        "poll_pollster": poll_pollster, "poll_n_eff": poll_n_eff,
        "poll_m": poll_m, "poll_parties": poll_parties, "poll_y": poll_y,
        "M_tpp": len(tpp_poll), "tpp_poll": tpp_poll, "tpp_y": tpp_y,
        "tpp_flow_prior": tpp_flow_prior, "tpp_flow_conc": tpp_flow_conc,
        "start_share": start.tolist(),
        "start_sd": [START_SD[p] for p in parties[:-1]],
        "J_k": (house_slot > 0).sum(axis=1).tolist(),
        "house_slot": house_slot.tolist(),
    }
    return data, pollsters, weeks


def inits(data: dict, model_name: str, chains: int, seed: int) -> list[dict]:
    """Starting values, jittered per chain. Stan's default (uniform on (-2, 2) for
    unconstrained parameters) can start sigma_vel near 7 log-ratio/week; integrated over
    a ~200-week cycle the trend overflows the softmax, and warmup spends a long time
    recovering. These start the trend near flat and the error scales near typical."""
    rng = np.random.default_rng(seed)
    K1, T = data["K"] - 1, data["T"]
    h_free = sum(max(int(jk) - 1, 0) for jk in data["J_k"])
    corr = model_name == "poll_aggregator_corr"
    flow_prior = np.asarray(data["tpp_flow_prior"], dtype=float)
    out = []
    for _ in range(chains):
        init = {
            "eta0_raw": rng.normal(0, 0.5, K1),
            "z": rng.normal(0, 0.2, (K1, T - 1) if corr else (T - 1, K1)),
            "sigma_vel": rng.uniform(0.002, 0.01, K1),
            "phi": rng.uniform(0.6, 0.9),
            "tau": rng.uniform(0.5, 2.0, K1),
            "sigma_house": rng.uniform(0.03, 0.12, K1),
            "house_free": rng.normal(0, 0.5, h_free),
            "flow_alp": np.clip(flow_prior + rng.normal(0, 0.03, len(flow_prior)), 0.05, 0.95),
            "tau_tpp": float(rng.uniform(0.5, 1.5)),
        }
        if corr:
            init |= {"L_vel": np.eye(K1), "sigma_drift": rng.uniform(0.01, 0.06, K1),
                     "drift_free": rng.normal(0, 0.5, h_free)}
        out.append({k: np.asarray(v).tolist() for k, v in init.items()})
    return out


def fit(polls: pl.DataFrame, previous: Election, election: Election,
        start_share: dict[str, float], seed: int = 20261128,
        model_name: str = "poll_aggregator", auto_retry: bool = True, **sample_kw) -> AggregateFit:
    """``model_name``: ``poll_aggregator`` (independent party trends, fixed house
    effects) or ``poll_aggregator_corr`` (correlated trends, drifting house effects)."""
    parties = modelled_parties(polls)
    data, pollsters, weeks = prepare(polls, previous, election, start_share, parties)
    model = stan_model(model_name)
    # With the inits, 500 warmup iterations adapt well on most cycles; if convergence
    # diagnostics fail (R-hat > 1.01 or divergences), retry once with longer warmup.
    kw = {"chains": 4, "parallel_chains": 4, "iter_warmup": 500, "iter_sampling": 1000,
              "adapt_delta": 0.99, "max_treedepth": 12, "show_progress": False}
    kw.update(sample_kw)
    kw.setdefault("inits", inits(data, model_name, kw["chains"], seed))
    mcmc = model.sample(data=data, seed=seed, **kw)
    summary = mcmc.summary()
    divergences = int(np.sum(mcmc.method_variables()["divergent__"]))
    if auto_retry and (float(summary["R_hat"].max()) > 1.01 or divergences > 0):
        retry_kw = {**kw, "iter_warmup": max(kw["iter_warmup"] * 2, 1000),
                    "adapt_delta": max(kw["adapt_delta"], 0.995)}
        retry_kw["inits"] = inits(data, model_name, retry_kw["chains"], seed + 17)
        mcmc = model.sample(data=data, seed=seed + 17, **retry_kw)
        summary = mcmc.summary()
        divergences = int(np.sum(mcmc.method_variables()["divergent__"]))

    draws = mcmc.stan_variables()
    shares = draws["share"]  # draws x T x K
    house = draws["house"]  # draws x (K-1) x J
    rows = []
    for k, party in enumerate(parties[:-1]):
        for j, name in enumerate(pollsters):
            if data["house_slot"][k][j] == 0:
                continue
            h = house[:, k, j]
            rows.append({"pollster": name, "party": party, "median": float(np.median(h)),
                         "lo": float(np.quantile(h, 0.05)), "hi": float(np.quantile(h, 0.95))})

    diag = mcmc.diagnose()
    diagnostics = {
        "max_rhat": float(summary["R_hat"].max()),
        "min_ess_bulk": float(summary["ESS_bulk"].min()),
        "divergences": divergences,
        "report": diag,
    }
    return AggregateFit(
        parties=parties, weeks=weeks, shares=shares, house=pl.DataFrame(rows),
        params={k: draws[k] for k in ("sigma_vel", "phi", "tau", "sigma_house", "sigma_drift",
                                      "Omega_vel", "flow_alp", "tau_tpp")
                if k in draws},
        diagnostics=diagnostics, pollsters=pollsters,
    )
