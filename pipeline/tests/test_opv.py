"""Optional preferential voting: exhausted ballots in counts and flow estimation."""

import numpy as np
import polars as pl
import pytest
from test_preferences import flows, shares

from prophecy.model.preferences import BLOCS, IDX, count, estimate_flows, two_party


def exhaust(**kw: float) -> np.ndarray:
    e = np.zeros(len(BLOCS))
    for k, v in kw.items():
        e[IDX[k]] = v
    return e


def test_exhausted_ballots_leave_the_count():
    # GRN 15 excluded: weights ALP .8, COAL .2, exhaustion .25 -> 64% ALP, 16% COAL,
    # 20% exhaust. ALP 49.6, COAL 47.4 of the 97 still in the count.
    w = flows({"GRN": {"ALP": 0.8, "COAL": 0.2}})
    s = shares(ALP=40, COAL=45, GRN=15)
    winner, final = count(s[None, None], w[None], exhaust(GRN=0.25)[None])
    assert BLOCS[winner[0, 0]] == "ALP"
    assert final[0, 0, IDX["ALP"]] == pytest.approx(49.6 / 97)
    tpp = two_party(s[None], w[None], "ALP", "COAL", exhaust(GRN=0.25)[None])
    assert tpp[0] == pytest.approx(100 * 49.6 / 97)


def test_heavy_exhaustion_can_change_the_winner():
    # Same flows, but 75% of Greens ballots exhaust: ALP 40 + 3, COAL 45 + 0.75.
    w = flows({"GRN": {"ALP": 0.8, "COAL": 0.2}})
    winner, _ = count(shares(ALP=40, COAL=45, GRN=15)[None, None], w[None], exhaust(GRN=3.0)[None])
    assert BLOCS[winner[0, 0]] == "COAL"


def test_no_exhaustion_matches_full_preferential():
    w = flows({"GRN": {"ALP": 0.7, "COAL": 0.3}, "OTH": {"ALP": 0.4, "COAL": 0.6}})
    s = shares(ALP=38, COAL=42, GRN=12, OTH=8)[None, None]
    _, full = count(s, w[None])
    _, opv = count(s, w[None], np.zeros((1, len(BLOCS))))
    np.testing.assert_allclose(full, opv)


def test_estimate_flows_recovers_exhaustion():
    # GRN excluded twice, with different choice sets; true weights ALP .7, COAL .3,
    # exhaustion .5 (so 7/15 ALP, 3/15 COAL, 5/15 exhaust when both remain).
    rows = []
    for district, (alp, coal, exh) in {"A": (700, 300, 500), "B": (1400, 600, 1000)}.items():
        for to, v in [("ALP", alp), ("COAL", coal), ("EXH", exh)]:
            rows.append({"district": district, "count": 2, "from_bloc": "GRN", "to_bloc": to, "votes": v})
    # Only Coalition left: exhaustion .5 v .3 -> 62.5% exhaust.
    for to, v in [("COAL", 375), ("EXH", 625)]:
        rows.append({"district": "C", "count": 2, "from_bloc": "GRN", "to_bloc": to, "votes": v})
    w, e = estimate_flows(pl.DataFrame(rows))
    g = IDX["GRN"]
    assert w[g, IDX["ALP"]] / w[g, IDX["COAL"]] == pytest.approx(7 / 3, rel=1e-3)
    assert e[g] / w[g, IDX["COAL"]] == pytest.approx(5 / 3, rel=1e-3)


def test_estimate_flows_without_exhaustion_is_unchanged():
    rows = [{"district": "A", "count": 2, "from_bloc": "GRN", "to_bloc": b, "votes": v}
            for b, v in [("ALP", 800), ("COAL", 200)]]
    w, e = estimate_flows(pl.DataFrame(rows))
    assert e is None
    assert w[IDX["GRN"], IDX["ALP"]] / w[IDX["GRN"], IDX["COAL"]] == pytest.approx(4.0, rel=1e-3)
