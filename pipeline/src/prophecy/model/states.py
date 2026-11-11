"""State elections (New South Wales, Queensland): baselines, seat inputs and flows.

The baseline is the previous election's result. When the boundaries are unchanged
(Queensland 2020 to 2024) it is used as it is. NSW redistributes between elections (2021
for the 2023 election), so there the previous result is re-cut onto the new districts. Each election-day venue is placed in the district
where it took votes at the *next* election (venue names are stable across elections);
pre-poll, postal, iVote and other declaration votes follow the old district's venue
votes in the same proportions. This is the usual notional-results method, applied to
first preferences and to the Labor v Coalition count.

Seat inputs also use what was public before polling day: the ballot (nominations close
weeks earlier), sitting members and whether they recontest, and by-elections.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import numpy as np
import polars as pl

from prophecy import CURATED_DIR, DATA_DIR
from prophecy.jurisdictions import Election
from prophecy.model.preferences import BLOCS, IDX, calibrate_to_results, estimate_flows
from prophecy.model.simulate import SeatInputs, apply_candidates, build_inputs
from prophecy.publish.results import slugify
from prophecy.schema.parties import bloc

PROCESSED = DATA_DIR / "processed"
# South Australia: PB a polling booth, S1-S3 one shared with other districts (2022 on);
# "Polling Booth" before 2022 (and in Queensland).
ORDINARY = {"Voting Centres", "Polling Places", "Polling Booth", "PB", "S1", "S2", "S3"}
DEFECTOR_PERSONAL_VOTE = 0.5  # share of a defecting member's old primary they keep
DEFECTOR_FROM = ("ALP", "COAL", "GRN", "ONP")  # parties whose vote is not the member's own
MOSTLY_UNCHANGED = 0.8  # share of a new district's votes from one old district
NEW_COAL_SHARE = 0.15  # newcomer's share of the Coalition vote in a three-cornered contest
MIN_VENUE_SHARE = 0.02  # a district taking less of a venue's votes than this is not its catchment


def _key(venue: str) -> str:
    return re.sub(r"[^a-z0-9]", "", venue.lower())


def venue_map(prev: pl.DataFrame, new: pl.DataFrame) -> pl.DataFrame:
    """Share of each old district's votes going to each new district.

    Returns rows (old, new, share) and, per old district, the fraction of election-day
    venue votes matched to a venue at the next election (``matched``).
    """
    formal = lambda df: df.filter(pl.col("party") != "INFORMAL")
    dest = (formal(new).filter(pl.col("section").is_in(ORDINARY))
            .with_columns(pl.col("venue").map_elements(_key, return_dtype=pl.String).alias("key"))
            .group_by("key", "district").agg(pl.col("votes").sum())
            .filter(pl.col("votes").sum().over("key") > 0)  # venues that took no votes
            .with_columns((pl.col("votes") / pl.col("votes").sum().over("key")).alias("w"))
            # Absent votes for other districts taken at a venue are not its catchment.
            .filter(pl.col("w") >= MIN_VENUE_SHARE)
            .with_columns((pl.col("w") / pl.col("w").sum().over("key")).alias("w"))
            .select("key", pl.col("district").alias("new"), "w"))
    venues = (formal(prev).filter(pl.col("section").is_in(ORDINARY))
              .with_columns(pl.col("venue").map_elements(_key, return_dtype=pl.String).alias("key"))
              .group_by("district", "key").agg(pl.col("votes").sum()))
    matched = venues.join(dest, on="key", how="inner").with_columns((pl.col("votes") * pl.col("w")).alias("v"))
    share = (matched.group_by("district", "new").agg(pl.col("v").sum())
             .with_columns((pl.col("v") / pl.col("v").sum().over("district")).alias("share")))
    rate = (venues.group_by("district").agg(pl.col("votes").sum().alias("all"))
            .join(venues.join(dest.select("key").unique(), on="key", how="semi")
                  .group_by("district").agg(pl.col("votes").sum().alias("hit")), on="district", how="left")
            .select("district", (pl.col("hit").fill_null(0) / pl.col("all")).alias("matched")))
    return share.select(pl.col("district").alias("old"), "new", "share").join(
        rate.rename({"district": "old"}), on="old", how="left")


def _redistribute(votes: pl.DataFrame, by: list[str], value: str,
                  new_booths: pl.DataFrame, shares: pl.DataFrame) -> pl.DataFrame:
    """Move ``value`` columns of venue-level ``votes`` (district, section, venue, *by)
    onto new districts: matched election-day venues go where the venue now is; the
    rest follow the old district's overall shares."""
    dest = (new_booths.filter((pl.col("party") != "INFORMAL") & pl.col("section").is_in(ORDINARY))
            .with_columns(pl.col("venue").map_elements(_key, return_dtype=pl.String).alias("key"))
            .group_by("key", "district").agg(pl.col("votes").sum().alias("n"))
            .filter(pl.col("n").sum().over("key") > 0)
            .with_columns((pl.col("n") / pl.col("n").sum().over("key")).alias("w"))
            .filter(pl.col("w") >= MIN_VENUE_SHARE)
            .with_columns((pl.col("w") / pl.col("w").sum().over("key")).alias("w"))
            .select("key", pl.col("district").alias("new"), "w"))
    v = votes.with_columns(pl.col("venue").map_elements(_key, return_dtype=pl.String).alias("key"))
    is_day = pl.col("section").is_in(ORDINARY)
    direct = v.filter(is_day).join(dest, on="key", how="inner")
    rest = pl.concat([
        v.filter(is_day).join(direct.select("district", "key").unique(), on=["district", "key"], how="anti"),
        v.filter(~is_day),
    ])
    spread = rest.join(shares.rename({"old": "district", "share": "w"}), on="district", how="inner")
    cols = ["district", "new", *by, value, "w"]
    return (pl.concat([direct.select(cols), spread.select(cols)])
            .with_columns((pl.col(value) * pl.col("w")).alias(value))
            .group_by("new", "district", *by).agg(pl.col(value).sum()))


