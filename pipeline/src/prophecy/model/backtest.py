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
        row["tpp_error"] = (round(tpp - r["tpp_alp_vs_coal"], 2)
                            if tpp is not None and r["tpp_alp_vs_coal"] is not None else None)
        rows.append(row)
    return pl.DataFrame(rows)


def _errors(table: pl.DataFrame, party: str) -> np.ndarray:
    """A party's final-poll errors; none when no election had polls in its final weeks."""
    col = f"{party}_error"
    return table[col].drop_nulls().to_numpy() if col in table.columns else np.array([])


def error_sd(table: pl.DataFrame, floor: dict[str, float]) -> dict[str, float]:
    """Root-mean-square historical error per party, never below ``floor``.

    With a handful of elections the RMS is noisy, so the floor (a prior judgement)
    guards against an unusually accurate run of elections shrinking the uncertainty.
    """
    out = {}
    for p in ERROR_PARTIES:
        e = _errors(table, p)
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
        e = _errors(table, p)
        out[p] = round(float(np.mean(e)) * BIAS_SHRINKAGE, 2) if len(e) else 0.0
    return out


POOL_JURISDICTIONS = ("VIC", "NSW", "QLD", "SA", "WA", "TAS", "ACT", "NT", "FED")
SHRINK_ELECTIONS = 4.0  # pseudo-elections pulling a jurisdiction toward the pooled error
MIN_ERROR_SD = 1.0  # points: a guard, well below the pooled estimates


def pooled_poll_error(before, jurisdiction: str, processed) -> dict:
    """Polling error for ``jurisdiction`` from every jurisdiction's elections before
    ``before``: the pooled root-mean-square error and mean (bias) per party, each
    jurisdiction's own values shrunk toward them (``SHRINK_ELECTIONS`` pseudo-
    elections), and the pooled correlation between parties' errors."""
    tables = []
    for j in POOL_JURISDICTIONS:
        code = j.lower()
        polls_path = processed / f"polls_{code}_all.csv"
        res_path = processed / f"election_results_{code}.csv"
        if not (polls_path.exists() and res_path.exists()):
            continue
        res = pl.read_csv(res_path, try_parse_dates=True).filter(pl.col("date") < before)
        t = poll_error_table(pl.read_csv(polls_path, try_parse_dates=True, infer_schema_length=None), res)
        if t.height:
            tables.append(t.select("year", *[f"{p}_error" for p in ERROR_PARTIES])
                          .with_columns(pl.lit(j).alias("jurisdiction")))
    table = pl.concat(tables, how="diagonal_relaxed")
    sd, bias = {}, {}
    k = SHRINK_ELECTIONS
    for p in ERROR_PARTIES:
        e = table[f"{p}_error"].drop_nulls().to_numpy()
        own = table.filter(pl.col("jurisdiction") == jurisdiction)[f"{p}_error"].drop_nulls().to_numpy()
        ms_g, mean_g = float(np.mean(e ** 2)), float(np.mean(e))
        n = len(own)
        ms = (n * float(np.mean(own ** 2)) + k * ms_g) / (n + k) if n else ms_g
        # The pooled mean is itself shrunk toward zero by the same pseudo-count.
        mean_g = mean_g * len(e) / (len(e) + k)
        mu = (n * float(np.mean(own)) + k * mean_g) / (n + k) if n else mean_g
        sd[p] = round(max(float(np.sqrt(ms)), MIN_ERROR_SD), 2)
        bias[p] = round(mu, 2)
    full = table.drop_nulls([f"{p}_error" for p in ERROR_PARTIES]).select(
        [f"{p}_error" for p in ERROR_PARTIES]).to_numpy()
    corr = np.corrcoef(full.T) if len(full) >= 5 else np.eye(len(ERROR_PARTIES))
    return {"sd": sd, "bias": bias, "corr": np.round(corr, 3).tolist(), "parties": list(ERROR_PARTIES),
            "n_elections": int(table.height), "n_own": int(table.filter(pl.col("jurisdiction") == jurisdiction).height)}


def crps(draws: np.ndarray, y: float) -> float:
    """Continuous ranked probability score of an ensemble (same units as ``y``)."""
    x = np.sort(draws)
    n = len(x)
    # E|X - y| - E|X - X'| / 2, the latter from the sorted sample in O(n).
    return float(np.mean(np.abs(x - y)) - np.sum((2 * np.arange(1, n + 1) - n - 1) * x) / n ** 2)


def seat_vote_scores(res: SimResult, actual_primary: pl.DataFrame,
                     parties: tuple[str, ...] = ("ALP", "COAL", "GRN")) -> dict:
    """Score the simulated seat primaries against the actual ones (percent).

    ``actual_primary``: district, bloc, pct. Reports per party the mean CRPS, the
    coverage of the 50% and 90% intervals and a ten-bin PIT histogram (flat when the
    seat-level uncertainty is right; U-shaped when overconfident)."""
    from prophecy.model.preferences import IDX

    act = {(d, b): v for d, b, v in actual_primary.select("district", "bloc", "pct").iter_rows()}
    out = {}
    for p in parties:
        k = IDX[p]
        scores, pits = [], []
        for i, d in enumerate(res.inputs.districts):
            y = act.get((d, p))
            sims = res.seat_primary[:, i, k] * 100
            if y is None or y < 0.5 or np.median(sims) < 0.5:
                continue  # not contested at one end
            scores.append(crps(sims, y))
            pits.append(float(np.mean(sims < y)))
        if not scores:
            continue
        pits = np.array(pits)
        out[p] = {"n": len(scores), "crps": round(float(np.mean(scores)), 3),
                  "cover50": round(float(np.mean((pits > 0.25) & (pits < 0.75))), 3),
                  "cover90": round(float(np.mean((pits > 0.05) & (pits < 0.95))), 3),
                  "pit_hist": np.histogram(pits, bins=10, range=(0, 1))[0].tolist()}
    return out


def pendulum_accuracy(base_tpp: dict[str, float], tpp_swing: float, actual: dict[str, str],
                      incumbents: dict[str, str]) -> float:
    """Mackerras pendulum baseline: each Labor v Coalition seat's previous 2PP moved by
    the forecast statewide 2PP swing decides it; other seats stay with their holder."""
    hits = 0
    for d, won in actual.items():
        t = base_tpp.get(d)
        inc = incumbents.get(d)
        if t is None or _two_party_bloc(inc) is None:
            pick = inc
        elif t + tpp_swing > 50:
            pick = "ALP"
        else:
            pick = inc if _two_party_bloc(inc) == "COAL" else "COAL"
        hits += pick == won or (pick == "COAL" and won in ("LIB", "NAT", "LNP", "CLP", "COAL"))
    return round(hits / len(actual), 4)


def _two_party_bloc(party: str | None) -> str | None:
    if party == "ALP":
        return "ALP"
    if party in ("LIB", "NAT", "LNP", "CLP", "COAL"):
        return "COAL"
    return None


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
