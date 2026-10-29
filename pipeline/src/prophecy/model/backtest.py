"""Historical evaluation: polling error by election, and seat-forecast scoring."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import polars as pl

from prophecy.model.simulate import SimResult, seat_labels

FINAL_WINDOW_DAYS = 28
ERROR_PARTIES = ["ALP", "COAL", "GRN"]


def poll_error_table(polls: pl.DataFrame, results: pl.DataFrame) -> pl.DataFrame:
    """Final-month simple poll average minus the actual result, per election.

    Uses each cycle's polls with fieldwork ending in the last ``FINAL_WINDOW_DAYS``
    before polling day (all pollsters weighted equally).
    """
    rows = []
    for r in results.iter_rows(named=True):
        lo = r["date"] - timedelta(days=FINAL_WINDOW_DAYS)
        final = polls.filter((pl.col("field_end") >= lo) & (pl.col("field_end") <= r["date"]))
        if final.height == 0:
            continue
        row = {"year": r["year"], "n_polls": final.height,
               "pollsters": ", ".join(sorted(final["pollster"].unique().to_list()))}
        for p in ERROR_PARTIES:
            avg = final[p].drop_nulls().mean()
            row[f"{p}_poll"] = round(avg, 2) if avg is not None else None
            row[f"{p}_result"] = r[p]
            row[f"{p}_error"] = round(avg - r[p], 2) if avg is not None and r[p] is not None else None
        tpp = final["tpp_alp_vs_coal"].drop_nulls().mean()
        row["tpp_poll"] = round(tpp, 2) if tpp is not None else None
        row["tpp_result"] = r["tpp_alp_vs_coal"]
        row["tpp_error"] = round(tpp - r["tpp_alp_vs_coal"], 2) if tpp is not None else None
        rows.append(row)
    return pl.DataFrame(rows)


def error_sd(table: pl.DataFrame, floor: dict[str, float]) -> dict[str, float]:
    """Root-mean-square historical error per party, never below ``floor``.

    With a handful of elections the RMS is noisy, so the floor (a prior judgement)
    guards against an unusually accurate run of elections shrinking the uncertainty.
    """
    out = {}
    for p in ERROR_PARTIES:
        e = table[f"{p}_error"].drop_nulls().to_numpy()
        rms = float(np.sqrt(np.mean(e**2))) if len(e) else 0.0
        out[p] = round(max(rms, floor.get(p, 0.0)), 2)
    return out


BIAS_SHRINKAGE = 0.5  # apply half the historical mean error: few elections, noisy mean


def error_bias(table: pl.DataFrame) -> dict[str, float]:
    """Shrunk mean historical error per party (polls minus result).

    Subtracting this from the poll average corrects persistent leans, e.g. polls
    overstating the Greens at most Victorian elections.
    """
    out = {}
    for p in ERROR_PARTIES:
        e = table[f"{p}_error"].drop_nulls().to_numpy()
        out[p] = round(float(np.mean(e)) * BIAS_SHRINKAGE, 2) if len(e) else 0.0
    return out


def score(res: SimResult, actual: dict[str, str], incumbents: dict[str, str]) -> dict:
    """Score seat probabilities against actual winners (party codes, LIB/NAT split)."""
    labels = seat_labels(res)
    names = res.inputs.districts
    parties = sorted(set(np.unique(labels)) | set(actual.values()))
    brier, logloss, fav_hits, sq_hits = [], [], 0, 0
    calib = []
    per_seat = []
    for d, name in enumerate(names):
        probs = {p: float(np.mean(labels[:, d] == p)) for p in parties}
        won = actual[name]
        brier.append(sum((probs[p] - (p == won)) ** 2 for p in parties))
        logloss.append(-np.log(max(probs[won], 1e-3)))
        fav = max(probs, key=probs.get)
        fav_hits += fav == won
        sq_hits += incumbents.get(name) == won
        calib.append((probs[fav], fav == won))
        per_seat.append({"district": name, "won": won, "favourite": fav,
                         "p_fav": round(probs[fav], 3), "p_won": round(probs[won], 3),
                         "incumbent": incumbents.get(name)})

    seats = {p: (labels == p).sum(axis=1) for p in ["ALP", "LIB", "NAT", "GRN", "IND", "OTH"]}
    coal_labels = ["LIB", "NAT", "LNP", "CLP", "COAL"]
    seats["COAL"] = np.isin(labels, coal_labels).sum(axis=1)
    actual_seats = {p: sum(1 for v in actual.values() if v == p) for p in seats}
    actual_seats["COAL"] = sum(1 for v in actual.values() if v in coal_labels)
    seat_check = {
        p: {"actual": actual_seats[p],
            "median": float(np.median(seats[p])),
            "p90": [float(x) for x in np.quantile(seats[p], [0.05, 0.95])],
            "covered_90": bool(np.quantile(seats[p], 0.05) <= actual_seats[p] <= np.quantile(seats[p], 0.95))}
        for p in ["ALP", "COAL", "GRN", "IND"]
    }

    bins = [(0.5, 0.7), (0.7, 0.9), (0.9, 0.99), (0.99, 1.01)]
    calibration = []
    for lo, hi in bins:
        sel = [hit for p, hit in calib if lo <= p < hi]
        ps = [p for p, _ in calib if lo <= p < hi]
        if sel:
            calibration.append({"bin": f"{lo:.2f}-{min(hi, 1):.2f}", "n": len(sel),
                                "mean_prob": round(float(np.mean(ps)), 3),
                                "hit_rate": round(float(np.mean(sel)), 3)})
    return {
        "n_seats": len(names),
        "brier": round(float(np.mean(brier)), 4),
        "log_loss": round(float(np.mean(logloss)), 4),
        "favourite_accuracy": round(fav_hits / len(names), 4),
        "status_quo_accuracy": round(sq_hits / len(names), 4),
        "seats": seat_check,
        "calibration": calibration,
        "misses": [s for s in per_seat if s["favourite"] != s["won"]],
    }
