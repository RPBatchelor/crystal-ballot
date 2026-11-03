"""Ingest Western Australian Legislative Assembly results from the Western Australian
Electoral Commission (WAEC).

The WAEC's election pages are an app over a JSON API (``API``), which serves every state
general election since 2008 in one format:

* ``sgElections/{event}/LACandidateSurname``: every candidate, with full name, district
  and party name.
* ``sgElections/{event}/{district code}/results``: the official first-preference count
  with votes by polling place (``resultsPollingPlace``), the two-candidate count and the
  full distribution of preferences, round by round (``resultsFullDistribution``).

Candidates appear in the count tables by surname and party abbreviation only, so names
are matched back to the candidate list. Responses are cached under ``data/raw/waec``.
Western Australia uses full preferential voting for the Legislative Assembly.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

import httpx
import polars as pl

from prophecy import RAW_DIR
from prophecy.ingest.ecq import _tables
from prophecy.ingest.ecsa import _row, _surname_first
from prophecy.ingest.vec import USER_AGENT, _cached_get
from prophecy.schema.parties import party_code

API = "https://eis.waec.wa.gov.au/api/sgElections/"
RAW = RAW_DIR / "waec"
EXHAUSTED = "EXH"

# WAEC party names that ``party_code`` would misread.
PARTIES = {
    "(No Party Designation)": "Independent",
    "SFFPWA": "Shooters, Fishers and Farmers",
    "WAFAMILYFIRST.COM": "Family First",
}


UNALIGNED = ("(No Party Designation)", "Independent")


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=120)


def _get(client: httpx.Client, year: int, path: str) -> dict:
    dest = RAW / str(year) / (path.replace("/", "_") + ".json")
    return json.loads(_cached_get(client, f"{API}sg{year}/{path}", dest).read_text(encoding="utf-8"))


def _party_name(name: str) -> str:
    return PARTIES.get(name, name)


def _key(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def _section(group: str, venue: str) -> str:
    """Election-day polling places keep the 'Polling Places' section the notional re-cut
    matches by venue; early and mobile polling (votes from many districts) do not."""
    if group != "Polling Places":
        return "Declaration"
    if "early polling" in venue.lower():
        return "Early Polling Places"
    if venue.lower().startswith("mobile"):
        return "Mobile Polling"
    return "Polling Places"


def parse_district(results: dict, candidates: list[dict]) -> dict[str, list[dict]]:
    """Rows for one district from its ``results`` response and its candidates (full
    names and party names, from ``LACandidateSurname``)."""
    district = results["currentElectorate"]["ElectorateName"]
    by_surname: dict[str, list[dict]] = defaultdict(list)
    for c in candidates:
        by_surname[_key(c["BALLOT_PAPER_NAME"].split(",")[0])].append(c)

    names: dict[str, str] = {}  # count-table label ('SURNAME - ABBR') -> full name
    party_names: dict[str, str] = {}
    first: dict[str, int] = {}
    for c in results["resultsCandidates"]:
        surname, abbr = c["BALLOT_PAPER_NAME"].strip(), c["PARTY_AFFILIATION"] or ""
        label = f"{surname} - {abbr}" if abbr else surname
        match = by_surname.get(_key(surname), [])
        if len(match) > 1:
            # Same surname twice on one ballot (Warren-Blackwood 2013: the Nationals'
            # Terry Redman and an unaligned K. Redman): tell them apart by affiliation.
            unaligned = abbr in ("", "IND")
            match = [m for m in match if (m["PARTY_AFFILIATION"] in UNALIGNED) == unaligned] or match
        full = match[0] if match else None
        names[label] = _surname_first(full["BALLOT_PAPER_NAME"]) if full else surname
        party_names[label] = _party_name(full["PARTY_AFFILIATION"]) if full else (abbr or "Independent")
        first[label] = c["Votes_Counted"]

    def label_of(name: str) -> str:
        """Count tables write 'SURNAME - ABBR', sometimes without spaces or apostrophes
        ("t HART" for "'t HART"), or for independents only the surname."""
        if name in names:
            return name
        same = [k for k in names if _key(k) == _key(name)]
        return (same or [k for k in names if _key(k.rsplit(" - ", 1)[0]) == _key(name)])[0]

    tcp = {label_of(c["Ballot_Paper_Name"]): c["Votes_Counted"] for c in results["results2CP"]}
    elected = max(tcp, key=tcp.get)
    formal = sum(first.values())
    out: dict[str, list[dict]] = {
        "primary": [_row(district, names[k], party_names[k], v, formal, k == elected) for k, v in first.items()],
        "tcp": [_row(district, names[k], party_names[k], v, sum(tcp.values()), k == elected)
                for k, v in tcp.items()],
        "dop_transfers": [],
        "booths": [],
    }

    # Distribution k moves the excluded candidate's ballots (a negative entry) to the
    # others; whatever is not transferred exhausted.
    rounds: dict[int, dict[str, int]] = defaultdict(dict)
    for r in results["resultsFullDistribution"] or []:
        if r["DISTRIBUTION_LEVEL"].startswith("Distribution"):
            rounds[r["PREFERENCE_LEVEL"]][label_of(r["BALLOT_PAPER_NAME"])] = r["FORMAL_LAST_PUBLISHED_NUMBER_ENTERED"]
    for level in sorted(rounds):
        moves = rounds[level]
        excluded = [k for k, v in moves.items() if v < 0]
        if len(excluded) != 1:
            continue  # no exclusion recorded at this level
        k = excluded[0]
        to = [(t, v) for t, v in moves.items() if v > 0]
        exhausted = -moves[k] - sum(v for _, v in to)
        for t, v in to + ([(None, exhausted)] if exhausted > 0 else []):
            out["dop_transfers"].append({
                "district": district, "count": level + 1, "from_candidate": names[k],
                "to_candidate": names[t] if t else "Exhausted", "votes": float(v),
                "from_party": party_code(party_names[k]),
                "to_party": party_code(party_names[t]) if t else EXHAUSTED})

    informal = 0
    for pp in results["resultsPollingPlace"]:
        venue = pp["BREAKDOWN_NAME"]
        section = _section(pp["BREAKDOWN_GROUP"], venue)
        informal += int(pp.get("Informal") or 0)
        for col, v in pp.items():
            if col in ("BREAKDOWN_NAME", "BREAKDOWN_GROUP", "Informal", "Total Votes"):
                continue
            k = label_of(col)
            out["booths"].append({"district": district, "section": section, "venue": venue,
                                  "candidate": names[k], "party": party_code(party_names[k]),
                                  "votes": int(v or 0)})
    top = results["toptotals"]
    out["districts"] = [{"district": district, "elected": names[elected],
                         "elected_party_name": party_names[elected],
                         "elected_party": party_code(party_names[elected]),
                         "enrolment": top.get("NUMBER_ELECTORS"), "formal": formal,
                         "informal": top.get("INFORMAL_LAST_PUBLISHED_NUMBER_ENTERED", informal)}]
    return out


def ingest_waec_assembly(year: int) -> dict[str, pl.DataFrame]:
    """Districts, first preferences, polling-place votes, two-candidate counts, Labor v
    Coalition 2PP (where those were the final two) and preference transfers."""
    rows: dict[str, list[dict]] = {}
    with _client() as client:
        cands = _get(client, year, "LACandidateSurname")["LACandidateSurname"]
        by_district: dict[str, list[dict]] = defaultdict(list)
        for c in cands:
            by_district[c["ELECTORATE_CODE"]].append(c)
        for code in sorted(by_district):
            res = _get(client, year, f"{code}/results")
            for k, v in parse_district(res, by_district[code]).items():
                rows.setdefault(k, []).extend(v)
    return _tables(rows, f"wa-{year}")
