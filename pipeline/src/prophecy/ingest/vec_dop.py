"""Ingest VEC indicative full distributions of preferences (DoP).

Each spreadsheet has a candidate-name row, a first-preference row, then alternating
"Transfer of N ballot papers ..." and "Progressive Total" rows. Victoria uses full
compulsory preferential voting for the Assembly, so every excluded candidate's ballots
transfer in full to the remaining candidates (no exhaustion).

Output is one row per (district, count, from candidate, to candidate): the raw material
for estimating party-to-party preference flows conditional on who is still in the count.
"""

from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import polars as pl
import xlrd

from prophecy import RAW_DIR
from prophecy.ingest.vec import _cached_get, _client, _norm, _ResultsPageParser, canonical_district

DOP_INDEX = "/results/electoral-statistics/state-election-statistics/full-preference-distributions"


def _rows(path: Path) -> list[list[str]]:
    """Spreadsheet as a list of string rows, for both .xls and .xlsx."""
    if path.suffix.lower() == ".xls":
        sheet = xlrd.open_workbook(path).sheet_by_index(0)
        raw = [sheet.row_values(r) for r in range(sheet.nrows)]
    else:
        ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        raw = [list(r) for r in ws.iter_rows(values_only=True)]
    return [["" if v is None else _norm(str(v)) for v in row] for row in raw]


def _num(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def parse_dop(path: Path, district: str) -> pl.DataFrame:
    rows = _rows(path)
    name_idx = next(i for i, r in enumerate(rows) if r and r[0].lower().startswith("candidates names"))
    names = rows[name_idx]
    # Candidate columns: non-empty header cells between the label and TOTAL.
    cols = {j: re.sub(r"\s*,\s*", ", ", names[j]) for j in range(1, len(names))
            if names[j] and names[j].upper() != "TOTAL"}

    def totals(row: list[str]) -> dict[int, float]:
        return {j: _num(row[j]) for j in cols if j < len(row) and _num(row[j])}

    body = rows[name_idx + 1 :]
    out = []
    count = 0
    current: dict[int, float] = {}
    for i, r in enumerate(body):
        label = r[0].lower() if r else ""
        if label.startswith("total first preference"):
            current = totals(r)
            for j, v in current.items():
                out.append((0, None, cols[j], v))
        elif label.startswith("transfer of"):
            count += 1
            # Zero receipts are blank too, so identify the excluded candidate as the one
            # whose running total equals the transfer size and who drops out of the next
            # progressive total.
            n = _num(re.search(r"transfer of ([\d,]+)", label).group(1))
            after = next(
                (totals(x) for x in body[i + 1 :] if x and re.match(r"(progressive|final) total", x[0].lower())),
                {},
            )
            excluded = [j for j, v in current.items() if j not in after and abs(v - n) < 0.5]
            if len(excluded) != 1:
                raise ValueError(f"{district}: cannot identify excluded candidate at count {count}")
            src = excluded[0]
            for j in after:
                v = _num(r[j]) if j < len(r) else None
                out.append((count, cols[src], cols[j], v or 0.0))
        elif label.startswith(("progressive total", "final total")):
            current = totals(r)
    return pl.DataFrame(
        out, schema={"count": pl.Int64, "from_candidate": pl.String, "to_candidate": pl.String,
                     "votes": pl.Float64},
        orient="row",
    ).with_columns(pl.lit(district).alias("district"))


def ingest_dop(year: int = 2022) -> pl.DataFrame:
    raw = RAW_DIR / "vec" / str(year) / "dop"
    with _client() as client:
        index = _cached_get(client, DOP_INDEX, raw / "index.html").read_text(encoding="utf-8")
        p = _ResultsPageParser()
        p.feed(index)
        links = [
            (href, text) for s in p.sections for href, text in s.links
            if href and re.search(r"\.xlsx?$", href, re.IGNORECASE)
        ]
        frames = []
        for href, text in links:
            if "by-election" in text.lower():
                continue  # by-election DoPs belong to a different contest
            district = canonical_district(re.sub(r"\s*(District)?\s*-.*$|\s*District.*$", "", text).strip())
            ext = Path(href).suffix.lower()
            path = _cached_get(client, href, raw / f"{district.lower().replace(' ', '-')}{ext}", binary=True)
            frames.append(parse_dop(path, district))
    return pl.concat(frames).with_columns(pl.lit(f"vic-{year}").alias("election_id"))


def attach_parties(transfers: pl.DataFrame, primary: pl.DataFrame) -> pl.DataFrame:
    """Add from/to party codes by matching candidate names within each district."""
    key = lambda c: pl.col(c).str.to_uppercase().str.replace_all(r"[^A-Z]", "")
    lookup = primary.select("district", key("candidate").alias("k"), "party")
    out = transfers
    for side in ("from", "to"):
        out = (
            out.with_columns(key(f"{side}_candidate").alias("k"))
            .join(lookup.rename({"party": f"{side}_party"}), on=["district", "k"], how="left")
            .drop("k")
        )
    unmatched = out.filter(pl.col("to_party").is_null())
    if unmatched.height:
        raise ValueError(f"Unmatched DoP candidates: {unmatched.select('district', 'to_candidate')}")
    return out
