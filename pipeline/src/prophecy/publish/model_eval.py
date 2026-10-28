"""Publish model-evaluation data (backtests, historical polling error) for the website."""

from __future__ import annotations

import json

import polars as pl

from prophecy import DATA_DIR, WEB_DATA_DIR

PROCESSED = DATA_DIR / "processed"


def publish_model_eval(jurisdiction: str) -> str | None:
    code = jurisdiction.lower()
    payload: dict = {"backtests": [], "poll_error": [], "poll_error_settings": None}
    for path in sorted(PROCESSED.glob(f"backtest-{code}-*/backtest_metrics.json")):
        metrics = json.loads(path.read_text(encoding="utf-8"))
        payload["backtests"].append({"election_id": path.parent.name.removeprefix("backtest-"),
                                     **metrics})
    table = PROCESSED / f"poll_error_{code}.csv"
    if table.exists():
        payload["poll_error"] = pl.read_csv(table).to_dicts()
    settings = PROCESSED / f"poll_error_{code}.json"
    if settings.exists():
        payload["poll_error_settings"] = json.loads(settings.read_text(encoding="utf-8"))
    if not payload["backtests"] and not payload["poll_error"]:
        return None
    out = WEB_DATA_DIR / code / "model.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return str(out)
