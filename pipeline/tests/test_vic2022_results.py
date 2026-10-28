"""Integrity checks on ingested VEC 2022 Legislative Assembly results.

Run ``uv run prophecy ingest-results --year 2022`` first.
"""

import polars as pl
import pytest

from prophecy import DATA_DIR

OUT = DATA_DIR / "processed" / "vic-2022"
pytestmark = pytest.mark.skipif(not OUT.exists(), reason="VEC 2022 results not ingested")


@pytest.fixture(scope="module")
def tables() -> dict[str, pl.DataFrame]:
    return {n: pl.read_csv(OUT / f"{n}.csv") for n in ("districts", "primary", "tcp", "tpp")}


def test_88_districts(tables):
    assert tables["districts"]["district"].n_unique() == 88


def test_seat_tally_matches_official(tables):
    # Official 2022 result (incl. Narracan supplementary): ALP 56, LIB 19, NAT 9, GRN 4.
    tally = dict(tables["districts"]["elected_party"].value_counts().iter_rows())
    assert tally == {"ALP": 56, "LIB": 19, "NAT": 9, "GRN": 4}


def test_every_district_has_two_tcp_finalists(tables):
    counts = tables["tcp"].group_by("district").len()
    assert counts.height == 88
    assert (counts["len"] == 2).all()


def test_tcp_winner_is_elected_member(tables):
    winners = (
        tables["tcp"].sort("votes", descending=True).group_by("district", maintain_order=True).first()
    )
    mismatched = winners.filter(~pl.col("elected"))
    assert mismatched.height == 0, mismatched.select("district", "candidate")


def test_primary_votes_sum_to_formal(tables):
    sums = tables["primary"].group_by("district").agg(pl.col("votes").sum().alias("sum"))
    joined = sums.join(tables["districts"], on="district")
    assert (joined["sum"] == joined["formal"]).all()


def test_statewide_primaries_close_to_official(tables):
    p = tables["primary"]
    share = p.group_by("bloc").agg(pl.col("votes").sum()).with_columns(
        (100 * pl.col("votes") / pl.col("votes").sum()).alias("pct")
    )
    pct = dict(share.select("bloc", "pct").iter_rows())
    # VEC statewide: ALP 36.7, Coalition 34.4, GRN 11.5 (approx).
    assert pct["ALP"] == pytest.approx(36.7, abs=0.5)
    assert pct["COAL"] == pytest.approx(34.5, abs=0.6)
    assert pct["GRN"] == pytest.approx(11.5, abs=0.4)


def test_statewide_tpp(tables):
    t = tables["tpp"]
    alp = 100 * t["alp_votes"].sum() / (t["alp_votes"].sum() + t["coal_votes"].sum())
    assert alp == pytest.approx(55.0, abs=0.3)
