"""Ingest South Australian House of Assembly results from the Electoral Commission of
South Australia (ECSA).

Three sources, by election:

* 2022 and 2026: the ECSA results app's API (``API``). ``HAStatic`` lists districts,
  candidates and parties; ``HAChange`` has votes by polling place and declaration type
  and the full distribution of preferences, round by round.
* 2018: one page per district on the ECSA site (``{District}2.html``) with first
  preferences by polling place and the two-candidate-preferred count, each ending in a
  "District Total" row.
* 2014: the same tables as articles on the ECSA site, found from its past-results index.
  The site has no 2014 general-election page for Fisher (only its December 2014
  by-election), and Mawson's polling-place article repeats MacKillop's tables, so both
  come from ``data/curated/results_sa_supplement.csv``, which overrides the pages.

Pages and API responses are cached under ``data/raw/ecsa/{year}``. South Australia uses
full preferential voting for the House of Assembly.
"""

from __future__ import annotations

import json
import re
from itertools import pairwise

import httpx
import polars as pl

from prophecy import CURATED_DIR, RAW_DIR
from prophecy.ingest.ecq import _NestedTables, _num, _tables
from prophecy.ingest.vec import USER_AGENT, _cached_get
from prophecy.schema.parties import bloc, party_code

API = "https://apim-ecsa-production.azure-api.net/results-display/"
SITE = "https://www.ecsa.sa.gov.au"
RAW = RAW_DIR / "ecsa"
ELECTION_DAYS = {2022: "2022-03-19", 2026: "2026-03-21"}
PAST_2014 = "/elections/past-state-election-results?view=article&id={id}&catid=12"
INDEX_2014 = 655  # "Past state election results (2009-2015)"
EXTRA_2014 = (681, 695)  # Davenport and Frome: not linked from the index
INDEX_2018 = "/elections/past-state-election-results?view=article&id=124&catid=12"
EXHAUSTED = "EXH"

# Party abbreviations on the 2014 and 2018 pages, to names ``party_code`` understands.
PARTIES = {
    "ALP": "Australian Labor Party", "LIB": "Liberal Party", "GRN": "The Greens",
    "NAT": "The Nationals SA", "NP": "The Nationals SA", "FFP": "Family First Party", "IND": "Independent",
    "SAB": "SA-Best", "AC": "Australian Conservatives", "DIG": "Dignity Party",
    "D4D": "Dignity for Disability", "ONP": "Pauline Hanson's One Nation",
    "LDP": "Liberal Democrats", "AJP": "Animal Justice Party",
}


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=120)


def _surname_first(name: str) -> str:
    """'CASEY, Dan' or 'Dan CASEY' -> 'CASEY Dan' (surname in capitals comes first)."""
    if "," in name:
        return " ".join(name.replace(",", " ").split())
    words = name.split()
    caps = [w for w in words if w.isupper() and len(w) > 1 or w in ("DE", "VAN", "DEN")]
    rest = [w for w in words if w not in caps]
    return " ".join(caps + rest)


def _row(district: str, name: str, party_name: str, votes: int, total: int, elected: bool) -> dict:
    code = party_code(party_name)
    return {"district": district, "candidate": name, "party_name": party_name, "party": code,
            "bloc": bloc(code), "votes": votes,
            "pct": round(100 * votes / total, 3) if total else None, "elected": elected}


# --------------------------------------------------------------------------------------
# 2022 and later: the results API
# --------------------------------------------------------------------------------------

def _api(client: httpx.Client, path: str, year: int) -> dict:
    dest = RAW / str(year) / (path.replace("/", "_") + ".json")
    return json.loads(_cached_get(client, API + path, dest).read_text(encoding="utf-8"))


def _rounds(change: dict, cid_of) -> list[tuple[int | None, dict[int, int]]]:
    """The count, round by round: (candidate excluded, or None for the first preferences;
    every remaining candidate's progressive total). 2026 lists rounds with the excluded
    candidate; 2022 lists each candidate's progressive total by round instead."""
    if "finalDistribution" in change:
        out = []
        for r in sorted(change["finalDistribution"], key=lambda r: r["roundNumber"]):
            totals = {cid_of(c["candidateName"]): c["progressiveTotal"] for c in r["candidateResults"]
                      if c["progressiveTotal"] is not None}
            out.append((cid_of(r["excludedCandidateName"]) if r["roundNumber"] else None, totals))
        return out
    by_round: dict[int, dict[int, int]] = {}
    for c in change["candidates"]:
        for d in c["distributionVotes"]:
            by_round.setdefault(d["round"], {})[c["candidateId"]] = d["distributionVote"]
    rounds = [by_round[k] for k in sorted(by_round)]
    # Excluded after round k: present in round k but not in round k + 1.
    return [(None, rounds[0])] + [(next(iter(set(a) - set(b))), b) for a, b in pairwise(rounds)]


