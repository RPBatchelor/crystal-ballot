"""Victoria's 2018 result re-cut onto the 2021 boundaries (the vic-2022 baseline)."""

from pathlib import Path

import polars as pl
import pytest

from prophecy.ingest.vec import parse_2cp_venues
from prophecy.model.pipeline import PROCESSED

NOTIONAL = PROCESSED / "vic-2022-notional"
CURATED = Path(__file__).resolve().parents[2] / "data" / "curated"


@pytest.mark.skipif(not NOTIONAL.exists(), reason="run `prophecy notional --election vic-2022`")
def test_notional_keeps_every_vote():
    # Re-cutting moves votes between districts; it must not create or lose them.
    notional = pl.read_csv(NOTIONAL / "primary.csv")["votes"].sum()
    actual = pl.read_csv(PROCESSED / "vic-2018" / "primary.csv")["votes"].sum()
    assert abs(notional / actual - 1) < 0.005


@pytest.mark.skipif(not NOTIONAL.exists(), reason="run `prophecy notional --election vic-2022`")
def test_notional_close_to_published_pendulum():
    # Antony Green's (ABC) notional margins, Labor v Coalition seats: the venue re-cut
    # should agree to about a point on average and not lean far to either side.
    abc = pl.read_csv(CURATED / "notional_checks_vic-2022.csv").filter(
        pl.col("notional_holder").is_in(["ALP", "LIB", "NAT"])
        & pl.col("two_party_opponent").is_in(["ALP", "LIB", "NAT"]))
    abc = abc.with_columns(pl.when(pl.col("notional_holder") == "ALP")
                           .then(50 + pl.col("margin")).otherwise(50 - pl.col("margin")).alias("abc"))
    ours = pl.read_csv(NOTIONAL / "districts.csv").select("district", "alp_tpp")
    diff = abc.join(ours, on="district").drop_nulls("alp_tpp").select(pl.col("alp_tpp") - pl.col("abc"))
    assert diff.height >= 70
    assert diff.to_series().abs().mean() < 1.5
    assert abs(diff.to_series().mean()) < 1.0


def test_parse_2cp_venues_splits_centres_and_vote_types():
    html = """<h2>Two candidate preferred vote</h2><table>
    <tr><td></td><td>BRENNAN, Sally</td><td>McLEISH, Cindy</td><td></td></tr>
    <tr><td>Voting Centres</td><td>AUSTRALIAN LABOR PARTY</td><td>LIBERAL</td><td>Mis-sorts</td></tr>
    <tr><td>Alexandra</td><td>615</td><td>821</td><td>0</td></tr>
    <tr><td></td></tr>
    <tr><td>Postal Votes</td><td>1,779</td><td>3,223</td><td>0</td></tr>
    <tr><td>Total</td><td>2394</td><td>4044</td><td>0</td></tr>
    </table>"""
    parties, rows = parse_2cp_venues(html)
    assert parties == ["AUSTRALIAN LABOR PARTY", "LIBERAL"]
    assert rows == [
        {"section": "Voting Centres", "venue": "Alexandra", "votes": (615, 821)},
        {"section": "Postal Votes", "venue": "Postal Votes", "votes": (1779, 3223)},
    ]
