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


COAL_CODES = {"LIB", "NAT", "LNP", "CLP", "COAL"}


def publish_retrospective(election: Election) -> str | None:
    """A blind backtest published as the forecast the model would have shown on the eve
    of the election, together with what actually happened.

    Federal backtests use a notional baseline without a Liberal/National split, so the
    Coalition is shown as one party there (forecast and actual alike).
    """
    import polars as pl

    processed = DATA_DIR / "processed"
    src = processed / f"backtest-{election.election_id}"
    if not (src / "forecast_summary.json").exists():
        return None
    summary = json.loads((src / "forecast_summary.json").read_text(encoding="utf-8"))
    metrics = json.loads((src / "backtest_metrics.json").read_text(encoding="utf-8"))
    meta_path = src / "aggregate_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    merge_coal = election.jurisdiction == "FED"

    def label(code: str) -> str:
        from prophecy.schema.parties import bloc

        if merge_coal:
            return "COAL" if code in COAL_CODES else bloc(code)
        return code if code in COAL_CODES or bloc(code) != "OTH" else "OTH"

    # Actual per-seat winners and first preferences (by bloc).
    actual_dir = processed / election.election_id
    districts = pl.read_csv(actual_dir / "districts.csv")
    winners = {d: label(p) for d, p in districts.select("district", "elected_party").iter_rows()}
    prim = (pl.read_csv(actual_dir / "primary.csv").group_by("district", "bloc")
            .agg(pl.col("pct").sum()))
    actual_primary: dict[str, dict[str, float]] = {}
    for d, b, v in prim.iter_rows():
        actual_primary.setdefault(d, {})[b] = round(v, 1)

    for d in summary["districts"]:
        if merge_coal:
            probs: dict[str, float] = {}
            for p, v in d["probs"].items():
                key = label(p)
                probs[key] = round(probs.get(key, 0) + v, 4)
            d["probs"] = probs
            d["incumbent"] = label(d["incumbent"])
        d["slug"] = slugify(d["district"])
        d["leader"], d["leader_prob"] = max(d["probs"].items(), key=lambda kv: kv[1])
        d["actual_winner"] = winners.get(d["district"])
        d["actual_primary"] = actual_primary.get(d["district"], {})
        d["p_actual"] = round(d["probs"].get(d["actual_winner"], 0.0), 4)
    if merge_coal:
        summary["seats"] = {k: v for k, v in summary["seats"].items() if k not in ("LIB", "NAT")}

    code = election.jurisdiction.lower()
    res = pl.read_csv(processed / f"election_results_{code}.csv").filter(
        pl.col("year") == election.date.year).row(0, named=True)
    seat_counts: dict[str, int] = {}
    for w in winners.values():
        seat_counts[w] = seat_counts.get(w, 0) + 1

    payload = {
        "election_id": election.election_id,
        "jurisdiction": election.jurisdiction,
        "election_date": election.date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model_version": MODEL_VERSION,
        "mode": "retrospective",
        "validated": True,
        "diagnostics": meta.get("diagnostics", {}),
        **summary,
        "actual": {
            "seat_counts": seat_counts,
            "primary": {p: res.get(p) for p in ("ALP", "COAL", "GRN", "ONP")},
            "tpp_alp": res.get("tpp_alp_vs_coal"),
        },
        "scores": {k: metrics[k] for k in ("brier", "log_loss", "favourite_accuracy",
                                           "status_quo_accuracy", "calibration", "seats")},
    }
    out = WEB_DATA_DIR / site_code(election.jurisdiction) / "forecast" / f"{election.date.year}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return str(out)
