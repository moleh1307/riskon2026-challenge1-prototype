"""Public data contracts for the ER-A event corpus adapter."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from riskon.models import Decision


class CorpusStatus(StrEnum):
    """Inspection status exposed by the adapter."""

    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    BLOCKED = "BLOCKED"


class IssueSeverity(StrEnum):
    """Whether an intake issue blocks preparation."""

    WARNING = "WARNING"
    ERROR = "ERROR"


class CorpusIssue(BaseModel):
    """Safe, structured issue detail without source dumps or absolute paths."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    severity: IssueSeverity
    relative_path: str | None = None
    detail: str | None = None


class ManifestRow(BaseModel):
    """One safe manifest row retained for deterministic preparation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    row_number: int = Field(ge=2)
    filename: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str | None = None


class ManifestDescriptor(BaseModel):
    """Manifest metadata and normalized rows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str
    columns: list[str]
    column_mapping: dict[str, str]
    row_count: int = Field(ge=0)
    has_url: bool
    rows: list[ManifestRow]


class HtmlInventory(BaseModel):
    """Structure-only inventory for one HTML document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    encoding: str
    parse_ok: bool
    heading_count: int = Field(ge=0)
    section_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    table_row_count: int = Field(ge=0)
    image_svg_reference_count: int = Field(ge=0)
    local_link_count: int = Field(ge=0)
    broken_local_link_count: int = Field(ge=0)
    external_link_count: int = Field(ge=0)
    script_count: int = Field(ge=0)
    style_count: int = Field(ge=0)
    form_count: int = Field(ge=0)
    comment_count: int = Field(ge=0)
    hidden_content_count: int = Field(ge=0)
    source_instruction_signal_count: int = Field(ge=0)
    asset_refs: list[str]
    local_link_refs: list[str]


class DocumentDescriptor(BaseModel):
    """Prepared descriptor for one manifest-declared HTML document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    relative_path: str
    title: str
    source_url: str
    sha256: str
    encoding: str
    section_count: int = Field(ge=0)
    heading_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    table_row_count: int = Field(ge=0)
    image_svg_reference_count: int = Field(ge=0)
    asset_refs: list[str]
    local_link_refs: list[str]
    broken_local_link_count: int = Field(ge=0)
    script_count: int = Field(ge=0)
    style_count: int = Field(ge=0)
    form_count: int = Field(ge=0)
    source_instruction_signal_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)


class AssetDescriptor(BaseModel):
    """Safe descriptor for a local, inline, or external asset reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_relative_path: str
    relative_path: str | None
    kind: str
    reference_count: int = Field(ge=1)
    exists: bool
    size_bytes: int | None = Field(default=None, ge=0)
    sha256: str | None = None


class LocalLinkEdge(BaseModel):
    """One safe local-link relationship or non-fetching URL observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_relative_path: str
    href: str
    target_relative_path: str | None
    anchor: str | None
    kind: str
    resolved: bool
    broken: bool


class CorpusIntakeRequest(BaseModel):
    """Input contract for a read-only event corpus inspection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_root: Path
    manifest_path: Path
    column_mapping: dict[str, str] = Field(default_factory=dict)
    output_root: Path


class CorpusIntakeReport(BaseModel):
    """Complete safe inventory and issue report for one corpus."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    status: CorpusStatus
    manifest: ManifestDescriptor | None
    documents: list[DocumentDescriptor]
    assets: list[AssetDescriptor]
    local_link_edges: list[LocalLinkEdge]
    html_file_count: int = Field(ge=0)
    manifest_row_count: int = Field(ge=0)
    matched_html_count: int = Field(ge=0)
    manifest_rows_without_files: list[str]
    orphan_html_files: list[str]
    duplicate_filenames: list[str]
    duplicate_titles: list[str]
    encoding_failures: list[str]
    html_parse_failures: list[str]
    heading_count: int = Field(ge=0)
    section_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    table_row_count: int = Field(ge=0)
    image_svg_reference_count: int = Field(ge=0)
    missing_local_assets: list[str]
    local_links: int = Field(ge=0)
    broken_local_links: int = Field(ge=0)
    external_links: int = Field(ge=0)
    script_count: int = Field(ge=0)
    style_count: int = Field(ge=0)
    form_count: int = Field(ge=0)
    source_instruction_signal_count: int = Field(ge=0)
    unsupported_file_types: list[str]
    total_corpus_size: int = Field(ge=0)
    corpus_fingerprint: str
    issues: list[CorpusIssue]
    external_fetches: int = Field(default=0, ge=0)
    network_enabled: bool = False

    @property
    def blocking_issues(self) -> tuple[CorpusIssue, ...]:
        """Return issues that prevent preparation."""

        return tuple(item for item in self.issues if item.severity is IssueSeverity.ERROR)

    @property
    def warnings(self) -> tuple[CorpusIssue, ...]:
        """Return non-blocking issues."""

        return tuple(item for item in self.issues if item.severity is IssueSeverity.WARNING)

    @property
    def blocking_issue_count(self) -> int:
        """Return the number of blocking issues."""

        return len(self.blocking_issues)

    @property
    def warning_count(self) -> int:
        """Return the number of warnings."""

        return len(self.warnings)


class PreparedCorpus(BaseModel):
    """Read-only descriptor graph; no event source content is copied."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_root: Path
    manifest_descriptor: ManifestDescriptor
    documents: list[DocumentDescriptor]
    assets: list[AssetDescriptor]
    local_link_edges: list[LocalLinkEdge]
    corpus_fingerprint: str
    warnings: list[str]


class CorpusSmokeCase(BaseModel):
    """One deterministic compatibility smoke case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    input_context: dict[str, str] = Field(default_factory=dict)
    expected_decision: Decision
    expected_answer_contains: list[str] = Field(default_factory=list)
    expected_table_rows: list[list[str]] = Field(default_factory=list)
    require_local_evidence: bool = False


class CompatibilityCaseResult(BaseModel):
    """Safe result for one smoke case; answer text is intentionally omitted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    matched: bool
    expected_decision: Decision
    actual_decision: Decision
    evidence_count: int = Field(ge=0)
    evidence_refs: list[str]
    answer_contains_matched: bool
    table_rows_matched: bool
    failures: list[str]


class CorpusCompatibilityReport(BaseModel):
    """Compatibility outcome and no-mutation/no-egress invariants."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    passed: bool
    case_results: list[CompatibilityCaseResult]
    expected_case_count: int = Field(ge=0)
    matched_case_count: int = Field(ge=0)
    source_mutations: int = Field(ge=0)
    source_file_hashes_unchanged: bool
    source_directory_entries_unchanged: bool
    external_fetches: int = Field(ge=0)
    source_instruction_executions: int = Field(ge=0)
    subprocess_calls: int = Field(ge=0)
    network_disabled: bool
    failure_codes: list[str]
