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
DEFAULT_N = 1000


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

    rows = []
    for r in polls.iter_rows(named=True):
        w = min(n_weeks, (r["mid"] - previous.date).days // 7 + 1)
        n_eff = (r["sample_size"] or DEFAULT_N) / DESIGN_EFFECT
        # Others is the reference category and never observed directly: the K-1 other
        # shares carry all the information (and ONP is only used when reported).
        for k, party in enumerate(parties[:-1], start=1):
            if r.get(party) is not None:
                rows.append((w, pidx[r["pollster"]], k, float(r[party]), n_eff))
    week, pollster, party, y, n_eff = map(list, zip(*rows))

    K = len(parties)
    J = len(pollsters)
    house_slot = np.zeros((K - 1, J), dtype=int)
    for k in range(K - 1):
        reporting = sorted({p for p, kk in zip(pollster, party) if kk == k + 1})
        for slot, j in enumerate(reporting, start=1):
            house_slot[k, j - 1] = slot
    start = np.array([start_share[p] for p in parties], dtype=float)
    start = 100 * start / start.sum()
    data = {
        "K": K, "T": n_weeks, "J": J, "N": len(y),
        "week": week, "pollster": pollster, "party": party, "y": y, "n_eff": n_eff,
        "start_share": start.tolist(),
        "start_sd": [START_SD[p] for p in parties[:-1]],
        "J_k": (house_slot > 0).sum(axis=1).tolist(),
        "house_slot": house_slot.tolist(),
    }
    return data, pollsters, weeks


def fit(polls: pl.DataFrame, previous: Election, election: Election,
        start_share: dict[str, float], seed: int = 20261128, **sample_kw) -> AggregateFit:
    parties = modelled_parties(polls)
    data, pollsters, weeks = prepare(polls, previous, election, start_share, parties)
    model = stan_model("poll_aggregator")
    kw = {"chains": 4, "parallel_chains": 4, "iter_warmup": 1000, "iter_sampling": 1000,
              "adapt_delta": 0.95, "max_treedepth": 12, "show_progress": False}
    kw.update(sample_kw)
    mcmc = model.sample(data=data, seed=seed, **kw)

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

    summary = mcmc.summary()
    diag = mcmc.diagnose()
    diagnostics = {
        "max_rhat": float(summary["R_hat"].max()),
        "min_ess_bulk": float(summary["ESS_bulk"].min()),
        "divergences": int(np.sum(mcmc.method_variables()["divergent__"])),
        "report": diag,
    }
    return AggregateFit(
        parties=parties, weeks=weeks, shares=shares, house=pl.DataFrame(rows),
        params={k: draws[k] for k in ("sigma_walk", "tau", "sigma_house")},
        diagnostics=diagnostics, pollsters=pollsters,
    )
