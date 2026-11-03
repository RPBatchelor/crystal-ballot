"""Independents standing for the first time: what such candidates have polled before.

A sitting or returning independent's vote carries forward from the previous result.
A first-time independent has no previous vote, yet a few each election poll strongly
(the "teal" and community independents). Their vote is drawn from the empirical
distribution of first-time independents' primary votes at earlier single-member
elections (a heavy right tail: median about 2.6%, 95th percentile about 20%).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl

from prophecy import DATA_DIR
from prophecy.jurisdictions import ELECTIONS, Election, previous
from prophecy.model.swing_fit import SINGLE_MEMBER, _key

PROCESSED = DATA_DIR / "processed"
JITTER_SD = 0.3  # log scale, around each resampled share


def _new_independents(e: Election, prev: Election) -> pl.DataFrame:
    """``e``'s independents who did not stand anywhere at ``prev``."""
    cur = pl.read_csv(PROCESSED / e.election_id / "primary.csv", infer_schema_length=None)
    old = pl.read_csv(PROCESSED / prev.election_id / "primary.csv", infer_schema_length=None)
    before = {_key(c) for c in old["candidate"].to_list()}
    return cur.filter((pl.col("bloc") == "IND")
                      & ~pl.col("candidate").map_elements(lambda c: _key(c) in before, return_dtype=pl.Boolean))


def pool(before: date) -> np.ndarray:
    """First-time independents' primary votes (fractions) at elections before ``before``."""
    out = []
    for e in ELECTIONS.values():
        p = previous(e)
        if (e.jurisdiction in SINGLE_MEMBER and p is not None and e.date < before
                and (PROCESSED / e.election_id / "primary.csv").exists()
                and (PROCESSED / p.election_id / "primary.csv").exists()):
            out.append(_new_independents(e, p)["pct"].cast(pl.Float64).to_numpy() / 100)
    return np.concatenate(out) if out else np.array([])


def count_new(e: Election, prev: Election, districts: list[str]) -> np.ndarray:
    """Number of first-time independents on each district's ballot."""
    new = _new_independents(e, prev).group_by("district").len()
    n = dict(new.iter_rows())
    return np.array([n.get(d, 0) for d in districts], dtype=int)


def draw(n_new: np.ndarray, shares: np.ndarray, size: int, rng: np.random.Generator) -> np.ndarray:
    """S x D total first-time independent vote: each candidate a resampled share."""
    D = len(n_new)
    out = np.zeros((size, D))
    if not len(shares):
        return out
    for k in range(1, int(n_new.max(initial=0)) + 1):
        has = n_new >= k
        picks = shares[rng.integers(0, len(shares), size=(size, int(has.sum())))]
        out[:, has] += picks * np.exp(rng.normal(0, JITTER_SD, size=picks.shape))
    return np.clip(out, 0, 0.6)
