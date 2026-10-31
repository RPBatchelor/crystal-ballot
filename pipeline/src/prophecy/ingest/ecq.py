"""Ingest Queensland Legislative Assembly results from the Electoral Commission of
Queensland (ECQ).

The ECQ's results system publishes each event's final results as one XML file (the
"XML media feed", archived as a zip and listed in ``elections.json``). Per district it
has the official first-preference count with votes by booth, and the full distribution
of preferences: which candidate was excluded at each count and where their ballots went,
ending in the two-candidate count. Cached under ``data/raw/ecq``.

Elections before 2020 are on the ECQ's legacy results site (``LEGACY``): one page per
district with first preferences by booth and a summary of the distribution of
preferences (who was excluded at each count, where their ballots went, and how many
exhausted). Cached under ``data/raw/ecq/legacy/{year}``.

Queensland used optional preferential voting until 2016 (the 2012 and 2015 elections), so
ballots then exhausted in large numbers; since 2017 voting is full preferential and
exhausted ballots are negligible. Both are kept as transfers to ``EXH``.
"""

from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import httpx
import polars as pl

from prophecy import RAW_DIR
from prophecy.ingest.vec import USER_AGENT, _cached_get
from prophecy.schema.parties import bloc, party_code

BASE = "https://resultsdata.elections.qld.gov.au/"
LEGACY = "https://results.ecq.qld.gov.au/elections/state/State{year}/results/"
RAW = RAW_DIR / "ecq"
FIRST_PREFERENCES = "Official First Preference Count"
DISTRIBUTION = "Official Distribution of Preferences Count"
EXHAUSTED = "EXH"


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE, headers={"User-Agent": USER_AGENT},
                        follow_redirects=True, timeout=120)


def _events() -> list[dict]:
    with _client() as client:
        path = _cached_get(client, "elections.json", RAW / "elections.json")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data["elections"] if isinstance(data, dict) and "elections" in data else list(data.values())


def download(year: int) -> Path:
    """The XML results feed for the ``year`` state general election."""
    event = next(e for e in _events()
                 if e["electionType"] == "State General" and e["electionDay"].startswith(str(year)))
    dest = RAW / str(year) / "publicResults.xml"
    if dest.exists():
        return dest
    with _client() as client:
        z = _cached_get(client, event["archiveXML"], RAW / Path(event["archiveXML"]).name, binary=True)
    with zipfile.ZipFile(io.BytesIO(z.read_bytes())) as zf:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read("publicResults.xml"))
    return dest


def _name(ballot_name: str) -> str:
    """'ENOCH, Leeanne' -> 'ENOCH Leeanne' (surname first, as in the other ingests)."""
    return " ".join(ballot_name.replace(",", " ").split())


def _count(el: ET.Element | None) -> int:
    return int(el.findtext("count") or 0) if el is not None else 0


def _round(district: ET.Element, name: str) -> ET.Element:
    return next(r for r in district.findall("countRound") if r.get("countName") == name)


