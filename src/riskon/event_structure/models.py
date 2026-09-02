"""Canonical-model sidecar for structural table records."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_structure.matrix import MatrixVerdict
from riskon.event_structure.records import ConfigurationRecord, Rejection


class StructuralTableData(BaseModel):
    """One normalised table and its governed matrix output."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    table_index: int
    heading: str = ""
    heading_level: int = 0
    n_rows: int
    n_cols: int
    header_rows: int
    headers: list[str] = Field(default_factory=list)
    quarantined: bool = False
    verdict: MatrixVerdict
    records: list[ConfigurationRecord] = Field(default_factory=list)
    rejections: list[Rejection] = Field(default_factory=list)
