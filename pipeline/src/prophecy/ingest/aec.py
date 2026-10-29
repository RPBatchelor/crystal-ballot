"""Ingest federal House of Representatives results from the AEC Tally Room downloads.

Produces the same tidy tables as the VEC ingest (districts, primary, tcp, tpp,
dop_transfers) so the seat model runs unchanged, plus a *notional* baseline for
elections held on new boundaries: the AEC's per-candidate ``Swing`` column is measured
against notional previous-election results on the current boundaries, so
``pct - swing`` recovers that notional baseline (published before polling day, so a
backtest using it remains blind).
"""

from __future__ import annotations

import time

import httpx
import polars as pl

from prophecy import RAW_DIR
from prophecy.schema.parties import bloc, party_code

BASE = "https://results.aec.gov.au/{event}/Website/Downloads/{name}-{event}.csv"
EVENTS = {2019: "24310", 2022: "27966", 2025: "31496"}
FILES = [
    "HouseFirstPrefsByCandidateByVoteTypeDownload",
    "HouseTcpByCandidateByVoteTypeDownload",
    "HouseTppByDivisionDownload",
    "HouseMembersElectedDownload",
    "HouseDopByDivisionDownload",
    "HouseTurnoutByDivisionDownload",
]
USER_AGENT = "prophecy-election-model/0.1 (election forecasting research)"


def download(year: int) -> None:
    event = EVENTS[year]
    out = RAW_DIR / "aec" / event
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120, follow_redirects=True) as c:
        for name in FILES:
            dest = out / f"{name}-{event}.csv"
            if dest.exists() and dest.stat().st_size > 0:
                continue
            r = c.get(BASE.format(event=event, name=name))
            r.raise_for_status()
            dest.write_bytes(r.content)
            time.sleep(1)


def _read(year: int, name: str) -> pl.DataFrame:
    event = EVENTS[year]
    # First line is a title banner; the header row follows.
    return pl.read_csv(RAW_DIR / "aec" / event / f"{name}-{event}.csv", skip_rows=1,
                       infer_schema_length=None)


def _codes(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.col("PartyNm").map_elements(lambda n: party_code(n), return_dtype=pl.String).alias("party"),
    ).with_columns(pl.col("party").map_elements(bloc, return_dtype=pl.String).alias("bloc"))


def _candidate(df: pl.DataFrame) -> pl.Expr:
    # Some candidates have no given name; avoid a null candidate name.
    name = pl.col("Surname").fill_null("") + pl.lit(", ") + pl.col("GivenNm").fill_null("")
    return name.str.strip_chars(", ").alias("candidate")


def ingest_aec_house(year: int) -> dict[str, pl.DataFrame]:
    election_id = f"fed-{year}"
    fp = _codes(_read(year, "HouseFirstPrefsByCandidateByVoteTypeDownload")
                .filter(pl.col("PartyNm").fill_null("Independent") != "Informal")
                .with_columns(pl.col("PartyNm").fill_null("Independent")))
    fp = fp.with_columns(
        _candidate(fp),
        (100 * pl.col("TotalVotes") / pl.col("TotalVotes").sum().over("DivisionNm")).round(3).alias("pct"),
    )
    elected = fp.filter(pl.col("Elected") == "Y")
    turnout = _read(year, "HouseTurnoutByDivisionDownload").select(
        pl.col("DivisionNm").alias("district"), pl.col("Enrolment").alias("enrolment"))

    districts = (
        fp.group_by("DivisionNm", "StateAb").agg(pl.col("TotalVotes").sum().alias("formal"))
        .join(elected.select("DivisionNm", pl.col("candidate").alias("elected"),
                             pl.col("PartyNm").alias("elected_party_name"),
                             pl.col("party").alias("elected_party")), on="DivisionNm")
        .rename({"DivisionNm": "district", "StateAb": "state"})
        .join(turnout, on="district", how="left")
        .with_columns(pl.lit(election_id).alias("election_id"), pl.lit(None, pl.Int64).alias("informal"))
        .sort("district")
    )
    primary = fp.select(
        pl.lit(election_id).alias("election_id"), pl.col("DivisionNm").alias("district"),
        "candidate", pl.col("PartyNm").alias("party_name"), "party", "bloc",
        pl.col("TotalVotes").alias("votes"), "pct", (pl.col("Elected") == "Y").alias("elected"),
        (pl.col("HistoricElected") == "Y").alias("sitting"),
        pl.col("Swing").cast(pl.Float64, strict=False).alias("swing"),
    )

    tcp = _codes(_read(year, "HouseTcpByCandidateByVoteTypeDownload").with_columns(
        pl.col("PartyNm").fill_null("Independent")))
    tcp = tcp.with_columns(_candidate(tcp)).select(
        pl.lit(election_id).alias("election_id"), pl.col("DivisionNm").alias("district"),
        "candidate", pl.col("PartyNm").alias("party_name"), "party", "bloc",
        pl.col("TotalVotes").alias("votes"),
        (100 * pl.col("TotalVotes") / pl.col("TotalVotes").sum().over("DivisionNm")).round(3).alias("pct"),
        (pl.col("Elected") == "Y").alias("elected"),
        pl.col("Swing").cast(pl.Float64, strict=False).alias("swing"),
    )

    tpp_raw = _read(year, "HouseTppByDivisionDownload")
    tpp = tpp_raw.select(
        pl.lit(election_id).alias("election_id"), pl.col("DivisionNm").alias("district"),
        pl.lit("AEC").alias("tpp_method"),
        pl.col("Australian Labor Party Votes").alias("alp_votes"),
        pl.col("Liberal/National Coalition Votes").alias("coal_votes"),
        pl.col("Australian Labor Party Percentage").alias("alp_tpp"),
        pl.col("Swing").cast(pl.Float64, strict=False).alias("swing"),
    )
    return {"districts": districts, "primary": primary, "tcp": tcp, "tpp": tpp,
            "dop_transfers": dop_transfers(year)}


