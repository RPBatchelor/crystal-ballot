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

LABEL_PATTERNS: list[tuple[str, str]] = [
    (r"\bdate\b|fieldwork", "date"),
    (r"firm|pollster|organisation|^poll", "pollster"),
    (r"client|commission|sponsor|publication|media", "client"),
    (r"sample", "sample"),
    (r"^(l/?np|lnp|coalition|lib/nat|liberal[-–/ ]national)$", "COAL"),
    (r"^(lib|liberal)$", "LIB"),
    (r"^(nat|nationals?)$", "NAT"),
    (r"^(alp|labor)$", "ALP"),
    (r"^(grn|greens?)$", "GRN"),
    (r"^(onp|one nation|phon)$", "ONP"),
    (r"^(ind|independents?)$", "IND"),
    (r"^(oth|others?)$", "OTH"),
]
TPP_HEADER = re.compile(r"\b(tpp|2pp|two[- ]party)", re.IGNORECASE)
INCLUDE_HEADING = re.compile(r"voting intention|opinion poll|^polling$", re.IGNORECASE)
EXCLUDE_HEADING = re.compile(
    r"council|premier|satisfaction|leader|seat|electorate|sub-state|three-party|"
    r"approval|preferred|metropolitan|regional|referendum", re.IGNORECASE)
PCT = re.compile(r"\d\s*%")


def _label_code(text: str) -> str | None:
    t = text.strip().lower()
    for pattern, code in LABEL_PATTERNS:
        if re.search(pattern, t):
            return code
    return None


def _n_header_rows(table: Table, grid: list[list[Cell | None]]) -> int:
    """Leading rows before the first data/event row (has a %, an event style, or a date)."""
    for r, (row, cells) in enumerate(zip(table.rows, grid)):
        texts = [c.text for c in cells if c is not None]
        if "DADADA" in row.attrs.upper() or any(PCT.search(t) for t in texts):
            return r
        if texts and parse_date_range(texts[0], 2000) is not None and not _label_code(texts[0]):
            return r
    return len(table.rows)


def _infer_columns(table: Table, grid: list[list[Cell | None]]) -> list[tuple[str, str]] | None:
    """(section, code) per grid column; section is 'meta', 'primary', 'tpp' or 'skip'.

    Labels come from the header cells stacked above each column (bottom-most known
    label wins); a spanning "TPP/2PP" header marks the two-party block.
    """
    n_header = _n_header_rows(table, grid)
    if n_header == 0:
        return None
    width = max(len(r) for r in grid[:n_header])
    swatches = _swatch_columns(table)
    cols: list[tuple[str, str]] = []
    for j in range(width):
        stack = [grid[r][j] for r in range(n_header) if j < len(grid[r]) and grid[r][j] is not None]
        code = next((c for c in (_label_code(cell.text) for cell in reversed(stack)) if c), None)
        is_tpp = any(TPP_HEADER.search(cell.text) for cell in stack)
        if code in ("date", "pollster", "client", "sample"):
            cols.append(("meta", code))
        elif code:
            cols.append(("tpp" if is_tpp else "primary", code))
        else:
            cols.append(("skip", ""))
    # Fall back to colour swatches for party columns the header text didn't name.
    if swatches and sum(1 for s, _ in cols if s in ("primary", "tpp")) < len(swatches):
        meta = [c for c in cols if c[0] == "meta"]
        primary, tpp = _value_columns(swatches)
        cols = meta + [("primary", c) for c in primary] + [("tpp", c) for c in tpp]
    # Older tables leave the date column's header blank.
    if cols and cols[0] == ("skip", "") and not any(c == "date" for _, c in cols):
        cols[0] = ("meta", "date")
    codes = {c for _, c in cols}
    if not {"date", "ALP"} <= codes:
        return None
    return cols


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

    # Single-pollster eras state the pollster in prose rather than a column.
    m = re.search(r"[Pp]olling\]? (?:was )?conducted by \[\[([^\]|]+)", wikitext)
    default_pollster = m.group(1) if m else "Unknown"

    polls: list[Poll] = []
    events: list[Event] = []
    results: list[Poll] = []  # election-result rows (pollster = "Election")
    for table in parse_tables(wikitext):
        ctx = context(table.start_line)
        titles = list(ctx.values())
        if not any(INCLUDE_HEADING.search(t) for t in titles):
            continue
        if any(EXCLUDE_HEADING.search(t) for t in titles if t != chamber_heading):
            continue
        year_heading = next((t for t in reversed(titles) if t.isdigit()), "")
        default_year = int(year_heading) if year_heading else date.today().year
        grid = table.grid()
        columns = _infer_columns(table, grid)
        if columns is None:
            continue
        n_header = _n_header_rows(table, grid)
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
            result = _election_row(cells, columns, jurisdiction)
            if result is not None:
                results.append(result)
                continue
            rec = _row_to_poll(cells, columns, jurisdiction, chamber_heading, default_year,
                               table.start_line, default_pollster)
            if rec is None:
                continue
            if rec.ALP is None:
                # Older tables mark leadership changes as plain rows spanning the table.
                text = max((c.text for c in cells if c is not None), key=len, default="")
                if len(text) > 25 and "sourced" not in text.lower():
                    # The date and description often share one cell: strip the leading date.
                    desc = re.sub(r"^\s*\d{1,2}\s+[A-Za-z]+\.?\s+\d{4}\s*[-–—:]?\s*", "", text)
                    events.append(Event(jurisdiction, rec.date_text, rec.field_end, desc.strip()))
                continue
            date_cell = cells[[c for _, c in columns].index("date")]
            if date_cell is not None and date_cell.inherited and polls:
                _merge_continuation(polls[-1], rec)
            else:
                polls.append(rec)
    return polls + _dedupe_results(results), events


