"""Publish the seat forecast as JSON for the website."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from prophecy import DATA_DIR, WEB_DATA_DIR
from prophecy.jurisdictions import Election, site_code
from prophecy.publish.results import slugify

MODEL_VERSION = "0.1.0"


def publish_forecast(election: Election, validated: bool = False) -> str | None:
    src = DATA_DIR / "processed" / election.election_id
    summary_path = src / "forecast_summary.json"
    if not summary_path.exists():
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    meta_path = src / "aggregate_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    for d in summary["districts"]:
        d["slug"] = slugify(d["district"])
        d["leader"], d["leader_prob"] = max(d["probs"].items(), key=lambda kv: kv[1])

    payload = {
        "election_id": election.election_id,
        "jurisdiction": election.jurisdiction,
        "election_date": election.date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model_version": MODEL_VERSION,
        # False until the model passes its historical backtest; the site labels the
        # forecast as a development preview while this is False.
        "validated": validated,
        "diagnostics": meta.get("diagnostics", {}),
        **summary,
    }
    out = WEB_DATA_DIR / site_code(election.jurisdiction) / "forecast" / f"{election.date.year}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return str(out)
