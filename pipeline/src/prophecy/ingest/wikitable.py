"""Minimal MediaWiki table parser.

Turns ``{| ... |}`` wikitext into a rectangular grid, expanding rowspan/colspan so
every logical column lines up. Each grid cell remembers where it came from so callers
can tell a merged cell (e.g. one value spanning IND and Others) from two real values.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field


@dataclass
class Cell:
    text: str  # cleaned display text
    raw: str  # original wikitext content (attributes stripped)
    header: bool
    rowspan: int = 1
    colspan: int = 1
    attrs: str = ""  # cell attributes, e.g. style="background:..."
    # Filled in during grid expansion:
    origin: tuple[int, int] = (0, 0)  # (row, col) of the source cell
    inherited: bool = False  # True when copied down by rowspan


@dataclass
class Row:
    cells: list[Cell]
    attrs: str = ""  # attributes on the ``|-`` line, e.g. a background style


@dataclass
class Table:
    rows: list[Row] = field(default_factory=list)
    start_line: int = 0

    def grid(self) -> list[list[Cell | None]]:
        """Expand rowspans/colspans into a rectangular grid of cells."""
        grid: list[list[Cell | None]] = []
        pending: dict[int, tuple[Cell, int]] = {}  # col -> (cell, rows remaining)
        for r, row in enumerate(self.rows):
            out: list[Cell | None] = []
            col = 0
            queue = list(row.cells)

            def fill_pending() -> None:
                nonlocal col
                while col in pending:
                    cell, left = pending[col]
                    out.append(_copy(cell, inherited=True))  # noqa: B023 (called within iteration)
                    if left <= 1:
                        del pending[col]
                    else:
                        pending[col] = (cell, left - 1)
                    col += 1

            fill_pending()
            for cell in queue:
                cell.origin = (r, col)
                for _ in range(cell.colspan):
                    out.append(cell)
                    if cell.rowspan > 1:
                        pending[col] = (cell, cell.rowspan - 1)
                    col += 1
                fill_pending()
            # Rowspans reaching past the last explicit cell of this row.
            for c in sorted(k for k in pending if k >= col):
                while col < c:
                    out.append(None)
                    col += 1
                fill_pending()
            grid.append(out)
        return grid


def _copy(cell: Cell, inherited: bool) -> Cell:
    c = Cell(cell.text, cell.raw, cell.header, cell.rowspan, cell.colspan, cell.attrs, cell.origin)
    c.inherited = inherited
    return c


# --------------------------------------------------------------------------------------
# Wikitext cleaning
# --------------------------------------------------------------------------------------

def _strip_balanced(text: str, opener: str, closer: str, predicate) -> str:
    """Remove balanced ``opener...closer`` spans whose inner text satisfies predicate."""
    out, i = [], 0
    while i < len(text):
        if text.startswith(opener, i):
            depth, j = 1, i + len(opener)
            while j < len(text) and depth:
                if text.startswith(opener, j):
                    depth += 1
                    j += len(opener)
                elif text.startswith(closer, j):
                    depth -= 1
                    j += len(closer)
                else:
                    j += 1
            inner = text[i + len(opener) : j - len(closer)]
            if predicate(inner):
                out.append("\n" * text.count("\n", i, j))  # keep line numbers stable
                i = j
                continue
            out.append(text[i:j])
            i = j
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


_REF_RE = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.DOTALL | re.IGNORECASE)
_DROP_TEMPLATES = ("efn", "refn", "cn", "citation needed", "sfn", "subscription", "update")


def clean(text: str) -> str:
    """Reduce a wikitext fragment to plain display text."""
    text = _REF_RE.sub("", text)
    text = _strip_balanced(
        text, "{{", "}}", lambda inner: inner.split("|")[0].strip().lower() in _DROP_TEMPLATES
    )
    text = re.sub(r"\{\{\s*n/?a\s*\}\}", "", text, flags=re.IGNORECASE)
    text = text.replace("{{!}}", "|")  # escaped pipe, e.g. inside [[Page{{!}}Label]]
    # Dash templates: {{ndash}}, {{en dash}}, {{snd}} (spaced en dash), ...
    text = re.sub(r"\{\{\s*(?:ndash|en ?dash|snd|spaced ndash)\s*\}\}", "–", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"\{\{\s*(?:mdash|em ?dash)\s*\}\}", "—", text, flags=re.IGNORECASE)
    text = html.unescape(text)  # &ndash; &nbsp; ...
    # {{tooltip|LABEL|explanation}} shows LABEL.
    text = re.sub(r"\{\{\s*(?:tooltip|abbr)\s*\|([^|{}]*)\|[^{}]*\}\}", r"\1", text, flags=re.IGNORECASE)
    # Unwrap simple templates: {{nowrap|x}} -> x ; other templates -> last arg.
    for _ in range(3):
        text = re.sub(r"\{\{([^{}]*)\}\}", lambda m: m.group(1).split("|")[-1], text)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)  # [[a|b]] -> b
    text = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", text)  # [url label] -> label
    text = re.sub(r"\[https?://\S+\]", "", text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("'''", "").replace("''", "").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def _split_top(text: str, sep: str) -> list[str]:
    """Split on ``sep`` only where not nested inside [[...]] or {{...}}."""
    parts, depth, buf, i = [], 0, [], 0
    while i < len(text):
        two = text[i : i + 2]
        if two in ("[[", "{{"):
            depth += 1
            buf.append(two)
            i += 2
            continue
        if two in ("]]", "}}"):
            depth = max(0, depth - 1)
            buf.append(two)
            i += 2
            continue
        if depth == 0 and text.startswith(sep, i):
            parts.append("".join(buf))
            buf = []
            i += len(sep)
            continue
        buf.append(text[i])
        i += 1
    parts.append("".join(buf))
    return parts


_SPAN_RE = re.compile(r'(rowspan|colspan)\s*=\s*"?(\d+)"?', re.IGNORECASE)
_ATTR_RE = re.compile(r"(?:^|\s)[a-z-]+\s*=", re.IGNORECASE)


def _parse_cell(chunk: str, header: bool) -> Cell:
    pieces = _split_top(chunk, "|")
    if len(pieces) >= 2 and "[" not in pieces[0] and _ATTR_RE.search(pieces[0]):
        attrs, content = pieces[0], "|".join(pieces[1:])
    else:
        attrs, content = "", chunk
    # A lone "attrs" that is really a value (e.g. "|5%| 5%") is harmless: content wins.
    spans = {k.lower(): int(v) for k, v in _SPAN_RE.findall(attrs)}
    return Cell(
        text=clean(content),
        raw=content.strip(),
        header=header,
        rowspan=spans.get("rowspan", 1),
        colspan=spans.get("colspan", 1),
        attrs=attrs.strip(),
    )


def parse_tables(wikitext: str) -> list[Table]:
    """Parse every top-level table in a page."""
    tables: list[Table] = []
    # Citations and footnotes often span several lines; a continuation line such as
    # "|access-date=..." would otherwise be read as a new table cell.
    # Removed text is replaced by its newlines so line numbers (used to match tables to
    # section headings) stay aligned with the original page.
    wikitext = _REF_RE.sub(lambda m: "\n" * m.group(0).count("\n"), wikitext)
    wikitext = _strip_balanced(
        wikitext, "{{", "}}", lambda inner: inner.split("|")[0].strip().lower() in _DROP_TEMPLATES
    )
    lines = wikitext.splitlines()
    current: Table | None = None
    row: Row | None = None
    last_cell: Cell | None = None
    depth = 0
    for n, line in enumerate(lines):
        s = line.strip()
        if s.startswith("{|"):
            depth += 1
            if depth == 1:
                current, row, last_cell = Table(start_line=n + 1), None, None
            continue
        if current is None:
            continue
        if s.startswith("|}"):
            depth -= 1
            if depth == 0:
                if row is not None and row.cells:
                    current.rows.append(row)
                tables.append(current)
                current = None
            continue
        if depth > 1:
            continue
        if s.startswith("|-"):
            if row is not None and row.cells:
                current.rows.append(row)
            row, last_cell = Row(cells=[], attrs=s[2:].strip()), None
            continue
        if s.startswith("|+"):
            continue
        if s.startswith(("!", "|")):
            if row is None:
                row = Row(cells=[])
            header = s.startswith("!")
            body = s[1:]
            sep = "!!" if header else "||"
            for chunk in _split_top(body, sep):
                last_cell = _parse_cell(chunk, header)
                row.cells.append(last_cell)
        elif last_cell is not None and s:
            # Continuation of a multi-line cell.
            last_cell.raw += "\n" + s
            last_cell.text = clean(last_cell.raw) if last_cell.text or s else last_cell.text
    return tables
