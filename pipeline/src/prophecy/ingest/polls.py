"""Ingest state voting-intention polls from Wikipedia "Opinion polling for ..." pages.

Wikipedia is a convenient index, not the source of truth: every row keeps its source
URL so it can be checked against the pollster's release, and hand corrections live in
``data/curated/poll_corrections.csv`` (applied after parsing).

Column layout is read from each table's colour-swatch header row (the row of empty
``data-sort-type="number"`` cells), which lists one party per leaf column. This makes
the parser robust to the layout changing year-to-year (e.g. One Nation only being
broken out from 2026, or LIB/NAT being split in early tables).
"""

from __future__ import annotations

import calendar
import os
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import httpx
import polars as pl

from prophecy import CURATED_DIR, RAW_DIR
from prophecy.ingest.wikitable import Cell, Table, parse_tables

WIKI_RAW_URL = "https://en.wikipedia.org/w/index.php?title={title}&action=raw"
# Wikimedia's robot policy requires a User-Agent with real contact details
# (URL or email); generic agents get 403. Set e.g.
#   PROPHECY_USER_AGENT="prophecy/0.1 (https://your-site; you@example.org)"
USER_AGENT_ENV = "PROPHECY_USER_AGENT"

# Wikipedia party-colour template names -> canonical party codes.
SWATCH_PARTY = {
    "labor": "ALP",
    "coalition": "COAL",
    "liberal": "LIB",
    "national": "NAT",
    "greens": "GRN",
    "one nation": "ONP",
    "independent": "IND",
    "lightgray": "OTH",
    "lightgrey": "OTH",
}
PRIMARY_FIELDS = ["ALP", "COAL", "GRN", "ONP", "IND", "OTH"]

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_name) if m})
MONTHS["sept"] = 9


@dataclass
class Poll:
    jurisdiction: str
    chamber: str
    pollster: str
    client: str | None
    field_start: date
    field_end: date
    date_text: str
    sample_size: int | None
    ALP: float | None = None
    COAL: float | None = None
    GRN: float | None = None
    ONP: float | None = None  # None => One Nation not reported separately (inside OTH)
    IND: float | None = None  # None => independents not reported separately (inside OTH)
    OTH: float | None = None
    tpp_alp_vs_coal: float | None = None  # ALP share of ALP-v-Coalition 2PP
    tpp_alp_vs_onp: float | None = None  # ALP share of ALP-v-One Nation 2PP
    source_line: int = 0


@dataclass
class Event:
    jurisdiction: str
    date_text: str
    event_date: date | None
    description: str


# --------------------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------------------

def fetch_wikitext(title: str, dest: Path) -> Path:
    user_agent = os.environ.get(USER_AGENT_ENV)
    if not user_agent:
        raise RuntimeError(
            f"Set {USER_AGENT_ENV} to a User-Agent with contact details to download from "
            "Wikipedia (see https://w.wiki/4wJS), or rerun with --no-refresh."
        )
    url = WIKI_RAW_URL.format(title=title.replace(" ", "_"))
    resp = httpx.get(url, headers={"User-Agent": user_agent}, follow_redirects=True, timeout=60)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(resp.text, encoding="utf-8")
    return dest


# --------------------------------------------------------------------------------------
# Parsing helpers
# --------------------------------------------------------------------------------------

