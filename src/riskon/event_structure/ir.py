"""Small intermediate representation for Confluence storage-format pages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_structure.icons import Icon
from riskon.event_structure.legend import Legend

Severity = Literal["quarantine", "note"]
LinkKind = Literal["internal_page", "wiki_url", "external"]
AttachmentVia = Literal["view-file", "image", "link"]


class ParseIssue(BaseModel):
    """A parse observation or a source ambiguity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    severity: Severity
    detail: str
    table_index: int | None = None
    row: int | None = None


class Cell(BaseModel):
    """One cell in a dense, rowspan/colspan-normalised table grid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    row: int
    col: int
    text: str = ""
    icons: list[Icon] = Field(default_factory=list)
    is_header: bool = False
    spanned: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.text and not self.icons


class Table(BaseModel):
    """A table whose geometry has been made explicit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    index: int
    n_rows: int
    n_cols: int
    header_rows: int = 0
    heading: str = ""
    heading_level: int = 0
    grid: list[list[Cell]] = Field(default_factory=list)

    def header_labels(self) -> list[str]:
        """Join multi-row headers while collapsing repeated rowspan text."""

        if not self.header_rows:
            return []
        labels: list[str] = []
        for col in range(self.n_cols):
            parts: list[str] = []
            for row in range(self.header_rows):
                text = self.grid[row][col].text
                if text and (not parts or parts[-1] != text):
                    parts.append(text)
            labels.append(" ".join(parts))
        return labels


class Section(BaseModel):
    """Flat prose section retained for acronym and page-text extraction."""

    model_config = ConfigDict(extra="forbid")

    heading: str = ""
    level: int = 0
    text: str = ""


class LinkRef(BaseModel):
    """A link that may be resolved using the manifest title index."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: LinkKind
    target: str
    anchor: str | None = None


class AttachmentRef(BaseModel):
    """A binary dependency referenced by a page."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str
    via: AttachmentVia


class MacroRef(BaseModel):
    """A Confluence macro and whether its body is render-time dynamic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    dynamic: bool


DYNAMIC_MACROS = frozenset({"children", "pagetree", "contentbylabel", "toc", "detailssummary"})


class Document(BaseModel):
    """One source page parsed without interpreting business meaning."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_id: str
    source_path: str
    text: str = ""
    legend: Legend | None = None
    sections: list[Section] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    links: list[LinkRef] = Field(default_factory=list)
    attachments: list[AttachmentRef] = Field(default_factory=list)
    macros: list[MacroRef] = Field(default_factory=list)
    issues: list[ParseIssue] = Field(default_factory=list)

    @property
    def quarantined(self) -> bool:
        return any(issue.severity == "quarantine" for issue in self.issues)

    @property
    def icon_count(self) -> int:
        """Count source cells carrying icons, excluding merged copies."""

        return sum(
            len(cell.icons)
            for table in self.tables
            for row in table.grid
            for cell in row
            if not cell.spanned
        )
