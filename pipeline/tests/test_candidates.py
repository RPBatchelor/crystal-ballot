import numpy as np
import polars as pl

from prophecy.model.preferences import IDX
from prophecy.model.simulate import SeatInputs, apply_candidates


def inputs() -> SeatInputs:
    return SeatInputs(
        districts=["A", "B", "C"], regions=["R", "R", "R"], weight=np.ones(3),
        base=np.full((3, 6), 1 / 6), onp_index=np.ones(3),
        coal_party=["LIB"] * 3, incumbent=["ALP", "LIB", "ALP"],
    )


def test_retirement_and_sophomore_flags():
    members = pl.DataFrame({
        "district": ["A", "B", "C"],
        "party": ["ALP", "LIB", "IND"],  # C: elected Labor, now an independent
        "first_elected": ["2014 or earlier", "2022", "2022"],
        "status": ["retiring", "recontesting", "retiring"],
    })
    out = apply_candidates(inputs(), members, None, sophomore_since=2022)
    assert out.retiring[0, IDX["ALP"]] == 1
    assert out.sophomore[1, IDX["COAL"]] == 1
    # A defector's retirement costs the party they were elected for.
    assert out.retiring[2, IDX["ALP"]] == 1 and out.retiring[2, IDX["IND"]] == 0
    assert out.contest is None


def test_ballot_masks_parties_without_candidates():
    cands = pl.DataFrame({
        "district": ["A", "A", "A"],
        "party": ["ALP", "LIB", "IND"],
        "name": ["x", "y", "z"],
        "prior_share": [None, None, 25.0],
    })
    out = apply_candidates(inputs(), None, cands, sophomore_since=2022)
    assert out.contest[0, IDX["ALP"]] and out.contest[0, IDX["COAL"]]
    assert not out.contest[0, IDX["GRN"]]  # no Greens candidate listed in A
    assert out.contest[1].all()  # B not on the ballot file yet: everyone contests
    assert out.ind_prior[0] == 0.25
