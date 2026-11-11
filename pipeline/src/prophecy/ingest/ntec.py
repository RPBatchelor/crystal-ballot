"""NT Electoral Commission division summaries: the official counts the Wikipedia
transcriptions (``wiki_nt``) are checked and corrected against.

The NTEC publishes, per election, a first-preference and a two-candidate-preferred
summary by division (saved by hand under ``data/raw/ntec/``; the site refuses automated
requests). They give votes by *party* only, so candidate names still come from
Wikipedia: ``reconcile`` overwrites each candidate's votes with the NTEC party total
(several independents in one division share the "Ind" total pro rata), and takes
formal, informal, enrolment and (2016, optional preferential) exhausted ballots from the
NTEC. In 2024 the two-candidate table is blank for most Labor v CLP divisions; those keep
Wikipedia's counts.
"""

from __future__ import annotations

from typing import Callable

import polars as pl

from prophecy import RAW_DIR

NTEC_DIR = RAW_DIR / "ntec"
# NTEC column headings -> our party codes (as ``wiki_nt`` assigns them).
PARTY = {"ALP": "ALP", "CLP": "CLP", "GRN": "GRN", "Ind": "IND", "TA": "TA", "1TP": "X_T", "CEC": "X_C",
         "SFP": "SFF", "AJP": "AJP", "BFFCPW": "X_BF", "FP": "X_AF"}
TOTALS = {"Formal", "Informal", "Total", "Roll", "% Turnout", "Exhausted"}


def _read(path) -> pl.DataFrame:
    df = pl.read_csv(path, encoding="utf8-lossy", infer_schema=False)
    df = df.rename({df.columns[0]: "district"})
    df = df.filter(pl.col("district").is_not_null() & (pl.col("district") != "Totals"))
    nums = [c for c in df.columns if c not in ("district", "% Turnout")]
    return df.with_columns(pl.col(c).str.replace_all(",", "").cast(pl.Int64) for c in nums)


def summaries(year: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(first preferences, two-candidate preferred) by division, one column per party."""
    fp = _read(NTEC_DIR / f"{year}_NT summary of first preference votes by division.csv")
    tcp = _read(NTEC_DIR / f"{year}_NT summary of two candidate preferred votes by division.csv")
    return fp, tcp


def _party_totals(row: dict) -> dict[str, int]:
    out = {}
    for col, v in row.items():
        if col in ("district", *TOTALS) or v is None:
            continue
        if col not in PARTY:
            raise ValueError(f"unknown NTEC party column {col!r}")
        out[PARTY[col]] = v
    return out


def _set_votes(rows: pl.DataFrame, totals: dict[str, int], where: str, log) -> pl.DataFrame:
    """One division's candidate rows with votes replaced by the NTEC party totals."""
    have = set(rows["party"])
    if have != set(totals):
        raise ValueError(f"{where}: parties differ (Wikipedia {sorted(have)}, NTEC {sorted(totals)})")
    out = []
    for party, total in totals.items():
        cands = rows.filter(pl.col("party") == party)
        wiki = int(cands["votes"].sum())
        if wiki != total:
            log(f"  {where} {party}: Wikipedia {wiki}, NTEC {total}")
        if wiki > 0:
            # Several candidates of one party (independents): share the total pro rata,
            # rounding so the parts add up.
            shares = [v * total / wiki for v in cands["votes"]]
        else:
            shares = [total / len(cands)] * len(cands)
        ints = [int(s) for s in shares]
        for i in sorted(range(len(ints)), key=lambda i: ints[i] - shares[i])[: total - sum(ints)]:
            ints[i] += 1
        out.append(cands.with_columns(pl.Series("votes", ints, dtype=pl.Int64)))
    df = pl.concat(out)
    return df.with_columns((100 * pl.col("votes") / pl.col("votes").sum()).round(3).alias("pct"))


def reconcile(year: int, tables: dict[str, pl.DataFrame],
              log: Callable[[str], None] = print) -> dict[str, pl.DataFrame]:
    """``wiki_nt`` tables with every count replaced by the NTEC's."""
    fp, tcp_n = summaries(year)
    fp_rows = {r["district"]: r for r in fp.iter_rows(named=True)}
    tcp_rows = {r["district"]: r for r in tcp_n.iter_rows(named=True)}
    primary, tcp = [], []
    for (d,), rows in tables["primary"].group_by("district", maintain_order=True):
        primary.append(_set_votes(rows, _party_totals(fp_rows[d]), f"{year} {d} primary", log))
    for (d,), rows in tables["tcp"].group_by("district", maintain_order=True):
        totals = _party_totals(tcp_rows[d])
        if not totals:  # NTEC table blank (2024 Labor v CLP divisions): keep Wikipedia's
            tcp.append(rows)
            continue
        tcp.append(_set_votes(rows, totals, f"{year} {d} 2CP", log))
    primary_df, tcp_df = pl.concat(primary), pl.concat(tcp)
    # The winner is whoever leads the final count (unchanged by these corrections).
    tcp_df = tcp_df.with_columns((pl.col("votes") == pl.col("votes").max().over("district")).alias("elected"))
    winners = dict(tcp_df.filter("elected").select("district", "candidate").iter_rows())
    before = dict(tables["districts"].select("district", "elected").iter_rows())
    changed = {d: (before[d], w) for d, w in winners.items() if before.get(d) != w}
    if changed:
        raise ValueError(f"{year}: NTEC counts change the winner: {changed}")
    primary_df = primary_df.with_columns(pl.col("candidate").is_in(list(winners.values())).alias("elected"))

    extra = pl.DataFrame([{"district": d, "formal_ntec": r["Formal"], "informal_ntec": r["Informal"],
                           "enrolment_ntec": r["Roll"],
                           "exhausted": tcp_rows[d].get("Exhausted")} for d, r in fp_rows.items()],
                         schema={"district": pl.String, "formal_ntec": pl.Int64, "informal_ntec": pl.Int64,
                                 "enrolment_ntec": pl.Int64, "exhausted": pl.Int64})
    districts = tables["districts"].join(extra, on="district", how="left").with_columns(
        pl.col("formal_ntec").alias("formal"), pl.col("informal_ntec").alias("informal"),
        pl.col("enrolment_ntec").alias("enrolment"),
    ).drop("formal_ntec", "informal_ntec", "enrolment_ntec")

    # Labor v CLP 2PP: the two-candidate count where those were the final two.
    tpp = tables["tpp"]
    counted = {}
    for (d,), t in tcp_df.group_by("district"):
        v = {b: n for b, n in t.select("bloc", "votes").iter_rows()}
        if set(v) == {"ALP", "COAL"}:
            counted[d] = (v["ALP"], v["COAL"])
    tpp = tpp.with_columns(
        pl.col("district").replace_strict({d: a for d, (a, _) in counted.items()}, default=None)
        .fill_null(pl.col("alp_votes")).alias("alp_votes"),
        pl.col("district").replace_strict({d: c for d, (_, c) in counted.items()}, default=None)
        .fill_null(pl.col("coal_votes")).alias("coal_votes"),
    ).with_columns((100 * pl.col("alp_votes") / (pl.col("alp_votes") + pl.col("coal_votes"))).round(3)
                   .alias("alp_tpp"))
    return {**tables, "primary": primary_df, "tcp": tcp_df, "final": tcp_df, "tpp": tpp, "districts": districts}