def parse_api_district(static: dict, change: dict) -> dict[str, list[dict]]:
    """Rows for one district from its ``HAStatic`` and ``HAChange`` entries."""
    district = static["districtName"]
    cands = {c["candidateId"]: c for c in static["candidates"]}
    names = {cid: _surname_first(c["candidateName"]) for cid, c in cands.items()}
    key = lambda name: frozenset(re.findall(r"[a-z']+", name.lower()))  # word order differs
    by_name = {key(c["candidateName"]): cid for cid, c in cands.items()}

    def cid_of(name: str) -> int:
        return by_name[key(name)]

    def party_name(cid: int) -> str:
        return cands[cid]["partyName"] or "Independent"

    rounds = _rounds(change, cid_of)
    first, final = rounds[0][1], rounds[-1][1]
    elected = max(final, key=final.get)
    formal, final_total = sum(first.values()), sum(final.values())
    out: dict[str, list[dict]] = {
        "primary": [_row(district, names[c], party_name(c), v, formal, c == elected) for c, v in first.items()],
        "tcp": [_row(district, names[c], party_name(c), v, final_total, c == elected) for c, v in final.items()],
        "dop_transfers": [],
        "booths": [],
    }
    for count, ((_, before), (k, after)) in enumerate(pairwise(rounds), start=2):
        moves = [(to, after[to] - before[to]) for to in after if after[to] > before[to]]
        exhausted = before[k] - sum(v for _, v in moves)
        for to, v in moves + ([(None, exhausted)] if exhausted > 0 else []):
            out["dop_transfers"].append({
                "district": district, "count": count, "from_candidate": names[k],
                "to_candidate": names[to] if to else "Exhausted", "votes": float(v),
                "from_party": party_code(party_name(k)),
                "to_party": party_code(party_name(to)) if to else EXHAUSTED})

    informal = change.get("informalDeclarationVotes") or 0
    for pp in change["pollingPlaces"]:
        informal += pp["informalVotes"] or 0
        for c in pp["pollingCandidates"]:
            out["booths"].append({"district": district, "section": pp.get("pollingPlaceTypeIdName", "PB"),
                                  "venue": pp["pollingPlaceName"], "candidate": names[c["candidateId"]],
                                  "party": party_code(party_name(c["candidateId"])),
                                  "votes": c["formalVotes"] or 0})
    for group, label in (("declarations", "declarationType"), ("absentOrdinary", "absentOrdinaryType")):
        for d in change.get(group, []):
            for c in d["candidateVotes"]:
                cid = cid_of(c["candidateFullName"])
                out["booths"].append({"district": district, "section": "Declaration", "venue": d[label],
                                      "candidate": names[cid], "party": party_code(party_name(cid)),
                                      "votes": c["votes"] or 0})
    out["districts"] = [{"district": district, "elected": names[elected],
                         "elected_party_name": party_name(elected),
                         "elected_party": party_code(party_name(elected)),
                         "enrolment": static.get("districtEnrolled"), "formal": formal, "informal": informal}]
    return out


def ingest_api(year: int) -> dict[str, list[dict]]:
    day = ELECTION_DAYS[year]
    with _client() as client:
        static = _api(client, f"HAStatic/{day}", year)
        change = _api(client, f"HAChange/{day}/0", year)
    changes = {d["districtId"]: d for d in change["districts"]}
    rows: dict[str, list[dict]] = {}
    for s in static["districts"]:
        for k, v in parse_api_district(s, changes[s["districtName"]]).items():
            rows.setdefault(k, []).extend(v)
    return rows


# --------------------------------------------------------------------------------------
# 2014 and 2018: polling-place pages
# --------------------------------------------------------------------------------------

def _candidate(header: str) -> tuple[str, str]:
    """'CHAPLEY Jo ALP' or 'CHAPLEY Jo ALP Number' -> ('CHAPLEY Jo', 'Australian Labor Party')."""
    words = header.removesuffix(" Number").split()
    return " ".join(words[:-1]).replace("`", "'"), PARTIES.get(words[-1], words[-1])


