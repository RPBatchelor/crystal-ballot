"""Ingest ACT Legislative Assembly results from Elections ACT.

The ACT, like Tasmania, elects its Assembly by Hare-Clark: five electorates of five
members since 2016. The tables match the Tasmanian ones (``prophecy.ingest.tec``):
``primary`` (first preferences by candidate, with group), ``members`` (one row per member
elected) and ``districts`` (one row per electorate).

Sources (cached under ``data/raw/elections_act/{year}``):

* 2016 and 2020: the distribution of preferences workbooks ("Table 1" per electorate),
  whose first row of counts is the first preferences, under each candidate's group.
* 2024: the statistics book (``Stats-Book-2024.XLSX``): first preferences by candidate
  per electorate (``{Electorate}CanSum`` sheets) and party abbreviations.
* Members elected: the "list of elected candidates" page for each election, matched
  against the candidates by name.
"""

from __future__ import annotations

import html
import io
import re

import httpx
import openpyxl
import polars as pl

from prophecy import RAW_DIR
from prophecy.ingest.vec import USER_AGENT, _cached_get
from prophecy.schema.parties import bloc, party_code

SITE = "https://www.elections.act.gov.au"
PAGES = SITE + "/elections/previous-assembly-elections/{year}-election"
RAW = RAW_DIR / "elections_act"
ELECTORATES = ["Brindabella", "Ginninderra", "Kurrajong", "Murrumbidgee", "Yerrabi"]
SEATS = 5
DOP_PAGE = {2016: "/2016-distribution-of-preferences", 2020: "/distribution-of-preferences-2020"}
# The 2024 list is filed under a page named for 2020.
ELECTED_PAGE = {2016: "/2016-list-of-elected-candidates", 2020: "/2020-list-of-elected-candidates",
                2024: "/2020-list-of-elected-candidates"}
STATS_BOOK_2024 = SITE + "/__data/assets/excel_doc/0006/2799717/Stats-Book-2024.XLSX"
# Groups whose names ``party_code`` would read as independents but which ran party
# tickets, and one-candidate groups of a named independent.
GROUPS = {
    "canberra liberals": ("LIB", "COAL"),
    "independents for canberra": ("IFC", "OTH"),
    "strong independents": ("STR", "OTH"),
    "belco party": ("BEL", "OTH"),
    "fiona carrick independent": ("IND", "IND"),
    "ungrouped": ("IND", "IND"),
}


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=120)


def _name(given_surname: str) -> str:
    """'Taimus WERNER-GIBBINGS' -> 'WERNER-GIBBINGS Taimus' (surname in capitals last)."""
    words = given_surname.split()
    k = len(words)
    while k > 0 and re.fullmatch(r"(?:Mc|Mac|De|Di|Le|O')?[A-Z][A-Z'\-]+", words[k - 1]):
        k -= 1
    k = k if k < len(words) else len(words) - 1
    return " ".join(words[k:] + words[:k])


def _party(group: str) -> tuple[str, str, str]:
    """(party name, code, bloc) for a ballot group."""
    g = " ".join(group.split())
    if g.lower() in GROUPS:
        code, b = GROUPS[g.lower()]
        return ("Independent" if code == "IND" else g), code, b
    code = party_code(g)
    return g, code, bloc(code)


def _workbook(path) -> openpyxl.Workbook:
    return openpyxl.load_workbook(io.BytesIO(path.read_bytes()), data_only=True)


def _first_preferences_dop(rows: list[tuple]) -> list[dict]:
    """Candidates and first preferences from a distribution of preferences Table 1."""
    groups, names = rows[1], rows[2]
    first = next(r for r in rows if r[0] == 1)
    out, group = [], None
    for j, (g, n) in enumerate(zip(groups, names)):
        if j < 2:
            continue
        if g:
            group = str(g)
        if not n or not str(n).strip() or group is None:
            continue
        name = str(n).strip()
        if name.lower() in ("exhausted", "loss by fraction", "total", "votes"):
            continue
        out.append({"group": group, "name": _name(name), "raw": name, "votes": int(first[j] or 0)})
    return out


