"""Northern Territory Legislative Assembly results, from Wikipedia's "Results of the
{year} Northern Territory general election" articles.

The NT Electoral Commission's site refuses automated requests, so the per-seat results
come from these articles, which transcribe the NTEC's counts (and cite them): one
election box per division with first preferences, the two-candidate count, Antony
Green's Labor v CLP two-party estimate where the final two were not Labor and the CLP,
and whether the seat was held or gained.

After a redistribution (2023, for the 2024 election) the boxes' "change" figures are
against the notional result on the new boundaries. ``notional_from_changes`` turns them
back into the previous election's notional first preferences and holder per seat, for
parties standing at both elections; the rest of the notional vote is "Others".

Pages are cached under ``data/raw/wikipedia/nt-results-{year}.wiki``.
"""

from __future__ import annotations

import re

import polars as pl

from prophecy import RAW_DIR
from prophecy.ingest.polls import fetch_wikitext
from prophecy.schema.parties import bloc, party_code

TITLE = "Results of the {year} Northern Territory general election"
# Party labels in the election boxes that ``party_code`` would misread.
PARTIES = {"Labor NT": "ALP", "CLP": "CLP", "Greens NT": "GRN", "Independent": "IND",
           "Territory Alliance": "TA", "Federation": "FED"}


def _num(text: str) -> float | None:
    t = text.replace(",", "").replace("−", "-").replace("–", "-").strip()
    try:
        return float(t)
    except ValueError:
        return None


def _field(block: str, name: str) -> str:
    m = re.search(rf"\|\s*{name}\s*=\s*(.*)", block)
    return m.group(1).strip() if m else ""


def _plain(text: str) -> str:
    """Wiki link markup to text: '[[Damien Ryan (politician)|Damien Ryan]]' -> 'Damien Ryan'."""
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"<ref.*?(</ref>|/>)|\{\{efn.*?\}\}", "", text)
    return " ".join(text.split())


def _name(full: str) -> str:
    """'Robyn Lambley' -> 'LAMBLEY Robyn' (surname first, in capitals, as elsewhere)."""
    words = _plain(full).split()
    if len(words) < 2:
        return full.upper()
    return " ".join([words[-1].upper(), *words[:-1]])


def _code(party: str) -> str:
    return PARTIES.get(party, party_code(party))


def _candidates(section: str) -> list[dict]:
    out = []
    for m in re.finditer(r"\{\{Election box candidate AU party(.*?)\n\}\}", section, flags=re.S):
        b = m.group(1)
        party = _plain(_field(b, "party"))
        out.append({"candidate": _name(_field(b, "candidate")), "party_name": party, "party": _code(party),
                    "votes": int(_num(_field(b, "votes")) or 0), "pct": _num(_field(b, "percentage")),
                    "change": _num(_field(b, "change"))})
    return out


def parse_division(name: str, box: str) -> dict:
    """Primaries, two-candidate count, Labor v CLP 2PP and result of one division's box."""
    two_cp = box.find("Election box 2cp")
    two_pp = box.find("Election box 2pp")
    first_end = min(i for i in (two_cp, two_pp, box.find("Election box formal")) if i >= 0)
    primary = _candidates(box[:first_end])
    tcp = _candidates(box[two_cp:]) if two_cp >= 0 else []
    tpp = _candidates(box[two_pp:two_cp if two_cp > two_pp else len(box)]) if two_pp >= 0 else []
    formal = re.search(r"Election box formal(.*?)\}\}", box, flags=re.S)
    informal = re.search(r"Election box informal(.*?)\}\}", box, flags=re.S)
    result = re.search(r"Election box (hold|gain) AU party(.*?)\}\}", box, flags=re.S)
    winner_party = _plain(_field(result.group(2), "winner")) if result else ""
    loser_party = _plain(_field(result.group(2), "loser")) if result else ""
    if not tcp:  # final two were Labor and the CLP: the 2PP box is the count
        tcp = tpp
    if not tcp and len(primary) == 2:  # two candidates: the first preferences decide
        tcp = primary
    elected = max(tcp, key=lambda r: r["votes"]) if tcp else max(primary, key=lambda r: r["votes"])
    return {
        "district": name, "primary": primary, "tcp": tcp, "tpp": tpp,
        "formal": int(_num(_field(formal.group(1), "votes")) or 0) if formal else sum(r["votes"] for r in primary),
        "informal": int(_num(_field(informal.group(1), "votes")) or 0) if informal else None,
        "elected": elected, "held": result.group(1) == "hold" if result else None,
        "previous_holder": _code(loser_party if result and result.group(1) == "gain" else winner_party),
    }


