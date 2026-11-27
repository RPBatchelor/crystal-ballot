"""Election-night live poller for Victoria 2026.

Usage:
    python pipeline/scripts/live_poll_vic.py                     # one-shot update
    python pipeline/scripts/live_poll_vic.py --watch 120         # poll every 120s
    python pipeline/scripts/live_poll_vic.py --calls calls.csv   # merge manual calls

Optional CSV format for --calls (data/curated/calls_vic-2026.csv):
    slug,called_party,called_at
    hawthorn,LIB,2026-11-28T19:35:00+11:00
    bendigo-east,ALP,2026-11-28T20:10:00+11:00
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from prophecy.ingest.vec import BASE, USER_AGENT, district_links, parse_district_page
from prophecy.publish.results import slugify
from prophecy.schema.parties import bloc, party_code

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "web" / "static" / "data" / "vic" / "live" / "2026.json"
DEFAULT_INDEX = "/results/state-election-results/2026-state-election-results"


def _fetch(url: str) -> str | None:
    full = url if url.startswith("http") else f"{BASE}{url}"
    res = subprocess.run(
        ["curl.exe", "-fsSL", "-A", USER_AGENT, "--max-time", "15", full],
        capture_output=True,
    )
    if res.returncode != 0:
        return None
    return res.stdout.decode("utf-8", errors="replace")


def load_manual_calls(path: Path | None) -> dict[str, dict]:
    if not path or not path.exists():
        return {}
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            slug = (row.get("slug") or "").strip()
            party = (row.get("called_party") or "").strip().upper()
            if slug and party:
                out[slug] = {
                    "called_party": party,
                    "called_at": (row.get("called_at") or "").strip() or datetime.now(timezone.utc).isoformat(),
                }
    return out


def poll_once(index_url: str, calls_path: Path | None) -> dict:
    manual = load_manual_calls(calls_path)
    districts: list[dict] = []
    bloc_votes: dict[str, int] = {}
    total_formal = 0
    tpp_alp_sum = 0
    tpp_coal_sum = 0

    index_html = _fetch(index_url)
    links = district_links(index_html) if index_html else {}
    for name, href in sorted(links.items()):
        slug = slugify(name)
        html = _fetch(href)
        if not html:
            continue
        r = parse_district_page(html, name)
        formal = r.formal or sum(c["votes"] or 0 for c in r.primary)
        enr = r.enrolment or 0
        pct_counted = round(100 * formal / enr, 1) if enr > 0 and formal > 0 else 0.0
        total_formal += formal

        prim_by_bloc: dict[str, int] = {}
        for c in r.primary:
            b = bloc(party_code(c["party_name"]))
            v = c["votes"] or 0
            prim_by_bloc[b] = prim_by_bloc.get(b, 0) + v
            bloc_votes[b] = bloc_votes.get(b, 0) + v
        prim_pct = (
            {b: round(100 * v / formal, 1) for b, v in prim_by_bloc.items()}
            if formal > 0
            else {}
        )

        tcp = r.final if len(r.final) == 2 else r.tcp_inline
        tcp_sorted = sorted(tcp, key=lambda c: -(c["votes"] or 0)) if tcp else []
        leading = party_code(tcp_sorted[0]["party_name"]) if tcp_sorted else None
        margin = None
        if len(tcp_sorted) == 2:
            tot_tcp = (tcp_sorted[0]["votes"] or 0) + (tcp_sorted[1]["votes"] or 0)
            if tot_tcp > 0:
                margin = round(100 * (tcp_sorted[0]["votes"] or 0) / tot_tcp - 50.0, 1)

        tpp_alp = None
        if len(tcp_sorted) == 2:
            sides = {bloc(party_code(c["party_name"])): (c["votes"] or 0) for c in tcp_sorted}
            if "ALP" in sides and "COAL" in sides and (sides["ALP"] + sides["COAL"]) > 0:
                tpp_alp_sum += sides["ALP"]
                tpp_coal_sum += sides["COAL"]
                tpp_alp = round(100 * sides["ALP"] / (sides["ALP"] + sides["COAL"]), 1)

        called_party = party_code(r.elected_party) if r.elected and r.elected_party else None
        status = "called" if called_party else ("counting" if pct_counted > 0 else "uncounted")
        source = "vec"
        called_at = None
        if slug in manual:
            called_party = manual[slug]["called_party"]
            called_at = manual[slug]["called_at"]
            status = "called"
            source = "curated"
        districts.append({
            "slug": slug,
            "district": name,
            "status": status,
            "called_party": called_party,
            "leading_party": leading or called_party,
            "margin": margin,
            "pct_counted": pct_counted,
            "primary": prim_pct,
            "tpp_alp": tpp_alp,
            "called_at": called_at,
            "source": source,
        })

    # Include any manual calls even if VEC index isn't live yet
    seen = {d["slug"] for d in districts}
    for slug, info in manual.items():
        if slug not in seen:
            districts.append({
                "slug": slug,
                "status": "called",
                "called_party": info["called_party"],
                "leading_party": info["called_party"],
                "margin": None,
                "pct_counted": 100.0,
                "called_at": info["called_at"],
                "source": "curated",
            })

    seats_called = sum(1 for d in districts if d["status"] == "called")
    seats_reporting = sum(1 for d in districts if d["pct_counted"] > 0 or d["status"] == "called")
    avg_pct = round(sum(d["pct_counted"] for d in districts) / max(len(districts), 1), 1)
    sw_prim = {
        b: (round(100 * bloc_votes[b] / total_formal, 1) if total_formal > 0 and b in bloc_votes else None)
        for b in ("ALP", "COAL", "GRN", "ONP")
    }
    sw_tpp = (
        round(100 * tpp_alp_sum / (tpp_alp_sum + tpp_coal_sum), 1)
        if (tpp_alp_sum + tpp_coal_sum) > 0
        else None
    )

    payload = {
        "election_id": "vic-2026",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "final" if seats_called >= 88 else ("counting" if seats_reporting > 0 else "pre_polls"),
        "source": "vec+curated" if manual else "vec",
        "note": None,
        "seats_called": seats_called,
        "seats_reporting": seats_reporting,
        "pct_counted": avg_pct,
        "statewide_primary": sw_prim,
        "tpp_alp": sw_tpp,
        "districts": districts,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"[{payload['updated_at']}] status={payload['status']} called={seats_called} reporting={seats_reporting} -> {OUT_PATH}")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index-url", default=DEFAULT_INDEX)
    ap.add_argument("--calls", type=Path, default=ROOT / "data" / "curated" / "calls_vic-2026.csv")
    ap.add_argument("--watch", type=int, default=0, help="Poll interval in seconds (0 = one-shot)")
    args = ap.parse_args()
    while True:
        poll_once(args.index_url, args.calls)
        if args.watch <= 0:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