def _first_preferences_stats(rows: list[tuple], parties: dict[str, str]) -> tuple[list[dict], int]:
    header = rows[0]
    total = header.index("Total")
    out, formal = [], 0
    for r in rows[1:]:
        label = r[0]
        if not isinstance(label, str):
            continue
        if label == "Formal":
            formal = int(r[total])
        elif label not in ("Group total", "Informal", "Total") and r[1] and str(r[1]).strip():
            out.append({"group": parties.get(str(r[1]).strip(), str(r[1]).strip()),
                        "name": _name(label.strip()), "raw": label.strip(), "votes": int(r[total] or 0)})
    return out, formal


def _elected(page: str) -> dict[str, str]:
    """Electorate -> its cell of members elected, as plain text."""
    i = page.find("<table")
    table = page[i:page.find("</table>", i)]
    out = {}
    for row in re.findall(r"<tr.*?</tr>", table, flags=re.S):
        cells = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S)]
        if len(cells) >= 2 and cells[0] in ELECTORATES:
            out[cells[0]] = cells[1]
    return out


def _is_elected(given_surname: str, cell: str) -> bool:
    """Candidate ('Given SURNAME') named in a members cell ('Given Surname - Party ...')."""
    words = given_surname.split()
    pattern = rf"\b{re.escape(words[0])}\b[^,\-–]{{0,30}}?\b{re.escape(words[-1])}\b"
    return re.search(pattern, cell, flags=re.IGNORECASE) is not None


def ingest_act_assembly(year: int) -> dict[str, pl.DataFrame]:
    raw = RAW / str(year)
    eid = f"act-{year}"
    with _client() as client:
        page = _cached_get(client, PAGES.format(year=year) + ELECTED_PAGE[year], raw / "elected.html").read_text(encoding="utf-8")
        elected = _elected(page)
        cands: dict[str, list[dict]] = {}
        formal: dict[str, int] = {}
        if year == 2024:
            wb = _workbook(_cached_get(client, STATS_BOOK_2024, raw / "stats_book.xlsx", binary=True))
            parties = {r[0]: r[1] for r in wb["Abbreviations"].iter_rows(values_only=True) if r[0] and r[1]}
            for e in ELECTORATES:
                cands[e], formal[e] = _first_preferences_stats(list(wb[f"{e[:4]}CanSum"].iter_rows(values_only=True)), parties)
        else:
            dop = _cached_get(client, PAGES.format(year=year) + DOP_PAGE[year], raw / "dop.html").read_text(encoding="utf-8")
            links = dict.fromkeys(re.findall(r'href="([^"]+?\.xlsx)"', dop))
            for e in ELECTORATES:
                url = next(u for u in links if e in u and re.search(r"table_?0?1", u, re.IGNORECASE))
                wb = _workbook(_cached_get(client, url, raw / f"{e.lower()}_table1.xlsx", binary=True))
                cands[e] = _first_preferences_dop(list(wb.worksheets[0].iter_rows(values_only=True)))
                formal[e] = sum(c["votes"] for c in cands[e])
    primary, members, districts = [], [], []
    for e in ELECTORATES:
        won = []
        for c in cands[e]:
            party_name, code, b = _party(c["group"])
            is_won = _is_elected(c["raw"], elected[e])
            primary.append({"district": e, "candidate": c["name"], "group": c["group"],
                            "party_name": party_name, "party": code, "bloc": b, "votes": c["votes"],
                            "pct": round(100 * c["votes"] / formal[e], 3), "elected": is_won})
            if is_won:
                won.append((c["name"], code, party_name))
        if len(won) != SEATS:
            raise ValueError(f"{eid} {e}: matched {len(won)} members elected, expected {SEATS}: {elected[e]}")
        # The elected lists do not give the order of election: numbered in ballot order.
        for i, (n, code, pname) in enumerate(won, start=1):
            members.append({"district": e, "order": i, "candidate": n, "party_name": pname, "party": code})
        districts.append({"district": e, "seats": SEATS, "formal": formal[e],
                          "elected": "; ".join(w[0] for w in won), "elected_party": "; ".join(w[1] for w in won)})
    tables = {"primary": pl.DataFrame(primary), "members": pl.DataFrame(members), "districts": pl.DataFrame(districts)}
    return {k: df.with_columns(pl.lit(eid).alias("election_id")).select("election_id", *df.columns)
            for k, df in tables.items()}
