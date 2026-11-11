"""NTEC reconciliation of the Wikipedia NT results, and the exhaustion rate used to
calibrate flows on NT 2016 (optional preferential)."""

import numpy as np
import polars as pl
import pytest

from prophecy import RAW_DIR
from prophecy.ingest.ntec import _set_votes, reconcile
from prophecy.ingest.wiki_nt import _candidates
from prophecy.model.preferences import BLOCS, IDX, count


def test_indented_box_close_is_parsed():
    # Blain 2016 closes each candidate box with an indented "}}".
    box = ("{{Election box candidate AU party\n   |party = Labor NT\n   |candidate = A B\n"
           "   |votes = 1,597\n   |percentage = 37.3\n   |change = +5.3\n }}\n")
    assert [c["votes"] for c in _candidates(box)] == [1597]


def test_independents_share_the_party_total_pro_rata():
    rows = pl.DataFrame({"candidate": ["A", "B", "C"], "party": ["ALP", "IND", "IND"],
                         "votes": [100, 30, 10]})
    out = _set_votes(rows, {"ALP": 101, "IND": 41}, "test", log=lambda s: None)
    v = dict(out.select("candidate", "votes").iter_rows())
    assert v["A"] == 101 and v["B"] + v["C"] == 41 and v["B"] == 31
    assert out["pct"].sum() == pytest.approx(100, abs=0.01)


def test_party_mismatch_is_an_error():
    rows = pl.DataFrame({"candidate": ["A"], "party": ["ALP"], "votes": [1]})
    with pytest.raises(ValueError):
        _set_votes(rows, {"CLP": 1}, "test", log=lambda s: None)


@pytest.mark.skipif(not (RAW_DIR / "wikipedia" / "nt-results-2016.wiki").exists()
                    or not (RAW_DIR / "ntec").exists(), reason="NT raw pages not downloaded")
def test_reconciled_2016_matches_ntec_and_keeps_winners():
    from prophecy.ingest.ntec import summaries
    from prophecy.ingest.wiki_nt import ingest_nt_assembly

    tables = reconcile(2016, ingest_nt_assembly(2016, refresh=False), log=lambda s: None)
    fp, _ = summaries(2016)
    blain = tables["primary"].filter(pl.col("district") == "Blain")
    assert blain.filter(pl.col("party") == "IND")["votes"].sum() == fp.filter(pl.col("district") == "Blain")["Ind"][0]
    d = tables["districts"]
    assert d["exhausted"].null_count() == 0 and d["enrolment"].null_count() == 0


def test_exhaust_rate_removes_that_share_of_each_transfer():
    shares = np.zeros((1, 1, len(BLOCS)))
    shares[0, 0, [IDX["ALP"], IDX["COAL"], IDX["GRN"]]] = [0.45, 0.45, 0.10]
    w = np.full((1, len(BLOCS), len(BLOCS)), 1.0)
    _, _, kept = count(shares, w, exhaust_rate=0.3, with_total=True)
    assert kept[0, 0] == pytest.approx(1 - 0.10 * 0.3)
    _, _, full = count(shares, w, with_total=True)
    assert full[0, 0] == pytest.approx(1.0)
