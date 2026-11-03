"""Ingest Tasmanian House of Assembly results from the Tasmanian Electoral Commission
(TEC).

Tasmania elects its House of Assembly by Hare-Clark proportional representation: five
divisions (the federal divisions' boundaries) each elect five members (2014-2021) or
seven (since 2024), with candidates grouped by party on the ballot. So every division
has several winners, and the tables differ from the single-member states':

* ``primary``: first preferences by candidate, with party group and whether elected.
* ``members``: one row per member elected, in order of election.
* ``districts``: one row per division: seats, quota, formal votes, enrolment, and the
  winners (joined), for the pages that expect one row per district.
* ``booths``: first preferences by polling place (2021 on).

Sources, by election (cached under ``data/raw/tec/{year}``):

* The final distribution of preferences for each division (``dist-{division}-m.html``,
  a fragment the results pages include; for 2018 the division's results page): candidates
  by group, the order they were elected, and the sitting members.
* First preferences by polling place (one workbook, a sheet per division) from 2021; for
  2018 the first-preferences section of the division's results page.

Denison was renamed Clark in 2017; 2018 results are filed under Denison and are read into
Clark so divisions line up across elections.
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

SITE = "https://www.tec.tas.gov.au/house-of-assembly/"
RAW = RAW_DIR / "tec"
DIVISIONS = ["Bass", "Braddon", "Clark", "Franklin", "Lyons"]
SEATS = {2018: 5, 2021: 5, 2024: 7, 2025: 7}
DIST = {
    2025: "elections-2025/results/{d}/dist-{d}-m.html",
    2024: "elections-2024/results/{d}/dist-{d}-m.html",
    2021: "StateElection2021/results/{d}/dist-{d}-m.html",
    2018: "StateElection2018/Results/{D}/index.html",
}
FIRST_PREFERENCES = {
    2025: "elections-2025/results/downloads/2025-state-election-first-preferences-by-polling-places.xlsx",
    2024: "elections-2024/results/pdf/2024-state-election-first-preferences-by-polling-places.xlsx",
    2021: "StateElection2021/results/assets/2021-State-election-first-preferences-by-polling-places.xlsx",
}
# Unregistered groups ("Group E") and ungrouped candidates stand as independents.
INDEPENDENT_GROUP = re.compile(r"^(group [a-z]+|ungrouped)$", re.IGNORECASE)
# Tasmania's Nationals (from 2025) run separately from, and against, the Liberals; the
# model counts them with other minor parties rather than as part of the Coalition vote.
STATE_BLOC = {"NAT": "OTH"}
# "SURNAME, Given", the surname in capitals (bar a Mc/Mac prefix): group total rows in
# the workbooks ("Shooters, Fishers, Farmers TAS") have the same shape otherwise.
NAME = re.compile(r"^(?:Mc|Mac|Di|De|Le|Van|von)?[A-Z][A-Z'’\- ]*, [A-Z].*$")


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=120)


def _name(ballot: str) -> str:
    """'O'BYRNE, Michelle' -> "O'BYRNE Michelle" (surname first, as in other ingests)."""
    return " ".join(ballot.replace("’", "'").replace(",", " ").split())


def _party(group: str) -> tuple[str, str]:
    """(party name, code) for a ballot group heading."""
    if INDEPENDENT_GROUP.match(group.strip()):
        return "Independent", "IND"
    return group.strip(), party_code(group)


def _bloc(code: str) -> str:
    return STATE_BLOC.get(code, bloc(code))


def _tokens(fragment: str) -> list[str]:
    """Text of every element, in order; group headings marked with a leading '#'."""
    fragment = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", "", fragment, flags=re.S)
    fragment = re.sub(r"<h[23][^>]*>", "\x00#", fragment)
    out = []
    for t in re.split(r"<[^>]+>|\x00", fragment):
        t = " ".join(html.unescape(t).split())
        if t:
            out.append(t)
    return out


def _num(text: str) -> int | None:
    t = text.replace(",", "").replace(" ", "")
    return int(t) if t.isdigit() else None


def parse_count(fragment: str) -> list[dict]:
    """Candidates from a results fragment: group, name, votes, status, sitting member.

    Works for the final distribution (status 'Elected n' / 'Excluded' / blank) and the
    first-preferences tables (no status)."""
    toks = _tokens(fragment)
    rows, group = [], None
    for i, t in enumerate(toks):
        if t.startswith("#"):
            group = t[1:].strip()
            continue
        if group is None or not NAME.match(t):
            continue
        nxt = toks[i + 1:i + 4]
        votes = next((_num(x) for x in nxt if _num(x) is not None), None)
        if votes is None:
            continue
        status = next((x for x in nxt if x.startswith(("Elected", "Excluded"))), "")
        order = re.search(r"Elected (\d+)", status)
        rows.append({"group": group, "name": _name(t), "votes": votes,
                     "elected_order": int(order.group(1)) if order else None,
                     "sitting": toks[i - 1] == "•"})
    return rows


