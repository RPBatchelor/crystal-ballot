"""Current members and their 2026 status (recontesting / retiring / vacant).

``data/curated/members_vic-2026.csv`` is the hand-maintained source of truth. It was
bootstrapped from VEC results (first-elected year by matching names across 2014-2022)
and is updated with retirements parsed from the election article's "Candidates and
retiring MPs" section, which cites each announcement.
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from prophecy.ingest.vec import canonical_district
from prophecy.ingest.wikitable import clean

PARTY_HEADINGS = {"labor": "ALP", "liberal": "LIB", "national": "NAT", "greens": "GRN",
                  "independent": "IND", "legalise cannabis": "LCP"}


def parse_retirements(wikitext: str) -> list[dict]:
    """MLA (lower house) entries from the retiring-MPs section."""
    start = wikitext.find("== Candidates and retiring MPs ==")
    if start < 0:
        return []
    end = wikitext.find("\n== ", start + 10)
    section = wikitext[start:end if end > 0 else None]
    out, party = [], None
    for line in section.splitlines():
        h = re.match(r"^===\s*(.*?)\s*===", line)
        if h:
            key = h.group(1).lower()
            party = next((code for name, code in PARTY_HEADINGS.items() if name in key), None)
            continue
        if not line.lstrip().startswith("*") or " MLA" not in line:
            continue
        m = re.search(r"\[\[Electoral district of ([^|\]]+)", line)
        if not m:
            continue
        text = clean(line.lstrip("* "))
        died = bool(re.search(r"\bdied\b|death", text, re.IGNORECASE))
        announced = re.search(r"announced (\d{1,2} \w+ \d{4})", text)
        out.append({
            "district": canonical_district(m.group(1).strip()),
            "member_text": text.split(" MLA")[0].strip(),
            "party": party,
            "status": "vacant" if died else "retiring",
            "note": ("died" if died else f"announced {announced.group(1)}" if announced else ""),
        })
    return out


def apply_retirements(members_path: Path, retirements: list[dict]) -> pl.DataFrame:
    members = pl.read_csv(members_path)
    by_district = {r["district"]: r for r in retirements}
    unknown = set(by_district) - set(members["district"])
    if unknown:
        raise ValueError(f"Retirements for unknown districts: {sorted(unknown)}")
    rows = []
    for r in members.iter_rows(named=True):
        ret = by_district.get(r["district"])
        if ret:
            r = {**r, "status": ret["status"], "note": ret["note"],
                 "source": "Wikipedia: 2026 Victorian state election (retiring MPs)"}
            if ret["party"] and ret["party"] != r["party"]:
                # e.g. elected for Labor, now sitting as an independent.
                r["note"] = f"{r['note']}; now {ret['party']} (elected {r['party']})".strip("; ")
                r["party"] = ret["party"]
        rows.append(r)
    out = pl.DataFrame(rows)
    out.write_csv(members_path)
    return out
