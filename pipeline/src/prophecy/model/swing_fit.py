"""Seat-swing parameters estimated from past elections, in place of hand-set values.

The seat model moves each seat's primary for party b by the statewide logit swing plus
a regional effect, seat noise and candidate effects. This module estimates those terms
from pairs of consecutive elections on the same boundaries (or on the later
election's boundaries via a notional re-cut), in the same logit form the simulation
uses:

    logit(s1) = logit(s0) + c + beta * (logit(s0) - mean) + retire * R + sophomore * F
                + region + e,      e ~ t(df, 0, scale)

where c is the shift that makes the seats average to the statewide result, R flags
that the seat's sitting member (of party b) did not recontest, and F that they were
first elected at the previous election and did recontest. ``beta`` < 0 is regression
to the mean: a party's strongest seats swing against it relative to a uniform swing.

Only pairs whose later election came before a cut-off date are used, so a blind
backtest never learns from its own or later elections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import numpy as np
import polars as pl
from scipy import stats
from scipy.special import expit, logit

from prophecy import CURATED_DIR, DATA_DIR
from prophecy.jurisdictions import ELECTIONS, Election, previous
from prophecy.schema.parties import bloc

PROCESSED = DATA_DIR / "processed"
SINGLE_MEMBER = ("VIC", "NSW", "QLD", "WA", "SA", "NT", "FED")
FIT_BLOCS = ("ALP", "COAL", "GRN")
MIN_SHARE = 0.02  # a party below 2% at either election is a contest change, not a swing
MIN_OBS = 150  # per party; below this the hand-set defaults are kept
SHRINK_OBS = 150  # pseudo-observations pulling a jurisdiction's noise scale to the pooled one
REGION_FILES = {"vic-2013": "regions_assembly2013.csv", "vic-2021": "regions_assembly2022.csv"}


def _key(name: str | None) -> str | None:
    """'FOLEY, Martin' / 'HOOD Lucy' / "O'HANLON Cressida" -> 'FOLEY M' (surname, initial)."""
    if not name or not isinstance(name, str):
        return None
    if "," in name:
        surname, given = name.split(",", 1)
    else:
        words = name.split()
        k = 0
        while k < len(words) and words[k] == words[k].upper():
            k += 1
        k = max(k, 1)
        surname, given = " ".join(words[:k]), " ".join(words[k:])
    s = re.sub(r"[^A-Z]", "", surname.upper())
    g = re.sub(r"[^A-Z]", "", given.upper())
    return f"{s} {g[:1]}"


def _shares(primary: pl.DataFrame) -> pl.DataFrame:
    g = primary.group_by("district", "bloc").agg(pl.col("votes").sum())
    return (g.with_columns((pl.col("votes") / pl.col("votes").sum().over("district")).alias("s"),
                           pl.col("votes").sum().over("district").alias("w"))
            .select("district", "bloc", "s", "w"))


def _regions(e: Election) -> dict[str, str]:
    from prophecy.publish.results import slugify

    name = REGION_FILES.get(e.boundary_set, f"regions_{e.boundary_set}.csv")
    for path in (CURATED_DIR / name, PROCESSED / name):
        if path.exists():
            df = pl.read_csv(path)
            if "slug" in df.columns:
                return {"__slug__": "1", **dict(df.iter_rows())}
            return dict(df.select("district", "region").iter_rows())
    return {}


def pair_baseline(e: Election, prev: Election) -> tuple[pl.DataFrame, pl.DataFrame] | None:
    """(primary with bloc, districts with district/elected/elected_party) of ``prev`` on
    ``e``'s boundaries, or None when no such baseline exists."""
    if e.boundary_set == prev.boundary_set:
        src = PROCESSED / prev.election_id
        if not (src / "primary.csv").exists():
            return None
        prim = pl.read_csv(src / "primary.csv", infer_schema_length=None)
        d = pl.read_csv(src / "districts.csv", infer_schema_length=None)
        return prim, d.select("district", "elected", "elected_party")
    nd = PROCESSED / f"{e.election_id}-notional"
    if not (nd / "primary.csv").exists():
        return None
    d = pl.read_csv(nd / "districts.csv", infer_schema_length=None)
    if "origin_share" in d.columns:
        d = d.filter(pl.col("origin_share") >= 0.5)
    if "elected" not in d.columns:
        d = d.with_columns(pl.lit(None, dtype=pl.String).alias("elected"))
    return pl.read_csv(nd / "primary.csv", infer_schema_length=None), d.select("district", "elected", "elected_party")