def _quota(fragment: str) -> int | None:
    m = re.search(r"Quota:?(?:&nbsp;|\s|<[^>]+>)*([\d, ]+\d)", fragment)
    return _num(m.group(1)) if m else None


def _first_preferences_sheet(rows: list[tuple]) -> tuple[dict[str, int], list[dict], int, int]:
    """First preferences by candidate, booth rows (venue, candidate, votes), formal and
    informal totals from one division's sheet."""
    header = next(r for r in rows if r and r[0] == "Candidates")
    venues = [v for v in header[1:] if v]
    total_col = venues.index("Total") + 1 if "Total" in venues else None
    first, booths, formal, informal = {}, [], 0, 0
    for r in rows:
        label = r[0] if r else None
        if not isinstance(label, str):
            continue
        if label.startswith("Total Formal"):
            formal = int(r[total_col] or 0)
        elif label.startswith("Informal"):
            informal = int(r[total_col] or 0)
        elif NAME.match(label.strip()):
            name = _name(label)
            first[name] = int(r[total_col] or 0)
            for v, n in zip(venues, r[1:]):
                if not str(v).startswith("Total") and n is not None:  # subtotal columns
                    booths.append({"venue": v, "candidate": name, "votes": int(n)})
    return first, booths, formal, informal


def _section(venue: str) -> str:
    v = venue.lower()
    if "pre-poll" in v or "postal" in v or "out of division" in v or "provisional" in v or "mobile" in v:
        return "Declaration"
    return "Polling Places"


def ingest_tec_assembly(year: int) -> dict[str, pl.DataFrame]:
    """Primaries, members elected, divisions and (2021 on) polling-place votes."""
    raw = RAW / str(year)
    eid = f"tas-{year}"
    primary, members, districts, booths = [], [], [], []
    with _client() as client:
        sheets = {}
        if year in FIRST_PREFERENCES:
            path = _cached_get(client, SITE + FIRST_PREFERENCES[year], raw / "first_preferences.xlsx", binary=True)
            wb = openpyxl.load_workbook(io.BytesIO(path.read_bytes()), data_only=True)
            sheets = {ws.title.strip(): list(ws.iter_rows(values_only=True)) for ws in wb.worksheets}
        for division in DIVISIONS:
            filed = "Denison" if year == 2018 and division == "Clark" else division
            url = SITE + DIST[year].format(d=filed.lower(), D=filed)
            page = _cached_get(client, url, raw / f"{division.lower()}.html").read_text(encoding="utf-8", errors="replace")
            if year == 2018:
                dist_part, fp_part = page.split("First preferences", 1)
            else:
                dist_part, fp_part = page, None
            final = parse_count(dist_part)
            if fp_part is not None:
                first = {r["name"]: r["votes"] for r in parse_count(fp_part)}
                formal = sum(first.values())
                informal = None
                div_booths = []
            else:
                first, div_booths, formal, informal = _first_preferences_sheet(sheets[division])
            missing = {r["name"] for r in final} ^ set(first)
            if missing:
                raise ValueError(f"{eid} {division}: candidates differ between count and first preferences: {missing}")
            for r in final:
                party_name, code = _party(r["group"])
                primary.append({"district": division, "candidate": r["name"], "group": r["group"],
                                "party_name": party_name, "party": code, "bloc": _bloc(code),
                                "votes": first[r["name"]], "pct": round(100 * first[r["name"]] / formal, 3),
                                "elected": r["elected_order"] is not None, "sitting": r["sitting"]})
                if r["elected_order"] is not None:
                    members.append({"district": division, "order": r["elected_order"], "candidate": r["name"],
                                    "party_name": party_name, "party": code})
            party_of = {r["candidate"]: r["party"] for r in primary if r["district"] == division}
            for b in div_booths:
                booths.append({"district": division, "section": _section(b["venue"]), "venue": b["venue"],
                               "candidate": b["candidate"], "party": party_of[b["candidate"]], "votes": b["votes"]})
            won = sorted((m for m in members if m["district"] == division), key=lambda m: m["order"])
            if len(won) != SEATS[year]:
                raise ValueError(f"{eid} {division}: {len(won)} members elected, expected {SEATS[year]}")
            districts.append({"district": division, "seats": SEATS[year], "quota": _quota(dist_part),
                              "formal": formal, "informal": informal,
                              "elected": "; ".join(m["candidate"] for m in won),
                              "elected_party": "; ".join(m["party"] for m in won)})
    tables = {"primary": pl.DataFrame(primary), "members": pl.DataFrame(members).sort("district", "order"),
              "districts": pl.DataFrame(districts)}
    if booths:
        tables["booths"] = pl.DataFrame(booths)
    return {k: df.with_columns(pl.lit(eid).alias("election_id")).select("election_id", *df.columns)
            for k, df in tables.items()}
