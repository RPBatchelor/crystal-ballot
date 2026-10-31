"""Ingest NSW Legislative Assembly results from the NSW Electoral Commission (NSWEC).

The NSWEC's past-results site (pastvtr.elections.nsw.gov.au) has three pages per
district, cached under ``data/raw/nswec/{year}``:

* first preferences, with a votes-by-venue table (``booths``, used to re-cut a previous
  election onto new boundaries);
* the full distribution of preferences: NSW uses optional preferential voting, so every
  count also records the ballots that *exhausted* (no further preference), kept here as
  transfers to ``EXH``;
* a two-candidate-preferred tool, which gives the count between *any* two candidates.
  It supplies the Labor v Coalition 2PP in every seat, including non-classic ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import httpx
import polars as pl

from prophecy import RAW_DIR
from prophecy.ingest.vec import _CANDIDATE_SCHEMA, USER_AGENT, _cached_get, _int, _ResultsPageParser
from prophecy.schema.parties import bloc, party_code

BASE = "https://pastvtr.elections.nsw.gov.au"
EXHAUSTED = "EXH"


@dataclass(frozen=True)
class Site:
    """URL layout of one election on the NSWEC archive."""

    index: str
    fp: str  # first preferences, by district slug
    dop: str  # distribution of preferences
    tcp_tool: str  # page listing every candidate pair
    tcp_data: str  # pair fragment, from the tool's option value


SITES = {
    2015: Site("/SGE2015/la-home.htm", "/SGE2015/la/{d}/cc/fp_summary/index.htm",
               "/SGE2015/la/{d}/dop/dop/index.htm", "/SGE2015/la/{d}/tcp/tool/index.htm",
               "/SGE2015/data/{pair}/tcp_vote_summary.html"),
    **{year: Site(f"/{code}/LA/Results", f"/{code}/LA/{{d}}/cc/fp_summary", f"/{code}/LA/{{d}}/dop/dop",
                  f"/{code}/LA/{{d}}/TCP", f"/{code}/LA/{{d}}/TCP/{{pair}}/tcp_vote_summary.html")
       for year, code in [(2019, "SG1901"), (2023, "SG2301")]},
}


# --------------------------------------------------------------------------------------
# Page parsing
# --------------------------------------------------------------------------------------

def _tables(html: str) -> list[list[list[str]]]:
    p = _ResultsPageParser()
    p.feed(html)
    return [t for s in p.sections for t in s.tables]


def district_name(html: str, slug: str) -> str:
    m = re.search(r"State Electoral District of ([^<\"]+?)\s*<", html)
    return m.group(1).strip() if m else slug.replace("-", " ").title()


def parse_fp(html: str) -> tuple[list[dict], list[dict], dict]:
    """Candidates (ballot order) with votes, votes by venue, and district totals."""
    tables = _tables(html)
    summary = next(t for t in tables if t and t[0][:2] == ["Candidate", "Representation"])
    cands = []
    for row in summary[1:]:
        if row[0].upper().startswith("TOTAL"):
            continue
        cands.append({"candidate": row[0], "party_name": row[1] or "Independent", "votes": _int(row[2])})

    booths, totals = [], {}
    venue = next((t for t in tables if t and t[0] and t[0][0].startswith("Venue")), None)
    if venue is not None:
        n = len(cands)
        section = ""
        for row in venue[1:]:
            if not any(row[1:]):
                section = row[0]
                continue
            label = row[0]
            if label.startswith("%"):
                continue
            values = [_int(x) or 0 for x in row[1:n + 4]]
            if label.startswith("Total Votes"):
                totals = {"formal": values[n], "informal": values[n + 1]}
                continue
            if label.startswith("Total"):  # section subtotals
                continue
            for c, v in zip(cands, values[:n]):
                booths.append({"section": section, "venue": label, "candidate": c["candidate"], "votes": v})
            booths.append({"section": section, "venue": label, "candidate": "", "votes": values[n + 1]})
    return cands, booths, totals


def parse_dop(html: str, cands: list[dict]) -> tuple[list[dict], dict[str, int], str | None]:
    """Transfers per count (incl. exhausted), each candidate's final total, and the
    elected candidate.

    Columns: name, first preferences, then (distributed, progressive) per later count.
    """
    tables = _tables(html)
    table = next((t for t in tables if t and t[0] and t[0][0] == "Counts"), None)
    if table is None:
        return [], {}, None
    excluded_row = table[1]
    # Count c (2, 3, ...) excludes the candidate named in column c-1 of the second row.
    # "SICARI Rosa (Rosetta) (LDP)Excluded Candidate" -> "SICARI Rosa (Rosetta)"
    excluded = [re.sub(r"\s*\([^()]*\)\s*Excluded.*$", "", x).strip()
                for x in excluded_row[2:] if "Excluded" in x]
    names = [c["candidate"] for c in cands]

    def match(cell: str) -> str | None:
        cell = cell.replace(" ", "")
        return next((n for n in names if cell.startswith(n.replace(" ", ""))), None)

    rows: dict[str, list[str]] = {}
    exhausted: list[str] = []
    elected = None
    for row in table[3:]:
        if row[0].startswith("Exhausted"):
            exhausted = row
            continue
        name = match(row[0])
        if name is None:
            continue
        rows[name] = row
        if any(x.startswith("ELECTED") for x in row[1:]):
            elected = name

    def cell(row: list[str], j: int) -> int | None:
        if j >= len(row):
            return None
        return _int(row[j].removeprefix("ELECTED")) if row[j] not in ("", "EXCLUDED", "-") else None

    transfers = []
    final: dict[str, int] = {}
    for k, loser in enumerate(excluded):
        frm = match(loser)
        dist_col = 2 + 2 * k
        for name, row in rows.items():
            if name == frm:
                continue
            v = cell(row, dist_col)
            if v is not None:
                transfers.append({"count": k + 2, "from_candidate": frm, "to_candidate": name, "votes": v})
        if exhausted:
            transfers.append({"count": k + 2, "from_candidate": frm, "to_candidate": "Exhausted",
                              "votes": cell(exhausted, dist_col) or 0})
    last = 1 + 2 * len(excluded)  # progressive total after the final count
    for name, row in rows.items():
        v = cell(row, last)
        if v is not None and name not in {match(x) for x in excluded}:
            final[name] = v
    return transfers, final, elected


def tcp_pairs(html: str) -> list[str]:
    """Option values of the two-candidate-preferred tool (one per candidate pair)."""
    return re.findall(r'<option value="([^"]+)"', html)


def parse_tcp_fragment(html: str) -> dict:
    vals = dict(re.findall(r"\$(\w+)=([^\n\r]*)", html))
    return {"a": vals["notionalA"].strip(), "b": vals["notionalB"].strip(),
            "a_votes": int(vals["formalA"]), "b_votes": int(vals["formalB"]),
            "exhausted": int(vals["exhausted"])}


# --------------------------------------------------------------------------------------
# Download + assemble
# --------------------------------------------------------------------------------------

def _slugs(index_html: str, site: Site) -> list[str]:
    pattern = re.escape(site.fp).replace(r"\{d\}", "([a-z0-9-]+)")
    return sorted(set(re.findall(pattern, index_html)))


def _pair_key(pair: str) -> tuple[str, str]:
    a, b = pair.rstrip("/").split("/")[-2:]
    return a, b


def _surname_key(name: str) -> str:
    """'CLANCY Justin' and option slugs 'clancy-justin' / 'clancy_justin' -> 'clancyjustin'."""
    return re.sub(r"[^a-z]", "", name.lower())


def ingest_nswec_assembly(year: int) -> dict[str, pl.DataFrame]:
    site = SITES[year]
    raw = RAW_DIR / "nswec" / str(year)
    election_id = f"nsw-{year}"
    districts, primary, final, tcp, tpp, transfers, booths, tpp_booths = [], [], [], [], [], [], [], []
    with httpx.Client(base_url=BASE, headers={"User-Agent": USER_AGENT}, follow_redirects=True,
                      timeout=60) as client:
        index = _cached_get(client, site.index, raw / "index.html").read_text(encoding="utf-8")
        for slug in _slugs(index, site):
            fp_html = _get(client, site.fp.format(d=slug), raw / "fp" / f"{slug}.html")
            name = district_name(fp_html, slug)
            cands, venue_rows, totals = parse_fp(fp_html)
            for c in cands:
                c["party"] = party_code(c["party_name"])
            dop_html = _get(client, site.dop.format(d=slug), raw / "dop" / f"{slug}.html")
            moves, final_votes, elected = parse_dop(dop_html, cands)
            party_of = {c["candidate"]: c for c in cands}
            if elected is None:  # no "ELECTED" marker: highest final (or primary) total
                votes = final_votes or {c["candidate"]: c["votes"] for c in cands}
                elected = max(votes, key=votes.get)
            districts.append({
                "election_id": election_id, "district": name, "elected": elected,
                "elected_party_name": party_of[elected]["party_name"],
                "elected_party": party_of[elected]["party"],
                "enrolment": _enrolment(fp_html), "formal": totals.get("formal") or sum(c["votes"] for c in cands),
                "informal": totals.get("informal"),
            })
            primary += _rows(election_id, name, cands, elected)
            final_rows = [{**party_of[n], "votes": v} for n, v in final_votes.items()]
            final += _rows(election_id, name, final_rows, elected)
            if len(final_rows) == 2:
                tcp += _rows(election_id, name, final_rows, elected)
            for t in moves:
                to = party_of.get(t["to_candidate"])
                transfers.append({
                    "district": name, "count": t["count"], "from_candidate": t["from_candidate"],
                    "to_candidate": t["to_candidate"], "votes": float(t["votes"]),
                    "from_party": party_of[t["from_candidate"]]["party"],
                    "to_party": to["party"] if to else EXHAUSTED, "election_id": election_id,
                })
            for b in venue_rows:
                c = party_of.get(b["candidate"])
                booths.append({"election_id": election_id, "district": name, "section": b["section"],
                               "venue": b["venue"], "candidate": b["candidate"],
                               "party": c["party"] if c else "INFORMAL", "votes": b["votes"]})
            res = _alp_coal_tpp(client, site, slug, raw, cands)
            if res is not None:
                row, venues = res
                tpp.append({"election_id": election_id, "district": name, **row})
                tpp_booths += [{"election_id": election_id, "district": name, "section": v["section"],
                                "venue": v["venue"], "alp": v["alp"], "coal": v["coal"],
                                "exhausted": v["exhausted"]} for v in venues]
    return {
        "districts": pl.DataFrame(districts),
        "primary": pl.DataFrame(primary, schema=_CANDIDATE_SCHEMA),
        "final": pl.DataFrame(final, schema=_CANDIDATE_SCHEMA),
        "tcp": pl.DataFrame(tcp, schema=_CANDIDATE_SCHEMA),
        "tpp": pl.DataFrame(tpp),
        "dop_transfers": pl.DataFrame(transfers),
        "booths": pl.DataFrame(booths),
        "tpp_booths": pl.DataFrame(tpp_booths),
    }


def _get(client: httpx.Client, url: str, dest: Path) -> str:
    return _cached_get(client, url, dest).read_text(encoding="utf-8", errors="replace")


def _enrolment(html: str) -> int | None:
    m = re.search(r"Electors Enrolled[^:]*:\s*([\d,]+)", html)
    return _int(m.group(1)) if m else None


def _rows(election_id: str, district: str, cands: list[dict], elected: str) -> list[dict]:
    total = sum(c["votes"] or 0 for c in cands) or 1
    return [{
        "election_id": election_id, "district": district, "candidate": c["candidate"],
        "party_name": c["party_name"], "party": c["party"], "bloc": bloc(c["party"]),
        "votes": c["votes"], "pct": round(100 * (c["votes"] or 0) / total, 3),
        "elected": c["candidate"] == elected,
    } for c in cands]


def _alp_coal_tpp(client: httpx.Client, site: Site, slug: str, raw: Path,
                  cands: list[dict]) -> tuple[dict, list[dict]] | None:
    """Labor v Coalition count from the TCP tool (leading Coalition candidate), in total
    and by venue."""
    alp = [c for c in cands if c["party"] == "ALP"]
    coal = sorted((c for c in cands if bloc(c["party"]) == "COAL"), key=lambda c: -c["votes"])
    if not alp or not coal:
        return None
    tool = _get(client, site.tcp_tool.format(d=slug), raw / "tcp" / f"{slug}.html")
    want = {_surname_key(alp[0]["candidate"]), _surname_key(coal[0]["candidate"])}
    pair = next((p for p in tcp_pairs(tool) if {_surname_key(x) for x in _pair_key(p)} == want), None)
    if pair is None:
        return None
    # As the site's script does: drop parentheses in names ("zaman-mohammed-(haseen)").
    url_pair = pair.replace("(", "").replace(")", "").replace("--", "-")
    frag = parse_tcp_fragment(_get(client, site.tcp_data.format(d=slug, pair=url_pair),
                                   raw / "tcp" / f"{slug}-alp-coal.html"))
    alp_first = _surname_key(frag["a"]) == _surname_key(alp[0]["candidate"])
    alp_votes = frag["a_votes"] if alp_first else frag["b_votes"]
    coal_votes = frag["b_votes"] if alp_first else frag["a_votes"]
    table = _get(client, site.tcp_data.format(d=slug, pair=url_pair).replace(
        "tcp_vote_summary", "tcp_table"), raw / "tcp" / f"{slug}-alp-coal-venues.html")
    venues = [{**v, "alp": v["a"] if alp_first else v["b"], "coal": v["b"] if alp_first else v["a"]}
              for v in parse_tcp_venues(table)]
    return {"tpp_method": "tcp", "alp_votes": alp_votes, "coal_votes": coal_votes,
            "alp_tpp": round(100 * alp_votes / (alp_votes + coal_votes), 3),
            "exhausted": frag["exhausted"]}, venues


def parse_tcp_venues(html: str) -> list[dict]:
    """Two-candidate count by venue: section, venue, a, b, exhausted."""
    tables = _tables(html)
    if not tables:
        return []
    out, section = [], ""
    for row in tables[0][1:]:
        if len(row) == 1 or not any(row[1:]):
            section = row[0]
            continue
        if row[0].startswith(("Total", "%")):
            continue
        a, b, ex = (_int(x) or 0 for x in row[1:4])
        out.append({"section": section, "venue": row[0], "a": a, "b": b, "exhausted": ex})
    return out