def dop_transfers(year: int) -> pl.DataFrame:
    """Per-count transfers from the AEC full distribution of preferences.

    At each count the excluded candidate has a negative transfer; every candidate still
    in the count receives a (possibly zero) share.
    """
    d = _codes(_read(year, "HouseDopByDivisionDownload").with_columns(
        pl.col("PartyNm").fill_null("Independent")))
    d = d.with_columns(_candidate(d))
    wide = d.pivot(on="CalculationType", index=["DivisionNm", "CountNumber", "candidate", "party"],
                   values="CalculationValue", aggregate_function="first")
    rows = []
    for (div, count), g in wide.filter(pl.col("CountNumber") > 0).group_by(
            "DivisionNm", "CountNumber", maintain_order=True):
        out = g.filter(pl.col("Transfer Count") < 0)
        if out.height != 1:
            continue  # final count or a bulk exclusion; skip
        src = out.row(0, named=True)
        receivers = g.filter((pl.col("Transfer Count") >= 0) & (pl.col("Preference Count") > 0))
        for r in receivers.iter_rows(named=True):
            rows.append({"district": div, "count": count, "from_candidate": src["candidate"],
                         "to_candidate": r["candidate"], "votes": float(r["Transfer Count"]),
                         "from_party": src["party"], "to_party": r["party"]})
    return pl.DataFrame(rows).with_columns(pl.lit(f"fed-{year}").alias("election_id"))


def notional_baseline(year: int) -> dict[str, pl.DataFrame]:
    """Previous-election notional results on ``year``'s boundaries, from AEC swings.

    Parties without a swing (new parties, or ones absent last time) contribute nothing;
    Others is the residual. Sitting members (``HistoricElected``) give the seat holder.
    """
    cur = ingest_aec_house(year)
    p = cur["primary"].with_columns((pl.col("pct") - pl.col("swing")).clip(0).alias("notional"))
    blocs = (
        p.filter(pl.col("swing").is_not_null())
        .group_by("district", "bloc").agg(pl.col("notional").sum())
        .filter(pl.col("bloc") != "OTH")
    )
    other = blocs.group_by("district").agg((100 - pl.col("notional").sum()).clip(0).alias("notional"))
    blocs = pl.concat([blocs, other.with_columns(pl.lit("OTH").alias("bloc")).select(blocs.columns)])
    # Express as one pseudo-candidate per bloc so build_inputs can aggregate as usual.
    enrol = cur["districts"].select("district", "enrolment", "state")
    primary = blocs.join(enrol, on="district").with_columns(
        pl.lit(f"fed-{year}-notional").alias("election_id"),
        pl.col("bloc").alias("party"),
        pl.col("bloc").alias("candidate"),
        pl.col("bloc").alias("party_name"),
        (pl.col("notional") / 100 * pl.col("enrolment")).round().cast(pl.Int64).alias("votes"),
        pl.col("notional").round(3).alias("pct"),
        pl.lit(False).alias("elected"),
    ).select("election_id", "district", "candidate", "party_name", "party", "bloc", "votes", "pct", "elected")

    # Holder: the sitting member's party where one recontests, else the notional leader
    # on the two-candidate count (AEC 2CP swing) or, failing that, first preferences.
    sitting = cur["primary"].filter(pl.col("sitting")).select("district", pl.col("party").alias("holder"))
    tcp = cur["tcp"].with_columns((pl.col("pct") - pl.col("swing")).alias("n"))
    tcp_lead = (tcp.filter(pl.col("swing").is_not_null()).sort("n", descending=True)
                .group_by("district", maintain_order=True).first()
                .select("district", pl.col("party").alias("tcp_lead")))
    prim_lead = (p.sort("notional", descending=True).group_by("district", maintain_order=True)
                 .first().select("district", pl.col("party").alias("prim_lead")))
    districts = (
        enrol.join(sitting, on="district", how="left").join(tcp_lead, on="district", how="left")
        .join(prim_lead, on="district", how="left")
        .with_columns(pl.coalesce("holder", "tcp_lead", "prim_lead").alias("elected_party"),
                      pl.col("enrolment").alias("formal"),
                      pl.lit(f"fed-{year}-notional").alias("election_id"),
                      pl.lit(None, pl.String).alias("elected"))
        .select("election_id", "district", "state", "elected", "elected_party", "enrolment", "formal")
        .sort("district")
    )
    # Ballot (known at close of nominations) and sitting members, for the candidate model.
    ballot = cur["primary"].select("district", pl.col("candidate").alias("name"), "party",
                                   pl.lit(None, pl.Float64).alias("prior_share"),
                                   pl.col("sitting"))
    return {"primary": primary, "districts": districts, "ballot": ballot}