def notional_baseline(previous: Election, election: Election,
                      log: Callable[[str], None] = print) -> dict[str, pl.DataFrame]:
    """``previous``'s first preferences and Labor v Coalition 2PP on ``election``'s
    districts, with each new district's notional holder."""
    pdir, ndir = PROCESSED / previous.election_id, PROCESSED / election.election_id
    prev_booths = pl.read_csv(pdir / "booths.csv")
    new_booths = pl.read_csv(ndir / "booths.csv")
    shares = venue_map(prev_booths, new_booths)
    low = shares.select("old", "matched").unique().filter(pl.col("matched") < 0.8)
    if low.height:
        log(f"WARNING: under 80% of election-day votes matched to new venues: {low.rows()}")

    prev_districts = pl.read_csv(pdir / "districts.csv")
    winners = dict(prev_districts.select("district", "elected").iter_rows())
    held = dict(prev_districts.select("district", "elected_party").iter_rows())
    cand = (prev_booths.filter(pl.col("party") != "INFORMAL")
            .select("district", "section", "venue", "candidate", "party", "votes"))
    # Votes not published by venue (South Australia 2022 gives polling booths only):
    # each candidate's remainder follows the old district's shares, like declaration votes.
    rest = (pl.read_csv(pdir / "primary.csv").select("district", "candidate", "party", "votes")
            .join(cand.group_by("district", "candidate").agg(pl.col("votes").sum().alias("by_venue")),
                  on=["district", "candidate"], how="left")
            .select("district", pl.lit("Declaration").alias("section"), pl.lit("(not by venue)").alias("venue"),
                    "candidate", "party", (pl.col("votes") - pl.col("by_venue").fill_null(0)).alias("votes"))
            .filter(pl.col("votes") > 0))
    cand = pl.concat([cand, rest.cast(cand.schema)])
    moved = _redistribute(cand, ["candidate", "party"], "votes", new_booths, shares)

    primary = (moved.with_columns(pl.col("party").map_elements(bloc, return_dtype=pl.String).alias("bloc"))
        .with_columns(_member_bloc(winners, held).alias("bloc"))
        .group_by("new", "party", "bloc").agg(pl.col("votes").sum())
        .rename({"new": "district"})
        .with_columns(
            (pl.col("party") + " (notional)").alias("candidate"),
            pl.col("votes").round(0).cast(pl.Int64),
        )
        .with_columns((100 * pl.col("votes") / pl.col("votes").sum().over("district")).round(3).alias("pct"))
        .sort("district", "votes", descending=[False, True]))

    if (pdir / "tpp_booths.csv").exists():
        tb = pl.read_csv(pdir / "tpp_booths.csv")
        sides = _redistribute(tb.unpivot(index=["district", "section", "venue"], on=["alp", "coal"],
                                         variable_name="side", value_name="votes"),
                              ["side"], "votes", new_booths, shares)
    else:
        # No Labor v Coalition count by venue (WA): each old seat's count follows its
        # votes, split in that seat's 2PP proportions. Old seats without such a count
        # (a Liberal v National final) are left out.
        tpp_old = pl.read_csv(pdir / "tpp.csv").select(
            "district", (pl.col("alp_votes") / (pl.col("alp_votes") + pl.col("coal_votes"))).alias("p"))
        sides = (moved.group_by("new", "district").agg(pl.col("votes").sum())
                 .join(tpp_old, on="district", how="inner")
                 .with_columns((pl.col("votes") * pl.col("p")).alias("alp"),
                               (pl.col("votes") * (1 - pl.col("p"))).alias("coal"))
                 .drop("votes", "p")
                 .unpivot(index=["new", "district"], on=["alp", "coal"], variable_name="side",
                          value_name="votes"))
    tpp = (sides.group_by("new", "side").agg(pl.col("votes").sum())
           .pivot(on="side", index="new", values="votes")
           .select(pl.col("new").alias("district"),
                   (100 * pl.col("alp") / (pl.col("alp") + pl.col("coal"))).round(2).alias("alp_tpp")))

    # Notional holder: the old seat supplying most of the new one, unless that seat was
    # won on a Labor v Coalition count, in which case the notional 2PP decides.
    origin = (moved.group_by("new", "district").agg(pl.col("votes").sum())
              .sort("votes", descending=True)
              .with_columns((pl.col("votes") / pl.col("votes").sum().over("new")).alias("share"))
              .group_by("new", maintain_order=True).first())
    tpp_d = dict(tpp.iter_rows())
    coal_lead = dict(primary.filter(pl.col("bloc") == "COAL").sort("votes", descending=True)
                     .group_by("district", maintain_order=True).first()
                     .select("district", "party").iter_rows())
    rows = []
    for r in origin.iter_rows(named=True):
        d, old = r["new"], r["district"]
        holder = held[old]
        # Within a point of 50 the venue re-cut cannot call it (it differs from published
        # notional margins by ~0.7 points on average): a mostly unchanged seat stays put.
        close = r["share"] >= MOSTLY_UNCHANGED and abs((tpp_d.get(d) or 0) - 50) < 1
        if bloc(holder) in ("ALP", "COAL") and tpp_d.get(d) is not None and not close:
            holder = "ALP" if tpp_d[d] > 50 else coal_lead.get(d, holder)
        rows.append({"district": d, "elected_party": holder,
                     "elected": winners[old] if holder == held[old] else None,
                     "main_origin": old, "origin_share": round(r["share"], 3),
                     "formal": int(primary.filter(pl.col("district") == d)["votes"].sum()),
                     "alp_tpp": tpp_d.get(d)})
    districts = pl.DataFrame(rows).sort("district")
    return {"primary": primary, "districts": districts, "venue_map": shares.sort("old", "share")}


