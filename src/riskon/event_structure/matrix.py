"""Conservative configuration-matrix detection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_structure.ir import Document, Table

MAX_LABEL_CHARS = 60
STATE_COLUMN_TEXT_TOLERANCE = 0.15
MIN_STATE_COLUMNS = 2
ColumnKind = Literal["label", "state", "mixed", "empty"]


class ColumnProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int
    kind: ColumnKind
    label: str = ""
    n_icons: int = 0
    n_text_only: int = 0
    n_empty: int = 0
    n_prose: int = 0


class MatrixVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_id: str
    table_index: int
    is_matrix: bool
    n_rows: int
    n_cols: int
    state_columns: list[int] = Field(default_factory=list)
    label_columns: list[int] = Field(default_factory=list)
    icon_count: int = 0
    icon_density: float = 0.0
    has_declared_header: bool = True
    reason: str = ""


def _profile_column(table: Table, col: int) -> ColumnProfile:
    body = [
        table.grid[row][col]
        for row in range(table.header_rows, table.n_rows)
        if not table.grid[row][col].spanned
    ]
    n_icons = sum(bool(cell.icons) for cell in body)
    n_text_only = sum(bool(cell.text and not cell.icons) for cell in body)
    n_prose = sum(len(cell.text) > MAX_LABEL_CHARS for cell in body)
    n_empty = sum(cell.is_empty for cell in body)
    if not body or n_empty == len(body):
        kind: ColumnKind = "empty"
    elif n_icons and n_text_only <= STATE_COLUMN_TEXT_TOLERANCE * len(body):
        kind = "state"
    elif n_icons:
        kind = "mixed"
    else:
        kind = "label"
    labels = table.header_labels()
    return ColumnProfile(
        index=col,
        kind=kind,
        label=labels[col] if col < len(labels) else "",
        n_icons=n_icons,
        n_text_only=n_text_only,
        n_empty=n_empty,
        n_prose=n_prose,
    )


def profile_table(table: Table) -> list[ColumnProfile]:
    return [_profile_column(table, col) for col in range(table.n_cols)]


def classify_table(table: Table, page_id: str) -> MatrixVerdict:
    profiles = profile_table(table)
    state_columns = [profile.index for profile in profiles if profile.kind == "state"]
    label_columns = [profile.index for profile in profiles if profile.kind == "label"]
    body_cells = [
        cell
        for row in range(table.header_rows, table.n_rows)
        for cell in table.grid[row]
        if not cell.spanned
    ]
    icon_count = sum(len(cell.icons) for cell in body_cells)
    density = sum(bool(cell.icons) for cell in body_cells) / len(body_cells) if body_cells else 0.0
    body_rows = table.n_rows - table.header_rows
    is_matrix = len(state_columns) >= MIN_STATE_COLUMNS and body_rows >= 2 and icon_count > 0
    if is_matrix:
        reason = (
            f"{len(state_columns)} state columns crossed with {body_rows} rows; "
            f"{icon_count} icons, {density:.0%} of body cells carry one"
        )
    elif icon_count and len(state_columns) < MIN_STATE_COLUMNS:
        reason = f"only {len(state_columns)} state column(s): icons are decoration"
    elif not icon_count:
        reason = "no icons: prose or a plain data table"
    else:
        reason = f"{body_rows} body row(s): too few to cross"
    return MatrixVerdict(
        page_id=page_id,
        table_index=table.index,
        is_matrix=is_matrix,
        n_rows=table.n_rows,
        n_cols=table.n_cols,
        state_columns=state_columns,
        label_columns=label_columns,
        icon_count=icon_count,
        icon_density=round(density, 3),
        has_declared_header=table.header_rows > 0,
        reason=reason,
    )


def classify_document(document: Document) -> list[MatrixVerdict]:
    return [classify_table(table, document.page_id) for table in document.tables]