def parse_district(d: ET.Element) -> dict[str, list[dict]]:
    """Rows for one ``<district>`` element of the feed."""
    name = d.get("districtName")
    cands = {c.get("ballotOrderNumber"): c for c in d.find("candidates").findall("candidate")}
    party_name = {k: c.get("party") or "Independent" for k, c in cands.items()}
    code = {k: party_code(v) for k, v in party_name.items()}
    elected = d.find("declaredCandidate").get("ballotOrderNumber")

    def cand_row(c: ET.Element, votes: int, total: int) -> dict:
        k = c.get("ballotOrderNumber")
        return {"district": name, "candidate": _name(c.get("ballotName")),
                "party_name": party_name[k], "party": code[k], "bloc": bloc(code[k]),
                "votes": votes, "pct": round(100 * votes / total, 3) if total else None,
                "elected": k == elected}

    fp = _round(d, FIRST_PREFERENCES)
    prim = fp.find("primaryVoteResults").findall("candidate")
    formal = sum(_count(c) for c in prim)
    out: dict[str, list[dict]] = {
        "districts": [{
            "district": name, "elected": _name(cands[elected].get("ballotName")),
            "elected_party_name": party_name[elected], "elected_party": code[elected],
            "enrolment": int(d.get("enrolment") or 0) or None, "formal": formal,
            "informal": _count(fp.find("totalInformalVotes")),
        }],
        "primary": [cand_row(c, _count(c), formal) for c in prim],
        "booths": [],
        "tcp": [],
        "dop_transfers": [],
    }
    for b in fp.find("booths").findall("booth"):
        for c in b.find("primaryVoteResults").findall("candidate"):
            k = c.get("ballotOrderNumber")
            out["booths"].append({"district": name, "section": b.get("typeDescription"),
                                  "venue": b.get("name"), "candidate": _name(c.get("ballotName")),
                                  "party": code[k], "votes": _count(c)})

    dop = _round(d, DISTRIBUTION)
    tcp = dop.find("twoCandidateVotes").findall("candidate")
    tcp_total = sum(_count(c) for c in tcp)
    out["tcp"] = [cand_row(c, _count(c), tcp_total) for c in tcp]
    for dist in dop.find("preferenceDistributionSummary").findall("preferenceDistribution"):
        k = dist.get("excludedBallotOrder")
        count = int(dist.get("distribution")) + 1  # count 1 is the first preferences
        moves = [(c.get("ballotOrderNumber"), _count(c)) for c in dist.findall("candidatePreferences")]
        moves.append((None, _count(dist.find("exhausted"))))
        for to, votes in moves:
            if votes:
                out["dop_transfers"].append({
                    "district": name, "count": count,
                    "from_candidate": _name(dist.get("excludedBallotName")),
                    "to_candidate": _name(cands[to].get("ballotName")) if to else "Exhausted",
                    "votes": float(votes), "from_party": code[k],
                    "to_party": code[to] if to else EXHAUSTED})
    return out


def ingest_ecq_assembly(year: int) -> dict[str, pl.DataFrame]:
    """Districts, first preferences, booths, two-candidate counts, Labor v LNP 2PP (where
    that was the final count) and preference transfers for one state election."""
    if year < 2020:
        return ingest_ecq_legacy(year)
    root = ET.parse(download(year)).getroot()
    election = next(e for e in root.findall("election") if e.get("eventType") == "State General")
    rows: dict[str, list[dict]] = {}
    for d in election.find("districts").findall("district"):
        for k, v in parse_district(d).items():
            rows.setdefault(k, []).extend(v)
    return _tables(rows, f"qld-{year}")


def _tables(rows: dict[str, list[dict]], eid: str) -> dict[str, pl.DataFrame]:
    """Row lists to tables, plus the Labor v LNP 2PP where those were the final two."""
    tables = {k: pl.DataFrame(v).with_columns(pl.lit(eid).alias("election_id"))
              for k, v in rows.items()}
    tables = {k: df.select("election_id", *[c for c in df.columns if c != "election_id"])
              for k, df in tables.items()}
    tcp = tables["tcp"]
    classic = (tcp.group_by("district").agg(pl.col("bloc"), pl.col("votes"))
               .filter(pl.col("bloc").list.sort() == ["ALP", "COAL"]))
    tpp = []
    for d, blocs, votes in classic.sort("district").iter_rows():
        v = dict(zip(blocs, votes))
        tpp.append({"election_id": eid, "district": d, "tpp_method": "2CP",
                    "alp_votes": v["ALP"], "coal_votes": v["COAL"],
                    "alp_tpp": round(100 * v["ALP"] / (v["ALP"] + v["COAL"]), 3)})
    tables["tpp"] = pl.DataFrame(tpp)
    tables["final"] = tcp
    return tables


# --------------------------------------------------------------------------------------
# Legacy results site (2012-2017)
# --------------------------------------------------------------------------------------

# Party abbreviations on the legacy pages, to names ``party_code`` understands.
LEGACY_PARTIES = {
    "ALP": "Australian Labor Party", "LNP": "Liberal National Party of Queensland",
    "GRN": "Queensland Greens", "ONP": "Pauline Hanson's One Nation",
    "KAP": "Katter's Australian Party", "PUP": "Palmer United Party", "FFP": "Family First Party",
    "IND": "Independent", "CR": "Civil Liberties, Consumer Rights, No-Tolls",
}


