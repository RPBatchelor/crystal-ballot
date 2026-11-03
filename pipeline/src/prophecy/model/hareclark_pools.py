"""What new parties and first-time independents have polled before, for Hare-Clark.

The Hare-Clark model splits the minor-party ("Others") vote among the parties on the
ballot. A party standing for the first time has no previous vote to split by, and a
fixed small weight cannot represent the occasional new party that takes a quota or
more (the Jacqui Lambie Network in Tasmania in 2024, Independents for Canberra in the
ACT in 2024). Instead each new party's strength is drawn, once per simulation for the
whole jurisdiction, from new parties' shares at earlier elections; and each first-time
independent's vote from first-time independents' votes in earlier Hare-Clark divisions.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import polars as pl

from prophecy import DATA_DIR
from prophecy.jurisdictions import ELECTIONS, previous
from prophecy.model.swing_fit import _key

PROCESSED = DATA_DIR / "processed"
HARE_CLARK = ("TAS", "ACT")
STATES = ("VIC", "NSW", "QLD", "WA", "SA", "NT", "TAS", "ACT")
MIN_CONTEST = 0.3  # a new party must contest this share of seats/divisions to count
DIVISION_SD = 0.35  # log scale: a new party's division-to-division variation


def _pairs(before: date, jurisdictions: tuple[str, ...]):
    for e in ELECTIONS.values():
        p = previous(e)
        if (e.jurisdiction in jurisdictions and p is not None and e.date < before
                and (PROCESSED / e.election_id / "primary.csv").exists()
                and (PROCESSED / p.election_id / "primary.csv").exists()):
            yield e, p


def new_party_pool(before: date) -> np.ndarray:
    """Shares (fractions) of minor parties at their first election in a state or
    territory, averaged over the seats or divisions they contested."""
    out = []
    for e, p in _pairs(before, STATES):
        cur = pl.read_csv(PROCESSED / e.election_id / "primary.csv", infer_schema_length=None)
        old = pl.read_csv(PROCESSED / p.election_id / "primary.csv", infer_schema_length=None)
        seats = cur["district"].n_unique()
        totals = cur.group_by("district").agg(pl.col("votes").sum().alias("f"))
        new = (cur.filter((pl.col("bloc") == "OTH") & (pl.col("party") != "IND")
                          & ~pl.col("party").is_in(old["party"].unique().implode()))
               .group_by("party", "district").agg(pl.col("votes").sum())
               .join(totals, on="district")
               .group_by("party").agg((pl.col("votes").sum() / pl.col("f").sum()).alias("s"),
                                      pl.col("district").n_unique().alias("n")))
        out.extend(new.filter(pl.col("n") >= MIN_CONTEST * seats)["s"].to_list())
    return np.array(out)


def new_ind_pool(before: date) -> np.ndarray:
    """First-time independents' shares (fractions) of their Hare-Clark division."""
    out = []
    for e, p in _pairs(before, HARE_CLARK):
        cur = pl.read_csv(PROCESSED / e.election_id / "primary.csv", infer_schema_length=None)
        old = pl.read_csv(PROCESSED / p.election_id / "primary.csv", infer_schema_length=None)
        before_keys = {_key(c) for c in old["candidate"].to_list()}
        totals = dict(cur.group_by("district").agg(pl.col("votes").sum()).iter_rows())
        for d, c, v in cur.filter(pl.col("party") == "IND").select("district", "candidate", "votes").iter_rows():
            if _key(c) not in before_keys:
                out.append(v / totals[d])
    return np.array(out)