def _member_bloc(winners: dict[str, str], held: dict[str, str]) -> pl.Expr:
    """Bloc of each candidate row: a minor-party member's vote (the Shooters' seats in NSW
    2019) is largely personal, so it sits with independents rather than being excluded
    first."""
    minor_member = {(d, winners[d]) for d, p in held.items() if bloc(p) == "OTH"}
    return (pl.when(pl.struct("district", "candidate").map_elements(
        lambda r: (r["district"], r["candidate"]) in minor_member, return_dtype=pl.Boolean))
        .then(pl.lit("IND")).otherwise(pl.col("bloc")))


def baseline(election: Election, previous: Election) -> tuple[pl.DataFrame, pl.DataFrame]:
    """First preferences and districts the seat inputs start from: the notional result
    after a redistribution (``prophecy nsw-notional``), else the previous result itself,
    every seat its own origin."""
    if election.boundary_set != previous.boundary_set:
        nd = PROCESSED / f"{election.election_id}-notional"
        return pl.read_csv(nd / "primary.csv"), pl.read_csv(nd / "districts.csv")
    src = PROCESSED / previous.election_id
    prev = pl.read_csv(src / "districts.csv")
    winners = dict(prev.select("district", "elected").iter_rows())
    held = dict(prev.select("district", "elected_party").iter_rows())
    primary = (pl.read_csv(src / "primary.csv")
               .with_columns(_member_bloc(winners, held).alias("bloc"))
               .select("district", "candidate", "party", "bloc", "votes", "pct"))
    districts = prev.select("district", "elected_party", "elected",
                            pl.col("district").alias("main_origin"),
                            pl.lit(1.0).alias("origin_share"), "formal")
    return primary, districts