class _NestedTables(HTMLParser):
    """Every <table> on a page (nested ones included) as rows of (text, image sources) cells."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[tuple[str, list[str]]]]] = []
        self._stack: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append({"rows": [], "row": None, "cell": None})
        if not self._stack:
            return
        top = self._stack[-1]
        if tag == "tr":
            top["row"] = []
        elif tag in ("td", "th") and top["row"] is not None:
            top["cell"] = ([], [])
        elif tag == "br" and top["cell"] is not None:
            top["cell"][0].append(" ")
        elif tag == "img" and top["cell"] is not None:
            top["cell"][1].append(dict(attrs).get("src") or "")

    def handle_endtag(self, tag):
        if not self._stack:
            return
        top = self._stack[-1]
        if tag in ("td", "th") and top["cell"] is not None and top["row"] is not None:
            text, imgs = top["cell"]
            top["row"].append((" ".join("".join(text).split()), imgs))
            top["cell"] = None
        elif tag == "tr" and top["row"] is not None:
            top["rows"].append(top["row"])
            top["row"] = None
        elif tag == "table":
            self.tables.append(self._stack.pop()["rows"])

    def handle_data(self, data):
        if self._stack and self._stack[-1]["cell"] is not None:
            self._stack[-1]["cell"][0].append(data)


def _num(text: str) -> int | None:
    t = text.replace(",", "").strip()
    return int(t) if re.fullmatch(r"\d+", t) else None


def _legacy_candidate(header: str) -> tuple[str, str]:
    """'BOOTHMAN, Mark LNP' -> ('BOOTHMAN Mark', 'LNP'); independents have no
    abbreviation ('BOLTON, Sandy' -> ('BOLTON Sandy', 'IND'))."""
    parts = header.split()
    given = header.split(",", 1)[1].split() if "," in header else parts[1:]
    # No abbreviation: the last word is a given name or initials ('DAVISON, BJ').
    if len(given) < 2 or not re.fullmatch(r"[A-Z0-9]{2,6}", parts[-1]):
        parts.append("IND")
    return " ".join(" ".join(parts[:-1]).replace(",", " ").split()), parts[-1]


def parse_legacy_booth_page(page: str, district: str) -> dict[str, list[dict]]:
    """Rows for one district from its legacy "Booth Details" page: first preferences
    by booth, and the summary of the distribution of preferences."""
    p = _NestedTables()
    p.feed(page)
    dop = next(t for t in p.tables if t and t[0] and t[0][0][0] == "Summary of Distribution of Preferences")
    booths = next(t for t in p.tables if len(t) > 2 and t[1] and t[1][0][0] == "No.")

    cands = []
    for text, imgs in dop[1][1:]:
        if not text or "Remaining" in text or text in ("Exhausted", "Total Formal Votes"):
            continue
        name, abbrev = _legacy_candidate(text)
        party_name = LEGACY_PARTIES.get(abbrev, abbrev)
        cands.append({"name": name, "party_name": party_name, "party": party_code(party_name),
                      "elected": any("tick" in i for i in imgs)})
    n = len(cands)

    def counts(row) -> tuple[list[int | None], int | None]:
        """Candidate votes (the first of each votes/% pair) and exhausted ballots."""
        cells = [c[0] for c in row[1:]]
        exhausted = _num(cells[2 * n + 1]) if len(cells) > 2 * n + 1 else None
        return [_num(cells[2 * i]) for i in range(n)], exhausted

    def cand_row(c: dict, votes: int, total: int) -> dict:
        return {"district": district, "candidate": c["name"], "party_name": c["party_name"],
                "party": c["party"], "bloc": bloc(c["party"]), "votes": votes,
                "pct": round(100 * votes / total, 3) if total else None, "elected": c["elected"]}

    body = [r for r in dop[2:] if r and r[0][0]]
    label = {r[0][0]: r for r in body}
    first, _ = counts(label["First Preference Votes"])
    final, _ = counts(label["District Total"])
    formal = sum(v or 0 for v in first)
    final_total = sum(v or 0 for v in final)
    out: dict[str, list[dict]] = {
        "primary": [cand_row(c, v or 0, formal) for c, v in zip(cands, first)],
        "tcp": [cand_row(c, v, final_total) for c, v in zip(cands, final) if v is not None],
        "dop_transfers": [],
        "booths": [],
    }
    standing = [v is not None for v in first]
    count = 1
    for row in body:
        if not row[0][0].endswith("Excluded"):
            continue
        count += 1
        votes, exhausted = counts(row)
        # The excluded candidate: still standing, but with no votes in their own row.
        gone = [i for i in range(n) if standing[i] and votes[i] is None]
        if len(gone) != 1:
            raise ValueError(f"{district}: cannot tell who was excluded at count {count} ({row[0][0]})")
        k = gone[0]
        standing[k] = False
        moves: list[tuple[dict | None, int]] = [(cands[i], v) for i, v in enumerate(votes) if v]
        if exhausted:
            moves.append((None, exhausted))
        for to, v in moves:
            out["dop_transfers"].append({
                "district": district, "count": count, "from_candidate": cands[k]["name"],
                "to_candidate": to["name"] if to else "Exhausted", "votes": float(v),
                "from_party": cands[k]["party"], "to_party": to["party"] if to else EXHAUSTED})

    for row in booths[2:]:
        cells = [c[0] for c in row]
        if len(cells) < 2 * n + 4 or _num(cells[0]) is None:
            continue
        venue = cells[1]
        section = ("Postal" if "Postal" in venue else "Pre-Poll" if "Pre-Poll" in venue
                   else "Declaration" if "Centre" in venue or "Voting" in venue else "Polling Booth")
        for i, c in enumerate(cands):
            out["booths"].append({"district": district, "section": section, "venue": venue,
                                  "candidate": c["name"], "party": c["party"],
                                  "votes": _num(cells[2 + 2 * i]) or 0})
    winner = next(c for c in cands if c["elected"])
    out["districts"] = [{"district": district, "elected": winner["name"],
                         "elected_party_name": winner["party_name"], "elected_party": winner["party"],
                         "enrolment": None, "formal": formal, "informal": None}]
    return out


def parse_legacy_district_page(page: str) -> dict[str, int | None]:
    """Enrolment and informal votes from a legacy "District Summary" page (the booth
    table leaves out some declaration votes)."""
    p = _NestedTables()
    p.feed(page)
    cells = {}
    for t in p.tables:
        for r in t:
            text = [c[0] for c in r]
            while text and not text[0]:
                text = text[1:]
            if text:
                cells.setdefault(text[0], text[1:])
    enrolment = cells.get("Electors at Close of Roll:", [""])[0]
    informal = cells.get("Total Informal", [""])[0]
    return {"enrolment": _num(enrolment), "informal": _num(informal)}


def ingest_ecq_legacy(year: int) -> dict[str, pl.DataFrame]:
    """A state election from the legacy results site (2012, 2015, 2017)."""
    base = LEGACY.format(year=year)
    raw = RAW / "legacy" / str(year)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=120) as client:
        summary = _cached_get(client, base + "summary.html", raw / "summary.html").read_text(encoding="utf-8")
        links = dict(re.findall(r'href="district(\d+)\.html"[^>]*>\s*([^<]+?)\s*<', summary))
        rows: dict[str, list[dict]] = {}
        for num, district in sorted(links.items(), key=lambda kv: int(kv[0])):
            page = _cached_get(client, base + f"booth{num}.html", raw / f"booth{num}.html")
            out = parse_legacy_booth_page(page.read_text(encoding="utf-8"), district)
            summary_page = _cached_get(client, base + f"district{num}.html", raw / f"district{num}.html")
            out["districts"][0].update(parse_legacy_district_page(summary_page.read_text(encoding="utf-8")))
            for k, v in out.items():
                rows.setdefault(k, []).extend(v)
    return _tables(rows, f"qld-{year}")