def parse_polling_place_page(page: str, district: str) -> dict[str, list[dict]]:
    """Rows for one district from a page of first preferences and the two-candidate
    count by polling place."""
    p = _NestedTables()
    p.feed(page)
    tables = [[[c[0] for c in r] for r in t] for t in p.tables if len(t) > 2]
    prim = next(t for t in tables if "Frml" in t[0])
    tcp = next(t for t in tables if t is not prim and any(r and r[0].rstrip(":") == "District Total" for r in t))
    header = prim[0]
    cands = [_candidate(h) for h in header[1:header.index("Frml")]]
    n = len(cands)
    total = next(r for r in prim if r[0] == "District Total")
    first = [_num(v) or 0 for v in total[1:n + 1]]
    formal, informal = _num(total[n + 1]), _num(total[n + 2])

    tcp_names = [_candidate(h)[0] for h in tcp[0][1:] if h and h != "%"]
    tcp_total = next(r for r in tcp if r[0].rstrip(":") == "District Total")
    tcp_votes = [_num(tcp_total[1]), _num(tcp_total[3])]  # votes, %, votes, %
    winner = tcp_names[0] if tcp_votes[0] > tcp_votes[1] else tcp_names[1]
    party_of = {name: party for name, party in cands}

    out: dict[str, list[dict]] = {
        "primary": [_row(district, c, party, v, formal, c == winner) for (c, party), v in zip(cands, first)],
        "tcp": [_row(district, c, party_of[c], v, sum(tcp_votes), c == winner)
                for c, v in zip(tcp_names, tcp_votes)],
        "dop_transfers": [],
        "booths": [],
    }
    for r in prim[1:]:
        # Skip the subtotal rows (the district total, and the sum of its polling places).
        if not r[0] or r[0].startswith(("District Total", "Polling Place Total")) or len(r) < n + 3:
            continue
        section = "Declaration" if r[0].startswith("Declaration") else "Polling Booth"
        for (c, party), v in zip(cands, r[1:n + 1]):
            out["booths"].append({"district": district, "section": section, "venue": r[0],
                                  "candidate": c, "party": party_code(party), "votes": _num(v) or 0})
    out["districts"] = [{"district": district, "elected": winner, "elected_party_name": party_of[winner],
                         "elected_party": party_code(party_of[winner]), "enrolment": None,
                         "formal": formal, "informal": informal}]
    return out


def _pages_2014(client: httpx.Client) -> list[tuple[str, str]]:
    """(district, page html) for the 2014 polling-place articles."""
    raw = RAW / "2014"
    index = _cached_get(client, SITE + PAST_2014.format(id=INDEX_2014), raw / "index.html").read_text(encoding="utf-8")
    ids = [int(i) for i, slug in re.findall(r"id=(\d+):(2014-state-election-results-[a-z-]+?polling[a-z-]*)&", index)]
    pages = []
    for i in sorted(set(ids) | set(EXTRA_2014)):
        page = _cached_get(client, SITE + PAST_2014.format(id=i), raw / f"article{i}.html").read_text(encoding="utf-8")
        title = re.search(r"2014 State Election Results ([A-Za-z ]+?)\s*-\s*Polling", page)
        pages.append((title.group(1).strip(), page))
    return pages


def _pages_2018(client: httpx.Client) -> list[tuple[str, str]]:
    raw = RAW / "2018"
    index = _cached_get(client, SITE + INDEX_2018, raw / "index.html").read_text(encoding="utf-8")
    files = sorted(set(re.findall(r'href="/html/results/2018/([A-Za-z_]+?)2\.html"', index)))
    return [(f.replace("_", " "), _cached_get(client, f"{SITE}/html/results/2018/{f}2.html", raw / f"{f}2.html")
             .read_text(encoding="utf-8")) for f in files]


def _supplement(year: int) -> dict[str, list[dict]]:
    """Curated districts missing from (or wrong on) ECSA's site: Fisher and Mawson, 2014."""
    sup = pl.read_csv(CURATED_DIR / "results_sa_supplement.csv").filter(pl.col("year") == year)
    rows: dict[str, list[dict]] = {}
    for (district,), g in sup.group_by("district"):
        formal = int(g["votes"].sum())
        tcp = g.filter(pl.col("tcp_votes").is_not_null())
        winner = g.filter(pl.col("elected")).row(0, named=True)
        rows.setdefault("primary", []).extend(
            _row(district, r["candidate"], r["party_name"], r["votes"], formal, r["elected"])
            for r in g.iter_rows(named=True))
        rows.setdefault("tcp", []).extend(
            _row(district, r["candidate"], r["party_name"], r["tcp_votes"], int(tcp["tcp_votes"].sum()), r["elected"])
            for r in tcp.iter_rows(named=True))
        rows.setdefault("districts", []).append({
            "district": district, "elected": winner["candidate"], "elected_party_name": winner["party_name"],
            "elected_party": party_code(winner["party_name"]), "enrolment": None, "formal": formal,
            "informal": winner["informal"]})
    return rows


def ingest_ecsa_assembly(year: int) -> dict[str, pl.DataFrame]:
    """Districts, first preferences, polling-place votes, two-candidate counts, Labor v
    Liberal 2PP (where those were the final two) and, from 2022, preference transfers."""
    if year in ELECTION_DAYS:
        rows = ingest_api(year)
    else:
        with _client() as client:
            pages = _pages_2014(client) if year == 2014 else _pages_2018(client)
        rows = _supplement(year)
        curated = {r["district"] for r in rows.get("districts", [])}
        for district, page in pages:
            if district in curated:
                continue
            for k, v in parse_polling_place_page(page, district).items():
                rows.setdefault(k, []).extend(v)
    if not rows.get("dop_transfers"):
        rows.pop("dop_transfers", None)
    return _tables(rows, f"sa-{year}")