# --------------------------------------------------------------------------------------
# Seat inputs
# --------------------------------------------------------------------------------------

def state_inputs(election: Election, previous: Election,
                 log: Callable[[str], None] = print, federal_onp: bool = True) -> SeatInputs:
    """Seat inputs on ``election``'s boundaries from the baseline, with by-elections,
    sitting members (recontesting, retiring, defected) and the ballot."""
    primary, districts = baseline(election, previous)
    region_of = regions_for(election, log)
    region_df = districts.select("district", pl.col("district").map_elements(
        lambda d: region_of[slugify(d)], return_dtype=pl.String).alias("region"))
    geo = onp_geography(election, primary, log) if federal_onp else primary.select("district", "bloc", "votes", "pct")
    inputs = build_inputs(primary, districts, geo, region_df)

    # Members at dissolution: previous winners, then by-election winners.
    prev = pl.read_csv(PROCESSED / previous.election_id / "districts.csv")
    member = dict(prev.select("district", "elected").iter_rows())
    member_party = dict(prev.select("district", "elected_party").iter_rows())
    first_term = set(member.values()) - _sitting_before(previous)
    by_change = set()
    for r in _by_elections(election.jurisdiction, previous.date, election.date).iter_rows(named=True):
        if bloc(r["party"]) != bloc(member_party[r["district"]]):
            by_change.add(r["district"])
        member[r["district"]], member_party[r["district"]] = r["member"], r["party"]
        first_term.add(r["member"])

    ballot = pl.read_csv(PROCESSED / election.election_id / "primary.csv").select(
        "district", pl.col("candidate").alias("name"), "party", "bloc")
    standing = {n: (d, p) for d, n, p, _ in ballot.iter_rows()}
    # The Coalition party standing (e.g. a member who moved from the Nationals to the
    # Liberals) where only one of them does.
    for d, parties in ballot.filter(pl.col("bloc") == "COAL").group_by("district").agg(pl.col("party")).iter_rows():
        if len(set(parties)) == 1 and d in inputs.districts:
            inputs.coal_party[inputs.districts.index(d)] = parties[0]
    # Three-cornered contests: a Liberal and a National both on the ballot.
    coal_on = dict(ballot.filter(pl.col("party").is_in(["LIB", "NAT"])).group_by("district")
                   .agg(pl.col("party").unique()).iter_rows())
    prev_coal = (primary.filter(pl.col("party").is_in(["LIB", "NAT"])).group_by("district", "party")
                 .agg(pl.col("votes").sum()).pivot(on="party", index="district", values="votes"))
    prev_split = {r["district"]: (r.get("LIB") or 0) / ((r.get("LIB") or 0) + (r.get("NAT") or 0))
                  for r in prev_coal.iter_rows(named=True) if (r.get("LIB") or 0) + (r.get("NAT") or 0) > 0}
    lib_share = np.full(len(inputs.districts), np.nan)
    for i, d in enumerate(inputs.districts):
        if set(coal_on.get(d, [])) >= {"LIB", "NAT"}:
            # Only one stood last time: the newcomer starts small (often a token
            # candidate in the other party's heartland).
            sp = prev_split.get(d, 0.5)
            lib_share[i] = min(max(sp, NEW_COAL_SHARE), 1 - NEW_COAL_SHARE)
    inputs.lib_share = lib_share
    rows, priors = [], {}
    for i, r in enumerate(districts.iter_rows(named=True)):
        d, old = r["district"], r["main_origin"]
        if old is None or r["origin_share"] < 0.5:
            # A largely new seat: no sitting member's personal vote to gain or lose.
            inputs.incumbent[i] = r["elected_party"]
            inputs.notes.setdefault(d, []).append(f"new seat, notionally {r['elected_party']}")
            continue
        m = member[old]
        holder = member_party[old]
        if old in by_change:
            inputs.notes.setdefault(d, []).append(f"won by {holder} at a by-election")
        elif bloc(r["elected_party"]) != bloc(holder) and bloc(holder) in ("ALP", "COAL"):
            # Notionally won by the other side after the redistribution: the old
            # member's personal vote is not the holder's, so no member effects apply.
            rows.append({"district": d, "party": r["elected_party"], "status": "recontesting",
                         "first_elected": "earlier"})
            inputs.notes.setdefault(d, []).append(f"notionally {r['elected_party']} after the redistribution")
            continue
        inputs.incumbent[i] = holder
        where, on_ballot = standing.get(m), m
        if where is None:
            # Ballot names can differ from the count's (SKELTON Robert, then SKELTON Rob):
            # fall back to the one candidate with the member's surname in their own seat.
            same = ballot.filter((pl.col("district") == d)
                                 & (pl.col("name").str.split(" ").list.first() == m.split()[0]))
            if same.height == 1:
                where, on_ballot = (d, same["party"][0]), same["name"][0]
        if where is None or where[0] != d:
            rows.append({"district": d, "party": holder, "status": "retiring", "first_elected": "earlier"})
            if where is not None:
                inputs.notes.setdefault(d, []).append(f"sitting member {m} ({holder}) contesting {where[0]}")
            continue
        party_now = where[1]
        if bloc(party_now) == "COAL":
            # Their vote follows them if they changed Coalition party (Port Macquarie).
            inputs.coal_party[i] = party_now
            inputs.incumbent[i] = party_now
            if np.isfinite(inputs.lib_share[i]) and party_now != holder and holder in ("LIB", "NAT"):
                inputs.lib_share[i] = 1 - inputs.lib_share[i]
        if bloc(party_now) == "IND" and bloc(holder) in DEFECTOR_FROM:
            # Left a party to stand as an independent (or for KAP): keeps part of their
            # vote. (Minor-party members' votes are already counted as independent votes.)
            inputs.incumbent[i] = "IND"
            old_share = primary.filter(pl.col("district") == d)
            own = old_share.filter(pl.col("party") == holder)["pct"].sum()
            priors[d] = (on_ballot, round(DEFECTOR_PERSONAL_VOTE * own, 1))
            inputs.notes.setdefault(d, []).append(
                f"sitting member {m} elected as {holder}, recontesting as "
                + ("an independent" if party_now == "IND" else party_now))
        elif bloc(party_now) == "IND":
            inputs.incumbent[i] = "IND"
        rows.append({"district": d, "party": party_now, "status": "recontesting",
                     "first_elected": str(previous.date.year) if m in first_term else "earlier"})
    members = pl.DataFrame(rows)
    # Only the defector's own candidacy carries the prior.
    cands = ballot.with_columns(pl.struct("district", "name").map_elements(
        lambda r: priors[r["district"]][1] if priors.get(r["district"], (None,))[0] == r["name"] else None,
        return_dtype=pl.Float64).alias("prior_share"))
    inputs = apply_candidates(inputs, members, cands, sophomore_since=previous.date.year)
    log(f"{election.jurisdiction} inputs: {len(inputs.districts)} seats, {int(inputs.retiring.sum())} retiring, "
        f"{int(inputs.sophomore.sum())} first-term recontesting, {len(priors)} defectors")
    return inputs