def _election_row(cells: list[Cell | None], columns: list[tuple[str, str]],
                  jurisdiction: str) -> Poll | None:
    """An "<date> election" result row, returned as a Poll with pollster "Election"."""
    texts = [c.text for c in cells if c is not None]
    label = next((t for t in texts if "election" in t.lower()), None)
    if label is None:
        return None
    m = re.search(r"(\d{4})", label)
    if not m:
        return None
    rng = parse_date_range(label, int(m.group(1)))
    year = int(m.group(1))
    when = rng[1] if rng else date(year, 11, 30)  # month unknown: placeholder, fixed by caller
    rec = Poll(jurisdiction, "Legislative Assembly", "Election", None, when, when, label, None)
    for (sec, code), cell in zip(columns, cells):
        if cell is None or sec not in ("primary", "tpp"):
            continue
        v = parse_number(cell.text)
        if v is None:
            continue
        if sec == "primary":
            target = "COAL" if code in ("LIB", "NAT") else code
            cur = getattr(rec, target)
            setattr(rec, target, v if cur is None else cur + v)
        elif code == "ALP":
            rec.tpp_alp_vs_coal = v
    return rec if rec.ALP is not None else None


def _dedupe_results(results: list[Poll]) -> list[Poll]:
    by_year: dict[int, Poll] = {}
    for r in results:
        by_year.setdefault(r.field_end.year, r)
    return list(by_year.values())


def _row_to_poll(
    cells: list[Cell | None],
    columns: list[tuple[str, str]],
    jurisdiction: str,
    chamber: str,
    default_year: int,
    table_line: int,
    default_pollster: str = "Unknown",
) -> Poll | None:
    meta = {code: cells[j] for j, (sec, code) in enumerate(columns) if sec == "meta"}
    date_cell = meta.get("date")
    pollster_cell, client_cell, sample_cell = meta.get("pollster"), meta.get("client"), meta.get("sample")
    if date_cell is None or "election" in date_cell.text.lower():
        return None
    rng = parse_date_range(date_cell.text, default_year)
    if rng is None:
        return None
    # Older single-pollster tables (e.g. Newspoll-only) have no firm column.
    pollster = re.sub(r"\s+", " ", pollster_cell.text).strip() if pollster_cell else default_pollster
    if not pollster or "election" in pollster.lower() or "exit poll" in pollster.lower():
        return None
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
    seen: dict[int, list[str]] = {}
    values: dict[int, float | None] = {}
    for (sec, code), cell in zip(columns, cells):
        if sec != "primary" or cell is None:
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
    tpp = {
        ("COAL" if code in ("LIB", "NAT") else code): (parse_number(cell.text) if cell is not None else None)
        for (sec, code), cell in zip(columns, cells)
        if sec == "tpp"
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
    title: str, jurisdiction: str, slug: str, refresh: bool = True,
    window: tuple[date, date] | None = None, cycle: str | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Polls, events and election-result rows from one Wikipedia page.

    ``window`` (previous election, this election] keeps only this cycle's polls; pages
    often repeat polls from adjacent cycles.
    """
    raw_path = RAW_DIR / "wikipedia" / f"{slug}.wiki"
    if refresh or not raw_path.exists():
        fetch_wikitext(title, raw_path)
    parsed, events = parse_poll_page(raw_path.read_text(encoding="utf-8"), jurisdiction)
    df = pl.DataFrame([asdict(p) for p in parsed], infer_schema_length=None)
    is_result = pl.col("pollster") == "Election"
    results = df.filter(is_result)
    df = (
        df.filter(~is_result)
        # The same poll can appear at the boundary of two year tables.
        .unique(subset=["pollster", "field_start", "field_end", "ALP", "COAL"], keep="first",
                maintain_order=True)
        .with_columns(
            pl.sum_horizontal(PRIMARY_FIELDS).round(1).alias("primary_sum"),
        )
        .sort("field_end", descending=True)
    )
    ev = pl.DataFrame([asdict(e) for e in events]) if events else pl.DataFrame()
    if window is not None:
        lo, hi = window
        df = df.filter((pl.col("field_end") > lo) & (pl.col("field_start") < hi))
        if ev.height:
            ev = ev.filter(pl.col("event_date").is_null()
                           | ((pl.col("event_date") > lo) & (pl.col("event_date") <= hi)))
    if cycle is not None:
        df = df.with_columns(pl.lit(cycle).alias("cycle"))
    df = apply_corrections(df)
    return df, ev, results


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
