"""Publish poll data as JSON for the website."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

from prophecy import DATA_DIR, WEB_DATA_DIR, jurisdictions
from prophecy.jurisdictions import Election

POLL_FIELDS = [
    "pollster", "client", "field_start", "field_end", "sample_size",
    "ALP", "COAL", "GRN", "ONP", "IND", "OTH", "tpp_alp_vs_coal", "tpp_alp_vs_onp",
]


def publish_polls(election: Election) -> str:
    """Every cycle's polls for the jurisdiction, with trends, events and results.

    The current cycle's trend is the Bayesian aggregate (with 90% bands); earlier cycles
    use a simple kernel average. A null row separates cycles so lines break at elections.
    """
    processed = DATA_DIR / "processed"
    code = election.jurisdiction.lower()
    cycles = [e for e in jurisdictions.in_jurisdiction(election.jurisdiction)
              if (processed / f"polls_{e.election_id}.csv").exists() and e.date <= election.date]

    all_polls, trend, events = [], [], []
    for e in cycles:
        polls = pl.read_csv(processed / f"polls_{e.election_id}.csv", try_parse_dates=True,
                            infer_schema_length=None)
        all_polls.append(polls.select(POLL_FIELDS).with_columns(pl.lit(e.election_id).alias("cycle")))
        model_trend = processed / e.election_id / "poll_trend.csv"
        if e.election_id == election.election_id and model_trend.exists():
            rows = _records(pl.read_csv(model_trend, try_parse_dates=True, infer_schema_length=None))
        else:
            rows = kernel_trend(polls)
        if trend:
            trend.append({"date": rows[0]["date"]})  # break the line at the election
        trend.extend(rows)
        ev_path = processed / f"events_{e.election_id}.csv"
        if ev_path.exists():
            ev = pl.read_csv(ev_path, try_parse_dates=True)
            events.extend(_records(ev.select("event_date", "description")))

    results_path = processed / f"election_results_{code}.csv"
    results = (_records(pl.read_csv(results_path, try_parse_dates=True)) if results_path.exists()
               else [])
    house_path = processed / election.election_id / "house_effects.csv"
    method = (
        "Current cycle: Bayesian poll aggregate (a smooth, damped trend from the previous result, "
        "adjusting for each pollster's house effect and sample size; bands are 90% credible "
        "intervals; 2PP implied from primaries via estimated preference flows). Earlier cycles: "
        f"simple {BANDWIDTH_DAYS}-day kernel average of published polls."
    )
    payload = {
        "election_id": election.election_id,
        "jurisdiction": election.jurisdiction,
        "election_date": election.date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "cycles": [{"election_id": e.election_id, "date": e.date.isoformat()} for e in cycles],
        "polls": _records(pl.concat(all_polls, how="diagonal_relaxed").sort("field_end", descending=True)),
        "trend": trend,
        "trend_method": method,
        "results": results,
        "house_effects": _records(pl.read_csv(house_path)) if house_path.exists() else [],
        "events": sorted(events, key=lambda r: str(r["event_date"])),
    }
    out = WEB_DATA_DIR / election.jurisdiction.lower() / "polls.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return str(out)


BANDWIDTH_DAYS = 60  # comparable to Wikipedia's LOESS smoothing of poll charts
TREND_SERIES = ["ALP", "COAL", "GRN", "ONP", "tpp_alp_vs_coal"]
MIN_WEIGHT = 0.5  # don't extend a series into periods with (almost) no polls


def kernel_trend(polls: pl.DataFrame, step_days: int = 7) -> list[dict]:
    """Simple smoothed poll average on a weekly grid, ending at the latest poll."""
    mid = polls.select(
        (pl.col("field_start") + (pl.col("field_end") - pl.col("field_start")) / 2).alias("mid"),
        pl.col("sample_size").fill_null(1000).sqrt().alias("w"),
        *TREND_SERIES,
    )
    days = (mid["mid"] - mid["mid"].min()).dt.total_days().to_numpy()
    start, end = mid["mid"].min(), mid["mid"].max()
    out = []
    grid = list(range(0, int(days.max()) + 1, step_days))
    if grid[-1] != int(days.max()):
        grid.append(int(days.max()))
    for g in grid:
        k = np.exp(-0.5 * ((days - g) / BANDWIDTH_DAYS) ** 2) * mid["w"].to_numpy() / 30
        row: dict = {"date": (start + timedelta(days=g)).isoformat()}
        for s in TREND_SERIES:
            v = mid[s].to_numpy(allow_copy=True).astype(float)
            ok = ~np.isnan(v)
            wsum = k[ok].sum()
            row[s] = round(float((k[ok] * v[ok]).sum() / wsum), 2) if wsum >= MIN_WEIGHT else None
        out.append(row)
    assert out[-1]["date"] == end.isoformat()
    return out


def _records(df: pl.DataFrame) -> list[dict]:
    return [
        {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}
        for row in df.iter_rows(named=True)
    ]