def parse_number(text: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else None


def parse_date_range(text: str, default_year: int) -> tuple[date, date] | None:
    """Parse fieldwork ranges like '15–22 Oct', '24 Nov – 8 Dec 2025', 'Sep–Oct 2023'."""
    t = text.replace("–", "-").replace("—", "-").replace(" ", " ")
    t = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", t)
    tokens = re.findall(r"\d{4}|\d{1,2}|[A-Za-z]+", t)
    parts: list[dict] = []  # each: {day, month, year}
    cur: dict = {}
    for tok in tokens:
        low = tok.lower()
        if tok.isdigit() and len(tok) == 4:
            cur["year"] = int(tok)
        elif tok.isdigit():
            if "day" in cur:
                parts.append(cur)
                cur = {}
            cur["day"] = int(tok)
        elif low[:4] in MONTHS or low[:3] in MONTHS:
            month = MONTHS.get(low[:4], MONTHS.get(low[:3]))
            if "month" in cur:
                parts.append(cur)
                cur = {}
            cur["month"] = month
    if cur:
        parts.append(cur)
    parts = [p for p in parts if p]
    if not parts or not any("month" in p for p in parts):
        return None
    # Propagate month/year backwards ("15-22 Oct" -> start month Oct) and forwards.
    last_month = next(p["month"] for p in reversed(parts) if "month" in p)
    last_year = next((p["year"] for p in reversed(parts) if "year" in p), default_year)
    for p in reversed(parts):
        p.setdefault("month", last_month)
        p.setdefault("year", last_year)
        last_month, last_year = p["month"], p["year"]
    start, end = parts[0], parts[-1]
    # A start month after the end month means the range crosses a year boundary.
    if (start["year"], start["month"]) > (end["year"], end["month"]):
        start["year"] = end["year"] - 1
    s_day = start.get("day", 1)
    e_day = end.get("day", calendar.monthrange(end["year"], end["month"])[1])
    try:
        return date(start["year"], start["month"], s_day), date(end["year"], end["month"], e_day)
    except ValueError:
        return None


def _swatch_columns(table: Table) -> list[str] | None:
    """Return party code per leaf column from the colour-swatch header row."""
    for row in table.rows:
        swatches = [c for c in row.cells if c.header and "data-sort-type" in _attrs_of(c)]
        if swatches:
            codes = []
            for c in swatches:
                m = re.search(r"party colours\|([^}]+)\}\}", _attrs_of(c))
                key = (m.group(1) if m else re.search(r"background:\s*([a-z]+)", _attrs_of(c)).group(1))
                codes.append(SWATCH_PARTY.get(key.strip().lower(), key.strip().upper()))
            return codes
    return None


def _attrs_of(cell: Cell) -> str:
    return cell.attrs


def _value_columns(swatches: list[str]) -> tuple[list[str], list[str]]:
    """Split swatch codes into primary-vote columns and 2PP columns.

    Primary block ends when ALP appears for the second time.
    """
    second_alp = swatches.index("ALP", 1)
    return swatches[:second_alp], swatches[second_alp:]


# --------------------------------------------------------------------------------------
# Main parser
# --------------------------------------------------------------------------------------

def parse_poll_page(
    wikitext: str, jurisdiction: str, chamber_heading: str = "Legislative Assembly"
) -> tuple[list[Poll], list[Event]]:
    lines = wikitext.splitlines()
    # Map each table to the (sub)section headings above it.
    headings: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = re.match(r"^(=+)\s*(.*?)\s*=+\s*$", line)
        if m:
            headings.append((i + 1, len(m.group(1)), m.group(2)))

    def context(line_no: int) -> dict[int, str]:
        ctx: dict[int, str] = {}
        for ln, level, title in headings:
            if ln > line_no:
                break
            ctx = {k: v for k, v in ctx.items() if k < level}
            ctx[level] = title
        return ctx

    polls: list[Poll] = []
    events: list[Event] = []
    for table in parse_tables(wikitext):
        ctx = context(table.start_line)
        if ctx.get(2) != "Voting intention" or ctx.get(3) != chamber_heading:
            continue
        year_heading = ctx.get(4, "")
        default_year = int(year_heading) if year_heading.isdigit() else date.today().year
        swatches = _swatch_columns(table)
        if not swatches:
            continue
        primary_cols, tpp_cols = _value_columns(swatches)
        meta_cols = ["date", "pollster", "client", "sample"]
        columns = meta_cols + primary_cols + tpp_cols
        n_header = _header_rows(table)
        grid = table.grid()
        for r, (row, cells) in enumerate(zip(table.rows, grid)):
            if r < n_header or not cells:
                continue
            if "DADADA" in row.attrs.upper():
                texts = [c.text for c in cells if c is not None]
                if len(texts) >= 2:
                    rng = parse_date_range(texts[0], default_year)
                    events.append(
                        Event(jurisdiction, texts[0], rng[1] if rng else None, texts[-1])
                    )
                continue
            if len(cells) < len(columns):
                cells = cells + [None] * (len(columns) - len(cells))
            rec = _row_to_poll(
                cells, columns, len(meta_cols), len(primary_cols), jurisdiction,
                chamber_heading, default_year, table.start_line,
            )
            if rec is None:
                continue
            date_cell = cells[0]
            if date_cell is not None and date_cell.inherited and polls:
                _merge_continuation(polls[-1], rec)
            else:
                polls.append(rec)
    return polls, events


def _header_rows(table: Table) -> int:
    n = 0
    for row in table.rows:
        if row.cells and all(c.header for c in row.cells):
            n += 1
        else:
            break
    return n


def _row_to_poll(
    cells: list[Cell | None],
    columns: list[str],
    n_meta: int,
    n_primary: int,
    jurisdiction: str,
    chamber: str,
    default_year: int,
    table_line: int,
) -> Poll | None:
    date_cell, pollster_cell, client_cell, sample_cell = cells[:4]
    if date_cell is None or pollster_cell is None:
        return None
    rng = parse_date_range(date_cell.text, default_year)
    if rng is None:
        return None
    pollster = re.sub(r"\s+", " ", pollster_cell.text).strip()
    rec = Poll(
        jurisdiction=jurisdiction,
        chamber=chamber,
        pollster=pollster,
        client=(client_cell.text or None) if client_cell else None,
        field_start=rng[0],
        field_end=rng[1],
        date_text=date_cell.text,
        sample_size=int(parse_number(sample_cell.text)) if sample_cell and parse_number(sample_cell.text) else None,
        source_line=table_line,
    )

    # Primary votes: group grid columns by source cell so merged cells are detected.
    primary = columns[n_meta : n_meta + n_primary]
    seen: dict[int, list[str]] = {}
    values: dict[int, float | None] = {}
    for code, cell in zip(primary, cells[n_meta : n_meta + n_primary]):
        if cell is None:
            continue
        key = id(cell) if not cell.inherited else hash((cell.origin, cell.raw))
        seen.setdefault(key, []).append(code)
        values[key] = parse_number(cell.text)
    for key, codes in seen.items():
        target = _merge_target(codes)
        val = values[key]
        if val is None:
            continue
        current = getattr(rec, target)
        setattr(rec, target, val if current is None else current + val)

    # 2PP block: ALP + one opponent.
    tpp_codes = columns[n_meta + n_primary :]
    tpp = {
        code: (parse_number(cell.text) if cell is not None else None)
        for code, cell in zip(tpp_codes, cells[n_meta + n_primary :])
    }
    alp = tpp.get("ALP")
    if alp is not None:
        if tpp.get("COAL") is not None:
            rec.tpp_alp_vs_coal = alp
        elif tpp.get("ONP") is not None:
            rec.tpp_alp_vs_onp = alp
    return rec


def _merge_target(codes: list[str]) -> str:
    """Field that receives a value spanning several leaf columns."""
    unique = list(dict.fromkeys(codes))
    if len(unique) == 1:
        code = unique[0]
        return "COAL" if code in ("LIB", "NAT") else code
    if set(unique) <= {"LIB", "NAT", "COAL"}:
        return "COAL"
    # Any merge involving Others (e.g. IND+OTH, ONP+OTH) is reported as Others.
    return "OTH"


def _merge_continuation(base: Poll, cont: Poll) -> None:
    """Fold a rowspan continuation row (alternative 2PP) into its parent poll."""
    if cont.tpp_alp_vs_onp is not None:
        base.tpp_alp_vs_onp = cont.tpp_alp_vs_onp
    if cont.tpp_alp_vs_coal is not None and base.tpp_alp_vs_coal is None:
        base.tpp_alp_vs_coal = cont.tpp_alp_vs_coal


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------

def ingest_wikipedia_polls(
    title: str, jurisdiction: str, slug: str, refresh: bool = True
) -> tuple[pl.DataFrame, pl.DataFrame]:
    raw_path = RAW_DIR / "wikipedia" / f"{slug}.wiki"
    if refresh or not raw_path.exists():
        fetch_wikitext(title, raw_path)
    polls, events = parse_poll_page(raw_path.read_text(encoding="utf-8"), jurisdiction)
    df = pl.DataFrame([asdict(p) for p in polls])
    df = (
        # Election-result reference rows are not polls; results come from the EC.
        df.filter(~pl.col("pollster").str.to_lowercase().str.contains("election"))
        # The same poll can appear at the boundary of two year tables.
        .unique(subset=["pollster", "field_start", "field_end", "ALP", "COAL"], keep="first",
                maintain_order=True)
        .with_columns(
            pl.sum_horizontal(PRIMARY_FIELDS).round(1).alias("primary_sum"),
        )
        .sort("field_end", descending=True)
    )
    df = apply_corrections(df)
    ev = pl.DataFrame([asdict(e) for e in events]) if events else pl.DataFrame()
    return df, ev


def apply_corrections(df: pl.DataFrame) -> pl.DataFrame:
    """Apply hand corrections keyed by (pollster, field_end)."""
    path = CURATED_DIR / "poll_corrections.csv"
    if not path.exists():
        return df
    fixes = pl.read_csv(path, try_parse_dates=True)
    for fix in fixes.iter_rows(named=True):
        mask = (pl.col("pollster") == fix["pollster"]) & (pl.col("field_end") == fix["field_end"])
        if fix["field"] == "DROP":
            df = df.filter(~mask)
            continue
        value = fix["value"]
        df = df.with_columns(
            pl.when(mask).then(pl.lit(value).cast(df.schema[fix["field"]])).otherwise(pl.col(fix["field"])).alias(fix["field"])
        )
    return df
