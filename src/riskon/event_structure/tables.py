"""Dense rowspan/colspan table normalisation."""

from __future__ import annotations

from lxml.html import HtmlElement  # type: ignore[import-untyped]

from riskon.event_structure.icons import icons_in
from riskon.event_structure.ir import Cell, ParseIssue, Table

CELL_TAGS = ("td", "th")


def _int_attr(element: HtmlElement, name: str) -> int:
    raw = element.get(name)
    if raw is None:
        return 1
    try:
        value = int(raw)
    except ValueError:
        return 1
    return value if value > 0 else 1


def _cell_text(element: HtmlElement) -> str:
    """Read a cell without folding nested-table content into its parent."""

    parts: list[str] = []
    if element.text:
        parts.append(element.text)
    for child in element:
        if isinstance(child.tag, str) and child.tag == "table":
            if child.tail:
                parts.append(child.tail)
            continue
        if isinstance(child.tag, str) and child.tag == "br":
            parts.append(" ")
        parts.append(_cell_text(child))
        if child.tail:
            parts.append(child.tail)
    return " ".join("".join(parts).split())


def _rows_of(table: HtmlElement) -> list[HtmlElement]:
    return [tr for tr in table.iter("tr") if next(tr.iterancestors("table"), None) is table]


def build_table(element: HtmlElement, index: int) -> tuple[Table, list[ParseIssue]]:
    """Expand merged cells into a dense grid and quarantine unsafe geometry/icons."""

    issues: list[ParseIssue] = []
    occupied: dict[tuple[int, int], Cell] = {}
    for row_index, tr in enumerate(_rows_of(element)):
        col = 0
        for cell_element in tr:
            if not isinstance(cell_element.tag, str) or cell_element.tag not in CELL_TAGS:
                continue
            while (row_index, col) in occupied:
                col += 1
            colspan = _int_attr(cell_element, "colspan")
            rowspan = _int_attr(cell_element, "rowspan")
            text = _cell_text(cell_element)
            icons = icons_in(cell_element)
            is_header = cell_element.tag == "th"
            for row_delta in range(rowspan):
                for col_delta in range(colspan):
                    occupied[(row_index + row_delta, col + col_delta)] = Cell(
                        row=row_index + row_delta,
                        col=col + col_delta,
                        text=text,
                        icons=icons,
                        is_header=is_header,
                        spanned=bool(row_delta or col_delta),
                    )
            for icon in icons:
                if not icon.known:
                    issues.append(
                        ParseIssue(
                            code="unknown_icon",
                            severity="quarantine",
                            detail=f"unrecognised icon name {icon.name!r} ({icon.encoding})",
                            table_index=index,
                            row=row_index,
                        )
                    )
            col += colspan

    n_rows = max((row for row, _col in occupied), default=-1) + 1
    n_cols = max((col for _row, col in occupied), default=-1) + 1
    grid = [
        [occupied.get((row, col), Cell(row=row, col=col)) for col in range(n_cols)]
        for row in range(n_rows)
    ]
    header_rows = 0
    for grid_row in grid:
        if grid_row and all(cell.is_header for cell in grid_row):
            header_rows += 1
        else:
            break
    for row_index in range(n_rows):
        filled = sum((row_index, col) in occupied for col in range(n_cols))
        if filled != n_cols:
            issues.append(
                ParseIssue(
                    code="ragged_row",
                    severity="quarantine",
                    detail=f"row covers {filled} of {n_cols} columns",
                    table_index=index,
                    row=row_index,
                )
            )
    if n_rows and not header_rows:
        issues.append(
            ParseIssue(
                code="no_header_row",
                severity="note",
                detail="no <th> row: column labels are not declared",
                table_index=index,
            )
        )
    if any(table is not element for table in element.iter("table")):
        issues.append(
            ParseIssue(
                code="nested_table",
                severity="note",
                detail="nested table content was not folded into the parent cell",
                table_index=index,
            )
        )
    return (
        Table(
            index=index,
            n_rows=n_rows,
            n_cols=n_cols,
            header_rows=header_rows,
            grid=grid,
        ),
        issues,
    )
