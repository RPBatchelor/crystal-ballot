"""Publish poll data as JSON for the website."""

from __future__ import annotations

import json
from datetime import UTC, datetime

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
        "events": _records(events.select("event_date", "description")) if events is not None else [],
    }
    out = WEB_DATA_DIR / election.jurisdiction.lower() / str(election.date.year) / "polls.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return str(out)


def _records(df: pl.DataFrame) -> list[dict]:
    return [
        {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}
        for row in df.iter_rows(named=True)
    ]