def pairs(before: date) -> list[tuple[Election, Election]]:
    out = []
    for e in ELECTIONS.values():
        p = previous(e)
        if (e.jurisdiction in SINGLE_MEMBER and p is not None and e.date < before
                and (PROCESSED / e.election_id / "primary.csv").exists() and pair_baseline(e, p) is not None):
            out.append((e, p))
    return sorted(out, key=lambda x: x[0].date)


def _winners(eid: str) -> set[str] | None:
    """Members elected at ``eid``; None when that election is not ingested."""
    path = PROCESSED / eid / "districts.csv"
    if not path.exists():
        return None
    return {k for k in map(_key, pl.read_csv(path, infer_schema_length=None)["elected"].to_list()) if k}


def _by_election_seats(e: Election, prev: Election) -> set[str]:
    path = CURATED_DIR / f"by_elections_{e.jurisdiction.lower()}.csv"
    if not path.exists():
        return set()
    by = pl.read_csv(path, try_parse_dates=True)
    return set(by.filter((pl.col("date") > prev.date) & (pl.col("date") < e.date))["district"].to_list())


def observations(e: Election, prev: Election) -> pl.DataFrame:
    """One row per seat and party (ALP, COAL, GRN) of the pair: shares, covariates, region."""
    from prophecy.publish.results import slugify

    base_primary, base_d = pair_baseline(e, prev)
    s0 = _shares(base_primary).rename({"s": "s0", "w": "w0"})
    nxt = pl.read_csv(PROCESSED / e.election_id / "primary.csv", infer_schema_length=None)
    s1 = _shares(nxt).rename({"s": "s1", "w": "w1"})
    ballot: dict[str, set] = {}
    for d, c in nxt.select("district", "candidate").iter_rows():
        ballot.setdefault(d, set()).add(_key(c))
    pp = previous(prev)
    earlier = _winners(pp.election_id) if pp else None  # unknown: no first-term flags
    skip = _by_election_seats(e, prev)
    regions = _regions(e)
    rows = []
    for d, member, party in base_d.iter_rows():
        if d in skip or party is None:
            continue
        b = bloc(party)
        k = _key(member)
        if e.jurisdiction == "FED" and k is None:
            sitting = nxt.filter((pl.col("district") == d) & pl.col("sitting").cast(pl.Boolean)) if "sitting" in nxt.columns else None
            recontest = sitting is not None and sitting.height > 0
            known = True
        else:
            recontest = k is not None and k in ballot.get(d, set())
            known = k is not None
        first_term = known and earlier is not None and k is not None and k not in earlier
        if regions.get("__slug__"):
            region = regions.get(slugify(d))
        else:
            region = regions.get(d)
        for fb in FIT_BLOCS:
            rows.append({"pair": e.election_id, "jurisdiction": e.jurisdiction, "district": d, "bloc": fb,
                         "region": region,
                         "retire": float(known and b == fb and not recontest),
                         "sophomore": float(b == fb and recontest and first_term)})
    cov = pl.DataFrame(rows, schema_overrides={"region": pl.String})
    return (cov.join(s0, on=["district", "bloc"], how="inner").join(s1, on=["district", "bloc"], how="inner")
            .filter((pl.col("s0") > MIN_SHARE) & (pl.col("s1") > MIN_SHARE)))


def _shift(l0: np.ndarray, w: np.ndarray, target: float) -> float:
    lo, hi = -6.0, 6.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if expit(l0 + mid) @ w > target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