def regions_for(election: Election, log: Callable[[str], None] = print) -> dict[str, str]:
    """Region of each district (by slug) on ``election``'s boundaries: the curated file
    when there is one, else derived from the next boundary set that has one, a district
    taking the region of its namesake there, or of the new district most of its votes
    went to (the later notional's venue map)."""
    from prophecy.jurisdictions import in_jurisdiction

    path = CURATED_DIR / f"regions_{election.boundary_set}.csv"
    if path.exists():
        return dict(pl.read_csv(path).iter_rows())
    later = [e for e in in_jurisdiction(election.jurisdiction) if e.date > election.date
             and e.boundary_set != election.boundary_set]
    names = pl.read_csv(PROCESSED / election.election_id / "districts.csv")["district"].to_list()
    region = {slugify(d): None for d in names}
    successor = {slugify(d): slugify(d) for d in names}  # district -> its district on later boundaries
    for e in later:
        vm = PROCESSED / f"{e.election_id}-notional" / "venue_map.csv"
        if vm.exists():
            m = (pl.read_csv(vm).sort("share", descending=True).group_by("old", maintain_order=True).first())
            step = {slugify(o): slugify(n) for o, n, *_ in m.iter_rows()}
            successor = {d: step.get(s, s) for d, s in successor.items()}
        f = CURATED_DIR / f"regions_{e.boundary_set}.csv"
        if f.exists():
            known = dict(pl.read_csv(f).iter_rows())
            for d in region:
                region[d] = region[d] or known.get(successor[d]) or known.get(d)
            break
    missing = [d for d, r in region.items() if r is None]
    if missing:
        raise ValueError(f"{election.election_id}: no region derivable for {missing}")
    log(f"regions for {election.boundary_set}: derived from a later boundary set")
    return region


