"""Legislative Assembly candidates from the VEC's per-district nominations pages.

Writes ``data/curated/candidates_{election}.csv`` (district, name, party, ballot_position,
prior_share, note). Re-running keeps any hand-entered ``prior_share``/``note`` for
candidates already in the file. The pages list candidates in nomination order until
the ballot draw; pass ``ballot_order=True`` once the draw is published to record the
page order as the ballot position.
"""

from __future__ import annotations

import re
import time
from html import unescape

import httpx
import polars as pl

from prophecy import CURATED_DIR, RAW_DIR
from prophecy.ingest.vec import BASE, USER_AGENT
from prophecy.schema.parties import party_code

NOMINATIONS_URL = "/electoral-boundaries/state-districts/{slug}-district/nominations"
_ROW = re.compile(r'<tr class="candidate-row">\s*<td>\s*(.*?)\s*(?:<p>(.*?)</p>)?\s*</td>', re.S)
COLUMNS = ["district", "name", "party", "ballot_position", "prior_share", "note"]


def district_slug(district: str) -> str:
    """'South-West Coast' -> 'south-west-coast'."""
    return re.sub(r"[^a-z0-9]+", "-", district.lower()).strip("-")


def parse_nominations(page: str) -> list[tuple[str, str]]:
    """(name, party name) per candidate row; no party line means an independent."""
    out = []
    for name, party in _ROW.findall(page):
        name = unescape(re.sub(r"\s+", " ", name)).strip()
        party = unescape(re.sub(r"\s+", " ", party or "")).strip()
        out.append((name, party or "Independent"))
    return out


def ingest_nominations(election_id: str, districts: list[str], ballot_order: bool = False,
                       delay_s: float = 0.5) -> pl.DataFrame:
    raw = RAW_DIR / "vec" / election_id / "nominations"
    raw.mkdir(parents=True, exist_ok=True)
    rows = []
    with httpx.Client(base_url=BASE, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True, timeout=60) as client:
        for d in districts:
            slug = district_slug(d)
            resp = client.get(NOMINATIONS_URL.format(slug=slug))
            resp.raise_for_status()
            (raw / f"{slug}.html").write_text(resp.text, encoding="utf-8")
            cands = parse_nominations(resp.text)
            if not cands:
                raise ValueError(f"No candidates found on the VEC nominations page for {d}")
            for pos, (name, party_name) in enumerate(cands, start=1):
                code = party_code(party_name)
                rows.append({"district": d, "name": name, "party": code,
                             "ballot_position": pos if ballot_order else None,
                             "note": party_name if code.startswith("X_") else None})
            time.sleep(delay_s)
    new = pl.DataFrame(rows, schema={"district": pl.String, "name": pl.String, "party": pl.String,
                                     "ballot_position": pl.Int64, "note": pl.String})
    return _keep_curated(new, CURATED_DIR / f"candidates_{election_id}.csv")


def _keep_curated(new: pl.DataFrame, path) -> pl.DataFrame:
    """Carry hand-entered prior_share and note over from the existing file."""
    if path.exists():
        old = pl.read_csv(path, infer_schema_length=None, schema_overrides={
            "prior_share": pl.Float64, "note": pl.String, "ballot_position": pl.Int64})
    else:
        old = pl.DataFrame(schema={c: pl.String for c in COLUMNS}).with_columns(
            pl.col("prior_share").cast(pl.Float64))
    old = old.select("district", "name", "prior_share", pl.col("note").alias("old_note"))
    return (new.join(old, on=["district", "name"], how="left")
            .with_columns(pl.coalesce("old_note", "note").alias("note"))
            .select(COLUMNS))