def divisions(wikitext: str) -> list[dict]:
    """Every division's parsed box, in article order."""
    out = []
    for m in re.finditer(r"^===\s*(.+?)\s*===\s*$", wikitext, flags=re.M):
        start = m.end()
        end = wikitext.find("Election box end", start)
        box = wikitext[start:end]
        if "Election box begin" not in box:
            continue
        out.append(parse_division(_plain(m.group(1)), box))
    return out


def _rows(division: dict, key: str, eid: str) -> list[dict]:
    total = sum(r["votes"] for r in division[key]) or 1
    win = division["elected"]["candidate"]
    return [{"election_id": eid, "district": division["district"], "candidate": r["candidate"],
             "party_name": r["party_name"], "party": r["party"], "bloc": bloc(r["party"]),
             "votes": r["votes"], "pct": round(100 * r["votes"] / total, 3),
             "elected": r["candidate"] == win} for r in division[key]]


def ingest_nt_assembly(year: int, refresh: bool = True) -> dict[str, pl.DataFrame]:
    eid = f"nt-{year}"
    path = RAW_DIR / "wikipedia" / f"nt-results-{year}.wiki"
    if refresh or not path.exists():
        fetch_wikitext(TITLE.format(year=year), path)
    divs = divisions(path.read_text(encoding="utf-8"))
    primary = [r for d in divs for r in _rows(d, "primary", eid)]
    tcp = [r for d in divs for r in _rows(d, "tcp", eid)]
    tpp = []
    for d in divs:
        v = {bloc(r["party"]): r["votes"] for r in d["tpp"] or d["tcp"]}
        if set(v) >= {"ALP", "COAL"}:
            tpp.append({"election_id": eid, "district": d["district"],
                        "tpp_method": "2CP" if not d["tpp"] else "estimate",
                        "alp_votes": v["ALP"], "coal_votes": v["COAL"],
                        "alp_tpp": round(100 * v["ALP"] / (v["ALP"] + v["COAL"]), 3)})
    districts = [{"election_id": eid, "district": d["district"], "elected": d["elected"]["candidate"],
                  "elected_party_name": d["elected"]["party_name"], "elected_party": d["elected"]["party"],
                  "enrolment": None, "formal": d["formal"], "informal": d["informal"],
                  "previous_holder": d["previous_holder"]} for d in divs]
    changes = [{"election_id": eid, "district": d["district"], "candidate": r["candidate"], "party": r["party"],
                "pct": r["pct"], "change": r["change"]} for d in divs for r in d["primary"]]
    tables = {"primary": pl.DataFrame(primary), "tcp": pl.DataFrame(tcp), "final": pl.DataFrame(tcp),
              "tpp": pl.DataFrame(tpp), "districts": pl.DataFrame(districts),
              "primary_changes": pl.DataFrame(changes)}
    return tables


def notional_from_changes(election_id: str, previous_districts: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """The previous result on this election's boundaries, from the boxes' changes.

    Each party standing at both elections gets its notional share (share minus change);
    the rest of the notional vote is Others. A minor-party member's vote (Territory
    Alliance in 2020) counts as independent, as in the other states' baselines. The
    notional holder is the party the seat was held by or gained from."""
    from prophecy import DATA_DIR

    src = DATA_DIR / "processed" / election_id
    ch = pl.read_csv(src / "primary_changes.csv")
    districts = pl.read_csv(src / "districts.csv")
    prev_members = dict(previous_districts.select("district", "elected").iter_rows())
    prev_party = dict(previous_districts.select("district", "elected_party").iter_rows())
    rows, drows = [], []
    for d in districts.iter_rows(named=True):
        name = d["district"]
        c = ch.filter((pl.col("district") == name) & pl.col("change").is_not_null())
        shares: dict[str, float] = {}
        for r in c.iter_rows(named=True):
            notional = max(r["pct"] - r["change"], 0.0)
            shares[r["party"]] = shares.get(r["party"], 0.0) + notional
        holder = d["previous_holder"]
        member_is_minor = bloc(prev_party.get(name, "")) == "OTH"
        others = max(100.0 - sum(shares.values()), 0.0)
        shares["OTH"] = shares.get("OTH", 0.0) + others
        for party, pct in shares.items():
            b = bloc(party) if party != "OTH" else "OTH"
            if member_is_minor and party == prev_party.get(name):
                b = "IND"  # the member's own (personal) vote
            rows.append({"district": name, "candidate": f"{party} (notional)", "party": party, "bloc": b,
                         "votes": round(d["formal"] * pct / 100), "pct": round(pct, 3)})
        same_seat = name in prev_members
        drows.append({"district": name, "elected_party": holder,
                      "elected": prev_members.get(name) if same_seat and prev_party.get(name) == holder else None,
                      "main_origin": name if same_seat else None, "origin_share": 1.0 if same_seat else 0.0,
                      "formal": d["formal"]})
    return {"primary": pl.DataFrame(rows), "districts": pl.DataFrame(drows)}