BROAD_CONTEST = 0.8  # share of seats One Nation must have contested for its state vote to map it
STATE_CODES = {"NSW": "NSW", "QLD": "QLD", "SA": "SA", "WA": "WA", "NT": "NT", "VIC": "VIC"}


def onp_geography(election: Election, primary: pl.DataFrame,
                  log: Callable[[str], None] = print) -> pl.DataFrame:
    """Where One Nation's vote sits (district, bloc, votes, pct): its previous state vote
    where it contested most seats, else the latest federal election before this one,
    re-aggregated from polling places onto the state districts (when the boundary file
    is on hand). Otherwise its previous state vote, flat where it did not stand."""
    from prophecy.ingest.boundaries import LAYERS, raw_path
    from prophecy.jurisdictions import in_jurisdiction

    state_geo = primary.select("district", "bloc", "votes", "pct")
    contested = primary.filter((pl.col("bloc") == "ONP") & (pl.col("votes") > 0))["district"].n_unique()
    n = primary["district"].n_unique()
    if contested >= BROAD_CONTEST * n:
        return state_geo
    fed = [f for f in in_jurisdiction("FED") if f.date < election.date and f.election_id != "fed-next"]
    if not fed or election.boundary_set not in LAYERS or not raw_path(election.boundary_set).exists():
        log(f"One Nation geography: previous state vote ({contested} of {n} seats); no federal crosswalk")
        return state_geo
    path = PROCESSED / f"{election.election_id}-federal-geo.csv"
    if not path.exists():
        from prophecy.ingest.federal_xwalk import federal_geography

        geo = federal_geography(fed[-1].date.year, STATE_CODES[election.jurisdiction],
                                election.boundary_set, sorted(primary["district"].unique().to_list()))
        geo.write_csv(path)
    log(f"One Nation geography: federal {fed[-1].date.year} polling places "
        f"(One Nation contested {contested} of {n} state seats last time)")
    return pl.read_csv(path)


def _by_elections(jurisdiction: str, after, before) -> pl.DataFrame:
    by = pl.read_csv(CURATED_DIR / f"by_elections_{jurisdiction.lower()}.csv", try_parse_dates=True)
    return by.filter((pl.col("date") > after) & (pl.col("date") < before))


def _sitting_before(previous: Election) -> set[str]:
    """Members elected before ``previous`` (to spot first-termers): winners at the
    election before it and at by-elections since."""
    from prophecy.jurisdictions import previous as prev_of

    earlier = prev_of(previous)
    path = PROCESSED / earlier.election_id / "districts.csv" if earlier else None
    if path is None or not path.exists():
        return set()
    return (set(pl.read_csv(path)["elected"].to_list())
            | set(_by_elections(previous.jurisdiction, earlier.date, previous.date)["member"].to_list()))


