"""Publish poll data as JSON for the website."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

from prophecy import DATA_DIR, WEB_DATA_DIR
from prophecy.jurisdictions import Election

POLL_FIELDS = [
    "pollster", "client", "field_start", "field_end", "sample_size",
    "ALP", "COAL", "GRN", "ONP", "IND", "OTH", "tpp_alp_vs_coal", "tpp_alp_vs_onp",
]


def publish_polls(election: Election) -> str:
    processed = DATA_DIR / "processed"
    polls = pl.read_csv(processed / f"polls_{election.election_id}.csv", try_parse_dates=True)
    events_path = processed / f"events_{election.election_id}.csv"
    events = pl.read_csv(events_path, try_parse_dates=True) if events_path.exists() else None

    payload = {
        "election_id": election.election_id,
        "jurisdiction": election.jurisdiction,
        "election_date": election.date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "polls": _records(polls.select(POLL_FIELDS).sort("field_end", descending=True)),
        "trend": kernel_trend(polls),
        "trend_method": f"Gaussian kernel average, {BANDWIDTH_DAYS}-day bandwidth, weighted by "
        "sqrt(sample size). Placeholder until the Bayesian aggregate.",
        "events": _records(events.select("event_date", "description")) if events is not None else [],
    }
    out = WEB_DATA_DIR / election.jurisdiction.lower() / "polls.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return str(out)


BANDWIDTH_DAYS = 30
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
