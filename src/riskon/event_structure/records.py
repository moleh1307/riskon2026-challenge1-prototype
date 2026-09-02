"""Governed records produced from wide configuration matrices."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from riskon.event_structure.icons import KNOWN_EMOTICON_NAMES, KNOWN_IMAGE_ICON_NAMES
from riskon.event_structure.ir import Document, Table
from riskon.event_structure.matrix import MatrixVerdict, classify_document

ABSENT = "absent"
VALID_STATES = frozenset({ABSENT}) | KNOWN_EMOTICON_NAMES | KNOWN_IMAGE_ICON_NAMES


class RecordProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_id: str
    table_index: int
    row: int
    col: int
    heading: str = ""


class ConfigurationRecord(BaseModel):
    """One source cell with explicit row/column/state provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimensions: dict[str, str]
    column: str
    state: str
    state_meaning: str | None = None
    annotation: str = ""
    raw_icon: str | None = None
    icon_encoding: str | None = None
    headers: list[str] = Field(default_factory=list)
    provenance: RecordProvenance

    @field_validator("dimensions")
    @classmethod
    def _dimensions_must_be_named_and_filled(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("a record with no dimensions identifies nothing")
        for name, content in value.items():
            if not name.strip():
                raise ValueError("a dimension has no declared column label")
            if not content.strip():
                raise ValueError(f"dimension {name!r} is empty")
        return value

    @field_validator("column")
    @classmethod
    def _column_must_be_declared(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("the state column has no declared header")
        return value

    @field_validator("state")
    @classmethod
    def _state_must_be_known(cls, value: str) -> str:
        if value not in VALID_STATES:
            raise ValueError(f"unknown state {value!r}")
        return value

    def key(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self.dimensions.items())) + (
            ("__heading__", self.provenance.heading),
            ("__column__", self.column),
        )

    def evidence_text(self) -> str:
        """Create a deterministic, source-derived row for local evidence."""

        parts = [f"heading: {self.provenance.heading}" if self.provenance.heading else ""]
        parts.extend(f"{name}: {value}" for name, value in self.dimensions.items())
        parts.append(f"column: {self.column}")
        parts.append(f"state: {self.state}")
        if self.state_meaning is not None:
            parts.append(f"declared meaning: {self.state_meaning}")
        if self.raw_icon is not None:
            parts.append(f"raw icon: {self.raw_icon}")
        if self.icon_encoding is not None:
            parts.append(f"icon encoding: {self.icon_encoding}")
        if self.annotation:
            parts.append(f"annotation: {self.annotation}")
        return "; ".join(part for part in parts if part)

    def source_row(self) -> list[str]:
        return [*self.dimensions.values(), self.column, self.state, self.state_meaning or ""]


class Rejection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: str
    provenance: RecordProvenance
    detail: str = ""


class Dataset(BaseModel):
    """Accepted records plus explicit rejected/ambiguous source rows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    records: list[ConfigurationRecord] = Field(default_factory=list)
    rejections: list[Rejection] = Field(default_factory=list)

    def add(self, record: ConfigurationRecord) -> bool:
        for existing in self.records:
            if existing.key() != record.key() or existing.state == record.state:
                continue
            same_row = existing.provenance.row == record.provenance.row
            self.rejections.append(
                Rejection(
                    reason="ambiguous_column_labels" if same_row else "contradiction",
                    provenance=record.provenance,
                    detail=(
                        f"{record.column!r} already recorded as {existing.state!r} at row "
                        f"{existing.provenance.row} column {existing.provenance.col}, "
                        f"now {record.state!r}"
                    ),
                )
            )
            return False
        self.records.append(record)
        return True

    def states_for(self, column: str) -> set[str]:
        return {record.state for record in self.records if record.column == column}


def _state_of(cell_icons: list[str]) -> str:
    distinct = set(cell_icons)
    if not distinct:
        return ABSENT
    if len(distinct) > 1:
        raise ValueError(f"cell carries conflicting icons: {sorted(distinct)}")
    return distinct.pop()


def unpivot(document: Document, table: Table, verdict: MatrixVerdict) -> Dataset:
    dataset = Dataset()
    labels = table.header_labels()

    def label_of(col: int) -> str:
        return labels[col] if col < len(labels) else ""

    for row in range(table.header_rows, table.n_rows):
        dimensions = {
            label_of(col): table.grid[row][col].text
            for col in verdict.label_columns
            if table.grid[row][col].text
        }
        for col in verdict.state_columns:
            cell = table.grid[row][col]
            provenance = RecordProvenance(
                page_id=document.page_id,
                table_index=table.index,
                row=row,
                col=col,
                heading=table.heading,
            )
            try:
                state = _state_of([icon.name for icon in cell.icons])
            except ValueError as error:
                dataset.rejections.append(
                    Rejection(reason="conflicting_icons", provenance=provenance, detail=str(error))
                )
                continue
            icon = cell.icons[0] if len(cell.icons) == 1 else None
            try:
                record = ConfigurationRecord(
                    dimensions=dimensions,
                    column=label_of(col),
                    state=state,
                    state_meaning=(document.legend.meaning_of(state) if document.legend else None),
                    annotation=cell.text,
                    raw_icon=icon.raw if icon else None,
                    icon_encoding=icon.encoding if icon else None,
                    headers=labels,
                    provenance=provenance,
                )
            except ValidationError as error:
                dataset.rejections.append(
                    Rejection(
                        reason="schema",
                        provenance=provenance,
                        detail="; ".join(item["msg"] for item in error.errors()),
                    )
                )
                continue
            dataset.add(record)
    return dataset


def unpivot_document(document: Document) -> dict[int, tuple[MatrixVerdict, Dataset]]:
    """Return each matrix's verdict and governed record set separately."""

    result: dict[int, tuple[MatrixVerdict, Dataset]] = {}
    for verdict in classify_document(document):
        if verdict.is_matrix:
            result[verdict.table_index] = (
                verdict,
                unpivot(document, document.tables[verdict.table_index], verdict),
            )
    return result