def _fit_exhaustion(w: np.ndarray, base: np.ndarray, src, names: list[str],
                    log: Callable[[str], None]) -> float:
    """The share of every transfer that exhausts, chosen so replaying the previous count
    exhausts the share of ballots each seat's ``exhausted`` column records; 0 when the
    election recorded none (full preferential)."""
    from scipy.optimize import minimize_scalar

    from prophecy.model.preferences import count

    d = pl.read_csv(src / "districts.csv")
    if "exhausted" not in d.columns or d["exhausted"].is_null().all():
        return 0.0
    share = dict(zip(d["district"], (d["exhausted"] / d["formal"]).to_list()))
    actual = np.array([share.get(n) if share.get(n) is not None else np.nan for n in names])

    def miss(e: float) -> float:
        _, _, kept = count(base[None], w[None], exhaust_rate=e, with_total=True)
        return float(np.nanmean((1 - kept[0] - actual) ** 2))

    e = float(minimize_scalar(miss, bounds=(0.0, 0.95), method="bounded").x)
    _, _, kept = count(base[None], w[None], exhaust_rate=e, with_total=True)
    log(f"exhaustion ({src.name}): {e:.1%} of each transfer; replayed {np.nanmean(1 - kept[0]):.1%} "
        f"of ballots exhausted per seat, recorded {np.nanmean(actual):.1%}")
    return e


def state_flows(previous: Election, log: Callable[[str], None] = print,
                weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray | None]:
    """Flows (and, under optional preferential voting, exhaustion) from the previous
    election's distributions of preferences, calibrated so replaying its counts
    reproduces its Labor v Coalition results.

    ``weights``: flows estimated elsewhere (the NT publishes no distributions; its
    federal divisions' are used), calibrated the same way."""
    src = PROCESSED / previous.election_id
    if weights is None:
        transfers = pl.read_csv(src / "dop_transfers.csv").with_columns(
            pl.col("from_party").map_elements(bloc, return_dtype=pl.String).alias("from_bloc"),
            pl.when(pl.col("to_party") == "EXH").then(pl.lit("EXH"))
            .otherwise(pl.col("to_party").map_elements(bloc, return_dtype=pl.String)).alias("to_bloc"),
        )
        w, exhaust = estimate_flows(transfers)
    else:
        w, exhaust = weights, None
    primary = pl.read_csv(src / "primary.csv")
    names = sorted(pl.read_csv(src / "districts.csv")["district"].to_list())
    base = np.zeros((len(names), len(BLOCS)))
    for d, b, v in primary.group_by("district", "bloc").agg(pl.col("votes").sum()).iter_rows():
        base[names.index(d), IDX[b]] += v
    base /= base.sum(axis=1, keepdims=True)
    tcp = pl.read_csv(src / "tcp.csv")
    alp_tcp = np.full(len(names), np.nan)
    for (d,), t in tcp.group_by("district"):
        if set(t["bloc"]) == {"ALP", "COAL"}:
            alp_tcp[names.index(d)] = t.filter(pl.col("bloc") == "ALP")["pct"][0]
    if weights is not None:
        # Flows estimated elsewhere carry no exhaustion. If the previous election was
        # optional preferential (NT 2016), its 2CPs are shares of the ballots still in the
        # count: calibrate with an exhaustion rate fitted to the exhausted ballots it
        # recorded, so the flows aren't understated. The forecast itself is full
        # preferential (NT since 2020), so no exhaustion is returned for simulating it.
        rate = _fit_exhaustion(w, base, src, names, log)
        flows, calib = calibrate_to_results(w, base, alp_tcp, exhaust_rate=rate)
        log(f"flow calibration ({previous.election_id}): {calib}")
        return flows, None
    flows, calib = calibrate_to_results(w, base, alp_tcp, exhaust=exhaust)
    log(f"flow calibration ({previous.election_id}): {calib}")
    if exhaust is not None:
        log("exhaustion weight by bloc: " + ", ".join(f"{b} {e:.2f}" for b, e in zip(BLOCS, exhaust)))
    return flows, exhaust
