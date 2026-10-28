"""Publish historical election results as JSON for the website."""

from __future__ import annotations

import json
import re

import polars as pl

from prophecy import DATA_DIR, WEB_DATA_DIR
from prophecy.jurisdictions import Election
from prophecy.schema.parties import bloc

PROCESSED = DATA_DIR / "processed"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def publish_results(election: Election) -> str:
    src = PROCESSED / election.election_id
    districts = pl.read_csv(src / "districts.csv")
    primary = pl.read_csv(src / "primary.csv")
    tcp = pl.read_csv(src / "tcp.csv")
    tpp = pl.read_csv(src / "tpp.csv")
    dop_path = src / "dop_transfers.csv"
    dop = pl.read_csv(dop_path) if dop_path.exists() else None
    by_path = PROCESSED / f"{election.election_id}-by-elections"
    by_elections = _by_elections(by_path) if by_path.exists() else {}

    seats = []
    for d in districts.sort("district").iter_rows(named=True):
        name = d["district"]
        p = primary.filter(pl.col("district") == name).sort("votes", descending=True)
        t = tcp.filter(pl.col("district") == name).sort("votes", descending=True)
        tp = tpp.filter(pl.col("district") == name)
        estimated = t.height < 2
        if estimated:
            # Archived seats without a 2CP count: approximate from the leading two
            # candidates of the final count (or first preferences), renormalised.
            final = pl.read_csv(src / "final.csv").filter(pl.col("district") == name)
            source = final if final.height >= 2 else p
            t = source.sort("votes", descending=True).head(2)
            t = t.with_columns((100 * pl.col("votes") / pl.col("votes").sum()).round(3).alias("pct"))
        winner, runner_up = t.row(0, named=True), t.row(1, named=True)
        seat = {
            "name": name,
            "slug": slugify(name),
            "elected": d["elected"],
            "party": d["elected_party"],
            "enrolment": d["enrolment"],
            "formal": d["formal"],
            "informal": d["informal"],
            "primary": [_cand(r) for r in p.iter_rows(named=True)],
            "tcp": [_cand(r) for r in t.iter_rows(named=True)],
            # Margin = winner's 2CP share minus 50.
            "margin": round(winner["pct"] - 50, 2),
            "tcp_estimated": estimated,
            "runner_up_party": runner_up["party"],
            "tpp_alp": tp["alp_tpp"][0] if tp.height else None,
            "tpp_method": tp["tpp_method"][0] if tp.height else None,
            "classic": {bloc(winner["party"]), bloc(runner_up["party"])} == {"ALP", "COAL"},
            "has_dop": dop is not None and dop.filter(pl.col("district") == name).height > 0,
            "by_election": by_elections.get(name),
        }
        seats.append(seat)

    totals = primary.group_by("bloc").agg(pl.col("votes").sum())
    total_votes = totals["votes"].sum()
    # Official statewide 2PP where known; summing seat 2PPs misses non-classic seats in
    # years when the EC published no full statewide figure.
    official = PROCESSED / f"election_results_{election.jurisdiction.lower()}.csv"
    official_tpp = None
    if official.exists():
        row = pl.read_csv(official).filter(pl.col("year") == election.date.year)
        official_tpp = row["tpp_alp_vs_coal"][0] if row.height else None
    seat_tpp = 100 * tpp["alp_votes"].sum() / (tpp["alp_votes"].sum() + tpp["coal_votes"].sum())
    payload = {
        "election_id": election.election_id,
        "jurisdiction": election.jurisdiction,
        "date": election.date.isoformat(),
        "seats_total": election.seats,
        "majority": election.seats // 2 + 1,
        "seat_counts": dict(districts["elected_party"].value_counts().iter_rows()),
        "primary_share": {
            b: round(100 * v / total_votes, 2) for b, v in totals.sort("votes", descending=True).iter_rows()
        },
        "party_share": {
            p: round(100 * v / total_votes, 2)
            for p, v in primary.group_by("party").agg(pl.col("votes").sum()).iter_rows()
        },
        "tpp_alp": round(official_tpp if official_tpp is not None else seat_tpp, 2),
        "seats": seats,
    }
    out_dir = WEB_DATA_DIR / election.jurisdiction.lower() / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{election.date.year}.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    if dop is not None:
        _publish_dop(dop, out_dir / f"{election.date.year}-preferences.json")
    return str(out)


def _cand(r: dict) -> dict:
    return {"candidate": r["candidate"], "party": r["party"], "party_name": r["party_name"],
            "votes": r["votes"], "pct": r["pct"]}


def _by_elections(path) -> dict[str, dict]:
    districts = pl.read_csv(path / "districts.csv", try_parse_dates=True)
    primary = pl.read_csv(path / "primary.csv")
    tcp = pl.read_csv(path / "tcp.csv")
    out = {}
    for d in districts.iter_rows(named=True):
        name = d["district"]
        t = tcp.filter(pl.col("district") == name).sort("votes", descending=True)
        out[name] = {
            "date": str(d["date"]),
            "elected": d["elected"],
            "party": d["elected_party"],
            "primary": [_cand(r) for r in primary.filter(pl.col("district") == name)
                        .sort("votes", descending=True).iter_rows(named=True)],
            "tcp": [_cand(r) for r in t.iter_rows(named=True)],
        }
    return out


def _publish_dop(dop: pl.DataFrame, out) -> None:
    """Per-seat exclusion sequence: who was excluded at each count and where votes went."""
    seats: dict[str, list] = {}
    for (district,), g in dop.filter(pl.col("count") > 0).group_by("district", maintain_order=True):
        counts = []
        for (count,), c in g.group_by("count", maintain_order=True):
            first = c.row(0, named=True)
            total = c["votes"].sum()
            counts.append({
                "count": count,
                "excluded": first["from_candidate"],
                "excluded_party": first["from_party"],
                "votes": total,
                "to": [{"candidate": r["to_candidate"], "party": r["to_party"], "votes": r["votes"],
                        "pct": round(100 * r["votes"] / total, 1) if total else 0}
                       for r in c.sort("votes", descending=True).iter_rows(named=True)],
            })
        seats[slugify(district)] = sorted(counts, key=lambda x: x["count"])
    out.write_text(json.dumps(seats, indent=1), encoding="utf-8")