@dataclass
class SwingParams:
    scale: dict[str, float]  # t scale of seat noise (logit), net of regional variance
    df: dict[str, float]
    beta: dict[str, float]  # regression to the mean
    retire: float
    sophomore: float
    region_sd: float
    n: dict[str, int]
    pairs: list[str]

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def fit(before: date, jurisdiction: str | None = None, log=print) -> SwingParams | None:
    """Estimate the seat-swing terms from pairs whose later election precedes ``before``.

    Coefficients and the tail shape are pooled over every jurisdiction; the noise scale
    is ``jurisdiction``'s own, shrunk toward the pooled scale (the NT's small seats swing
    about twice as much as other states')."""
    ps = pairs(before)
    if not ps:
        return None
    obs = pl.concat([observations(e, p) for e, p in ps])
    scale, df_, beta, n = {}, {}, {}, {}
    X_all, y_all, resid_rows = [], [], []
    for (pair, b), g in obs.group_by("pair", "bloc", maintain_order=True):
        l0, l1 = logit(g["s0"].to_numpy()), logit(g["s1"].to_numpy())
        w0 = g["w0"].to_numpy() / g["w0"].sum()
        w1 = g["w1"].to_numpy() / g["w1"].sum()
        # Shift so the seats average to the later statewide share (seat-weighted, as in
        # the simulation's re-centring).
        c = _shift(l0, w0, float(g["s1"].to_numpy() @ w1))
        centred = l0 - l0 @ w0
        y = l1 - l0 - c
        slopes = np.zeros((len(y), len(FIT_BLOCS)))
        slopes[:, FIT_BLOCS.index(b)] = centred  # one regression-to-the-mean slope per party
        X_all.append(np.column_stack([slopes, g["retire"].to_numpy(), g["sophomore"].to_numpy()]))
        y_all.append(y)
        resid_rows.append(g.select("pair", "jurisdiction", "bloc", "region"))
    X, y = np.vstack(X_all), np.concatenate(y_all)
    design = np.column_stack([X, np.ones(len(y))])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    r = pl.concat(resid_rows).with_columns(pl.Series("r", y - design @ coef))
    # Regional variance: spread of region means beyond what seat noise alone explains,
    # per pair and party; the median, as a few small-seat pairs (NT) are extreme.
    region_var = []
    for _, g in r.filter(pl.col("region").is_not_null()).group_by("pair", "bloc"):
        m = (g.group_by("region").agg(pl.col("r").mean().alias("m"), pl.col("r").var().alias("v"),
                                      pl.len().alias("k")).filter(pl.col("k") >= 3))
        if m.height >= 3:
            region_var.append(max(float(m["m"].var() - (m["v"] / m["k"]).mean()), 0.0))
    region_sd = float(np.sqrt(np.median(region_var))) if region_var else 0.06
    for k, b in enumerate(FIT_BLOCS):
        rb = r.filter(pl.col("bloc") == b)
        all_r = rb["r"].to_numpy()
        n[b] = len(all_r)
        d, _, sc = stats.t.fit(all_r, floc=0)
        d = float(np.clip(d, 2.5, 30))
        _, _, sc = stats.t.fit(all_r, f0=d, floc=0)
        own = rb.filter(pl.col("jurisdiction") == jurisdiction)["r"].to_numpy() if jurisdiction else np.array([])
        if len(own) >= 20:
            _, _, sc_j = stats.t.fit(own, f0=d, floc=0)
            sc = float(np.sqrt((len(own) * sc_j ** 2 + SHRINK_OBS * sc ** 2) / (len(own) + SHRINK_OBS)))
        # Net of the regional component (variance of a t is scale^2 * df / (df - 2)).
        total_var = sc ** 2 * d / (d - 2)
        seat_var = max(total_var - region_sd ** 2, 0.25 * total_var)
        scale[b] = round(float(np.sqrt(seat_var * (d - 2) / d)), 4)
        df_[b] = round(d, 2)
        beta[b] = round(float(coef[k]), 4)
    p = SwingParams(scale=scale, df=df_, beta=beta, retire=round(float(coef[3]), 4),
                    sophomore=round(float(coef[4]), 4), region_sd=round(region_sd, 4), n=n,
                    pairs=[e.election_id for e, _ in ps])
    log(f"seat-swing fit ({jurisdiction or 'pooled'}) on {len(ps)} pairs before {before}: {p.as_dict()}")
    return p


def apply(cfg, p: SwingParams | None):
    """Copy estimated terms onto a SimConfig, keeping defaults for thin estimates."""
    if p is None:
        return cfg
    for b in FIT_BLOCS:
        if p.n.get(b, 0) >= MIN_OBS:
            cfg.seat_sd[b] = p.scale[b]
            cfg.seat_df[b] = p.df[b]
            cfg.seat_beta[b] = p.beta[b]
    if min(p.n.values()) >= MIN_OBS:
        cfg.retire_effect, cfg.sophomore_effect, cfg.region_sd = p.retire, p.sophomore, p.region_sd
    # Others have no estimate of their own: give them the majors' tail shape.
    cfg.seat_df.setdefault("OTH", min(cfg.seat_df.values()) if cfg.seat_df else 30.0)
    return cfg
