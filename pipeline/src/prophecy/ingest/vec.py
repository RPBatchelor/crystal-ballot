"""Ingest Victorian Legislative Assembly results from the VEC website.

For each election we scrape the per-district results pages (cached under
``data/raw/vec/{year}/districts``), producing three tidy tables:

* ``primary``  - first-preference votes per candidate
* ``final``    - votes after full distribution (the deciding two-candidate count)
* ``tpp``      - ALP v Coalition two-party-preferred per district (from the VEC xlsx)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import httpx
import polars as pl

from prophecy import CURATED_DIR, RAW_DIR
from prophecy.schema.parties import bloc, party_code

BASE = "https://www.vec.vic.gov.au"
USER_AGENT = "prophecy-election-model/0.1 (election forecasting research)"
RESULTS_INDEX = {
    2022: "/results/state-election-results/2022-state-election-results",
}
TPP_XLSX = {
    2022: "/-/media/a8466a1794024583a2128ed431ca24f3.xlsx",
}
# Districts whose general-election result was decided at a supplementary election.
SUPPLEMENTARY = {
    2022: {
        "Narracan": "/results/state-election-results/state-by-elections-timeline/"
        "narracan-district-supplementary-election-results",
    },
}
BY_ELECTIONS_INDEX = "/results/state-election-results/state-by-elections-timeline"
# Elections before 2022 are served as static HTML from the VEC's results archive.
ARCHIVE_BASE = "https://itsitecoreblobvecprd01.blob.core.windows.net/public-files/historical-results"
ARCHIVE_YEARS = {2014, 2018}
REQUEST_DELAY_S = 1.0


# --------------------------------------------------------------------------------------
# HTML extraction
# --------------------------------------------------------------------------------------

@dataclass
class _Section:
    heading: str
    text: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (href, text)


class _ResultsPageParser(HTMLParser):
    """Split a page into sections by <h3>, collecting text, tables and links."""

    def __init__(self) -> None:
        super().__init__()
        self.sections: list[_Section] = [_Section("")]
        self._in_h3 = False
        self._h3_buf: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._href: str | None = None
        self._a_buf: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "h3":
            self._in_h3, self._h3_buf = True, []
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "a":
            self._href, self._a_buf = dict(attrs).get("href"), []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "h3" and self._in_h3:
            self._in_h3 = False
            self.sections.append(_Section(_norm("".join(self._h3_buf))))
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(_norm("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.sections[-1].tables.append(self._table)
            self._table = None
        elif tag == "a" and self._href is not None:
            self.sections[-1].links.append((self._href, _norm("".join(self._a_buf))))
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_h3:
            self._h3_buf.append(data)
        if self._cell is not None:
            self._cell.append(data)
        if self._href is not None:
            self._a_buf.append(data)
        if data.strip():
            self.sections[-1].text.append(_norm(data))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _int(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _section(sections: list[_Section], startswith: str) -> _Section | None:
    return next((s for s in sections if s.heading.lower().startswith(startswith.lower())), None)


@dataclass
class DistrictResult:
    district: str
    elected: str | None
    elected_party: str | None
    enrolment: int | None
    formal: int | None
    informal: int | None
    primary: list[dict]
    final: list[dict]
    tpp: list[dict]
    booth_primary_xlsx: str | None
    tcp: list[dict] = field(default_factory=list)  # two-candidate-preferred totals
    tcp_inline: list[dict] = field(default_factory=list)  # 2CP table on the page itself


def parse_district_page(html: str, district: str) -> DistrictResult:
    p = _ResultsPageParser()
    p.feed(html)
    sections = p.sections

    elected = elected_party = None
    sec = _section(sections, "Elected member")
    if sec and sec.text:
        elected = sec.text[0]
        elected_party = sec.text[1] if len(sec.text) > 1 else None

    enrolment = formal = informal = None
    sec = _section(sections, "Recheck votes") or _section(sections, "Recount votes") or _section(sections, "Votes")
    if sec:
        joined = " | ".join(sec.text)
        # 2022: "Total enrolment as at close of rolls: | 54533"; archive pages split the
        # label: "Total Enrolment | as at close of rolls: | 53340".
        m = re.search(r"enrolment(?:[^|\d]*\|)+\s*([\d,]+)", joined, re.IGNORECASE)
        enrolment = _int(m.group(1)) if m else None
        m = re.search(r"Formal votes:?\s*\|\s*([\d,]+)", joined, re.IGNORECASE)
        formal = _int(m.group(1)) if m else None
        m = re.search(r"Informal votes:?\s*\|\s*([\d,]+)", joined, re.IGNORECASE)
        informal = _int(m.group(1)) if m else None

    primary: list[dict] = []
    booth_xlsx = None
    sec = (_section(sections, "Recheck first preference") or _section(sections, "Recount first preference")
           or _section(sections, "First preference"))
    if sec and sec.tables:
        for row in sec.tables[0][1:]:
            if len(row) >= 3 and _int(row[2]) is not None:
                primary.append({"candidate": row[0], "party_name": row[1], "votes": _int(row[2])})
        booth_xlsx = next((h for h, _ in sec.links if h and ".xls" in h.lower()), None)
        if booth_xlsx is None:
            booth_xlsx = next((h for h, t in sec.links if "primary results" in t.lower()), None)

    final: list[dict] = []
    sec = _section(sections, "Results after distribution")
    if sec and sec.tables:
        for row in sec.tables[0][1:]:
            if len(row) >= 3 and _int(row[2]) is not None:
                final.append({"candidate": row[0], "party_name": row[1], "votes": _int(row[2])})

    tpp: list[dict] = []
    sec = _section(sections, "Two party preferred")
    if sec and sec.tables:
        for row in sec.tables[0][1:]:
            if len(row) >= 3 and _int(row[2]) is not None:
                tpp.append({"party_name": row[0], "candidate": row[1], "votes": _int(row[2])})

    # Archive pages for seats without a full distribution give the 2CP count inline.
    tcp_inline: list[dict] = []
    sec = _section(sections, "Two candidate preferred")
    if sec:
        for table in sec.tables:
            if table and table[0] and table[0][0].lower() == "candidate":
                for row in table[1:]:
                    if len(row) >= 3 and _int(row[2]) is not None:
                        tcp_inline.append({"candidate": row[0], "party_name": row[1], "votes": _int(row[2])})

    # The party line under "Elected member" is absent for independents (the next text
    # is a map caption), so take the elected member's party from the results table.
    elected_row = next((c for c in primary if c["candidate"] == elected), None)
    if elected_row is not None:
        elected_party = elected_row["party_name"]

    return DistrictResult(
        district, elected, elected_party, enrolment, formal, informal, primary, final, tpp,
        booth_xlsx, tcp_inline=tcp_inline,
    )


def parse_2cp_page(html: str) -> list[dict]:
    """Two-candidate-preferred totals from a '2CP results by voting centre' page.

    Table layout: a row of candidate names, a 'Voting centres' row of party names, one
    row per voting centre / vote type, then a 'Total' row. Columns 1-2 are the two
    candidates; the rest are mis-sorts, informal and total polled.
    """
    p = _ResultsPageParser()
    p.feed(html)
    for sec in p.sections:
        for table in sec.tables:
            party_idx = next(
                (i for i, r in enumerate(table) if r and r[0].lower().startswith("voting centre")),
                None,
            )
            total = next((r for r in table if r and r[0].lower() == "total"), None)
            if party_idx is None or party_idx == 0 or total is None:
                continue
            names, parties = table[party_idx - 1], table[party_idx]
            return [
                {"candidate": names[i], "party_name": parties[i], "votes": _int(total[i])}
                for i in (1, 2)
            ]
    return []


def canonical_district(name: str) -> str:
    """Normalise district names across VEC pages and spreadsheets."""
    name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
    key = re.sub(r"[^a-z]", "", name.lower())
    return _CANONICAL.get(key, name)


_CANONICAL = {"southwestcoast": "South-West Coast"}


# --------------------------------------------------------------------------------------
# Download + assemble
# --------------------------------------------------------------------------------------

def _client() -> httpx.Client:
    return httpx.Client(
        base_url=BASE, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60
    )


def _cached_get(client: httpx.Client, url: str, dest: Path, binary: bool = False) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    for attempt in range(4):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            break
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        dest.write_bytes(resp.content)
    else:
        dest.write_text(resp.text, encoding="utf-8")
    time.sleep(REQUEST_DELAY_S)
    return dest


def district_links(index_html: str) -> dict[str, str]:
    """District name -> results page path, from an election results index page."""
    links = re.findall(r'href="([^"]*/results-by-district/([a-z0-9-]+)-district-results)"', index_html)
    out: dict[str, str] = {}
    for href, slug in links:
        name = canonical_district(" ".join(w.capitalize() for w in slug.split("-")))
        out.setdefault(name, href)
    return out


def ingest_vec_assembly(year: int) -> dict[str, pl.DataFrame]:
    raw = RAW_DIR / "vec" / str(year)
    with _client() as client:
        index = _cached_get(client, RESULTS_INDEX[year], raw / "index.html").read_text(encoding="utf-8")
        links = district_links(index)
        links.update(SUPPLEMENTARY.get(year, {}))
        results, tcp = _fetch_districts(client, links, raw / "districts", raw / "2cp")
        tpp_path = _cached_get(client, TPP_XLSX[year], raw / "tpp_by_district.xlsx", binary=True)

    election_id = f"vic-{year}"
    tables = _assemble(results, tcp, election_id)
    tables["tpp"] = read_tpp_xlsx(tpp_path, election_id)
    return tables


def ingest_vec_by_elections(since: date) -> dict[str, pl.DataFrame]:
    """State by-elections on the VEC timeline held on or after ``since``."""
    raw = RAW_DIR / "vec" / "by-elections"
    with _client() as client:
        index = _cached_get(client, BY_ELECTIONS_INDEX, raw / "index.html").read_text(encoding="utf-8")
        hrefs = sorted(set(re.findall(
            r'href="(/results/state-election-results/state-by-elections-timeline/'
            r'[a-z0-9-]+/results-by-district/[a-z0-9-]+)"', index,
        )))
        links = {
            canonical_district(h.rsplit("/", 1)[-1].split("-district")[0].replace("-", " ").title()): h
            for h in hrefs
        }
        results, tcp = _fetch_districts(client, links, raw / "districts", raw / "2cp")

    # VEC by-election pages carry no date; dates are curated by hand.
    dates = pl.read_csv(CURATED_DIR / "by_elections_vic.csv", try_parse_dates=True)
    tables = _assemble(results, tcp, "by-election")
    tables["districts"] = tables["districts"].join(
        dates.select("district", "date", "kind"), on="district", how="left"
    )
    undated = tables["districts"].filter(pl.col("date").is_null())["district"].to_list()
    if undated:
        raise ValueError(f"Add dates for by-elections {undated} to by_elections_vic.csv")
    keep = tables["districts"].filter(
        (pl.col("date") >= since) & (pl.col("kind") == "by-election")
    )["district"].to_list()
    return {k: df.filter(pl.col("district").is_in(keep)) for k, df in tables.items()}


def _slug(href: str) -> str:
    return href.rstrip("/").rsplit("/", 1)[-1].removesuffix("-district-results")


def _fetch_districts(
    client: httpx.Client, links: dict[str, str], page_dir: Path, tcp_dir: Path
) -> tuple[list[DistrictResult], dict[str, list[dict]]]:
    results: list[DistrictResult] = []
    tcp: dict[str, list[dict]] = {}
    for name, href in sorted(links.items()):
        html = _cached_get(client, href, page_dir / f"{_slug(href)}.html").read_text(encoding="utf-8")
        results.append(parse_district_page(html, name))
        m = re.search(r'href="([^"]*2cp-results-by-voting-centre[^"]*)"', html)
        if m:
            tcp_html = _cached_get(client, m.group(1), tcp_dir / f"{_slug(href)}.html")
            tcp[name] = parse_2cp_page(tcp_html.read_text(encoding="utf-8"))
    return results, tcp


def _assemble(
    results: list[DistrictResult], tcp: dict[str, list[dict]], election_id: str
) -> dict[str, pl.DataFrame]:
    summary = pl.DataFrame(
        [
            {
                "election_id": election_id,
                "district": canonical_district(r.district),
                "elected": r.elected,
                "elected_party_name": r.elected_party,
                "elected_party": party_code(r.elected_party),
                "enrolment": r.enrolment,
                "formal": r.formal,
                "informal": r.informal,
                "booth_primary_xlsx": r.booth_primary_xlsx,
            }
            for r in results
        ]
    )
    # The 2CP page is an indicative election-night count and can pick the wrong pair
    # (e.g. Shepparton 2022) or predate rechecks (Pakenham 2022). Prefer the official
    # distribution whenever it ends with exactly two candidates.
    for r in results:
        r.tcp = r.final if len(r.final) == 2 else (tcp.get(r.district) or r.tcp_inline)
        if not r.tpp and {bloc(party_code(c["party_name"])) for c in r.tcp} == {"ALP", "COAL"}:
            r.tpp = [{"party_name": c["party_name"], "candidate": c["candidate"], "votes": c["votes"]}
                     for c in r.tcp]
    return {
        "districts": summary,
        "primary": _long(results, "primary", election_id),
        "final": _long(results, "final", election_id),
        "tcp": _long(results, "tcp", election_id),
    }


def _long(results: list[DistrictResult], attr: str, election_id: str) -> pl.DataFrame:
    rows = []
    for r in results:
        rows_r = getattr(r, attr)
        total = sum(x["votes"] or 0 for x in rows_r) or 1
        for x in rows_r:
            code = party_code(x["party_name"])
            rows.append(
                {
                    "election_id": election_id,
                    "district": canonical_district(r.district),
                    "candidate": x["candidate"],
                    "party_name": x["party_name"],
                    "party": code,
                    "bloc": bloc(code),
                    "votes": x["votes"],
                    "pct": round(100 * (x["votes"] or 0) / total, 3),
                    "elected": x["candidate"] == r.elected,
                }
            )
    return pl.DataFrame(rows, schema=_CANDIDATE_SCHEMA)


_CANDIDATE_SCHEMA = {
    "election_id": pl.String,
    "district": pl.String,
    "candidate": pl.String,
    "party_name": pl.String,
    "party": pl.String,
    "bloc": pl.String,
    "votes": pl.Int64,
    "pct": pl.Float64,
    "elected": pl.Boolean,
}


def ingest_vec_archive(year: int) -> dict[str, pl.DataFrame]:
    """Results for an archived election (static per-district pages, same layout as 2022)."""
    raw = RAW_DIR / "vec" / str(year)
    base = f"{ARCHIVE_BASE}/state{year}/"
    with httpx.Client(base_url=base, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True, timeout=60) as client:
        summary = _cached_get(client, "summary.html", raw / "summary.html").read_text(encoding="utf-8")
        slugs = sorted(set(re.findall(r'href="([a-z-]+district)\.html"', summary)))
        results = []
        for slug in slugs:
            html = _cached_get(client, f"{slug}.html", raw / "districts" / f"{slug}.html").read_text(
                encoding="utf-8", errors="replace")
            results.append(parse_district_page(html, _archive_name(html, slug)))
    election_id = f"vic-{year}"
    tables = _assemble(results, {}, election_id)
    tables["tpp"] = _tpp_from_pages(results, election_id)
    return tables


def _archive_name(html: str, slug: str) -> str:
    m = re.search(r">\s*([A-Z][A-Za-z' -]+?) District\s*<", html)
    return canonical_district(m.group(1).strip() if m else slug.removesuffix("district").title())


def _tpp_from_pages(results: list[DistrictResult], election_id: str) -> pl.DataFrame:
    rows = []
    for r in results:
        alp = next((x["votes"] for x in r.tpp if party_code(x["party_name"]) == "ALP"), None)
        coal = next((x["votes"] for x in r.tpp if bloc(party_code(x["party_name"])) == "COAL"), None)
        if alp is None or coal is None:
            continue
        rows.append({
            "election_id": election_id, "district": canonical_district(r.district),
            "tpp_method": "page", "alp_votes": alp, "coal_votes": coal,
            "alp_tpp": round(100 * alp / (alp + coal), 3),
        })
    return pl.DataFrame(rows)


def read_tpp_xlsx(path: Path, election_id: str) -> pl.DataFrame:
    df = pl.read_excel(path, sheet_id=1)
    df = df.rename({c: c.strip() for c in df.columns})
    return df.select(
        pl.lit(election_id).alias("election_id"),
        pl.col("District").map_elements(canonical_district, return_dtype=pl.String)
        .alias("district"),
        pl.col("Method").alias("tpp_method"),
        pl.col("ALP votes").cast(pl.Int64).alias("alp_votes"),
        pl.col("Coalition votes").cast(pl.Int64).alias("coal_votes"),
        (100 * pl.col("ALP %")).round(3).alias("alp_tpp"),
    ).filter(pl.col("district").is_not_null() & (pl.col("district") != "TOTAL"))
