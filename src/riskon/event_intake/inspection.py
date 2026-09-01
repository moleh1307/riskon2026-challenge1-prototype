"""Corpus inspection and the public ER-A adapter facade."""

from __future__ import annotations

import hashlib
from pathlib import Path

from riskon.event_intake.html_inventory import HtmlInventoryScanner, HtmlScanResult
from riskon.event_intake.manifest import EventManifestEntry, ManifestLoader
from riskon.event_intake.models import (
    CorpusCompatibilityReport,
    CorpusIntakeReport,
    CorpusIntakeRequest,
    CorpusIssue,
    CorpusSmokeCase,
    CorpusStatus,
    DocumentDescriptor,
    HtmlInventory,
    IssueSeverity,
    PreparedCorpus,
)
from riskon.event_intake.path_safety import PathAssessment, assess_paths


class CorpusInspector:
    """Build one deterministic, safe inventory from a corpus request."""

    def __init__(self, aliases_path: Path | None = None) -> None:
        self.manifest_loader = ManifestLoader(aliases_path)
        self.html_scanner = HtmlInventoryScanner()

    def inspect(self, request: CorpusIntakeRequest) -> CorpusIntakeReport:
        """Inspect files, manifest rows, markup, links, and assets."""

        assessment = assess_paths(request)
        issues = list(assessment.issues)
        if not assessment.source_root.is_dir():
            return _report_from_empty(issues)

        manifest_result = self.manifest_loader.load(
            assessment.manifest_path,
            assessment.source_root,
            column_mapping=request.column_mapping,
        )
        issues.extend(manifest_result.issues)
        html_scans: dict[str, HtmlScanResult] = {}
        for path in assessment.html_files:
            relative = path.relative_to(assessment.source_root).as_posix()
            scan = self.html_scanner.scan(path, relative, assessment.source_root)
            html_scans[relative] = scan
            issues.extend(scan.issues)

        manifest_rows = manifest_result.manifest.rows if manifest_result.manifest else []
        manifest_paths = {row.filename for row in manifest_rows}
        orphan_paths = sorted(
            path.relative_to(assessment.source_root).as_posix()
            for path in assessment.html_files
            if path.relative_to(assessment.source_root).as_posix() not in manifest_paths
        )
        for orphan in orphan_paths:
            issues.append(
                CorpusIssue(
                    code="ORPHAN_HTML",
                    severity=IssueSeverity.WARNING,
                    relative_path=orphan,
                    detail="An HTML file is not declared by the manifest.",
                )
            )

        unsupported: list[str] = _unsupported_files(assessment)
        for unsupported_path in unsupported:
            issues.append(
                CorpusIssue(
                    code="UNSUPPORTED_FILE_IGNORED",
                    severity=IssueSeverity.WARNING,
                    relative_path=unsupported_path,
                    detail="The file type is inventoried but not ingested.",
                )
            )

        documents: list[DocumentDescriptor] = []
        selected_paths: set[str] = set()
        if manifest_result.manifest:
            for entry in manifest_result.entries:
                relative = entry.row.filename
                if relative in selected_paths:
                    continue
                selected_paths.add(relative)
                document_scan = html_scans.get(relative)
                if document_scan is None:
                    continue
                if document_scan.inventory.source_instruction_signal_count:
                    issues.append(
                        CorpusIssue(
                            code="SOURCE_INSTRUCTION_SIGNAL",
                            severity=IssueSeverity.WARNING,
                            relative_path=relative,
                            detail=(
                                "Instruction-like source text was recorded and will not execute."
                            ),
                        )
                    )
                documents.append(_document_descriptor(entry, document_scan.inventory))

        all_assets = [
            descriptor
            for relative in sorted(html_scans)
            for descriptor in html_scans[relative].assets.descriptors
        ]
        all_edges = [
            edge for relative in sorted(html_scans) for edge in html_scans[relative].links.edges
        ]
        missing_assets = sorted(
            {path for scan in html_scans.values() for path in scan.assets.missing_paths}
        )
        duplicate_filenames = _duplicate_values([row.filename for row in manifest_rows])
        duplicate_titles = _duplicate_values([row.title for row in manifest_rows])
        missing_manifest_files = sorted(
            {
                row.filename
                for row in manifest_rows
                if not _manifest_file_exists(row.filename, assessment.source_root)
            }
        )
        encoding_failures = sorted(
            relative
            for relative, scan in html_scans.items()
            if scan.inventory.encoding == "unknown"
        )
        parse_failures = sorted(
            relative for relative, scan in html_scans.items() if not scan.inventory.parse_ok
        )
        manifest_external_links = sum(
            1
            for row in manifest_rows
            if row.url and row.url.casefold().startswith(("http://", "https://", "//"))
        )
        total = _sum_sizes(assessment)
        fingerprint = _fingerprint(assessment)
        unique_issues = _unique_issues(issues)
        status = CorpusStatus.READY
        if any(item.severity is IssueSeverity.ERROR for item in unique_issues):
            status = CorpusStatus.BLOCKED
        elif unique_issues:
            status = CorpusStatus.READY_WITH_WARNINGS
        return CorpusIntakeReport(
            status=status,
            manifest=manifest_result.manifest,
            documents=documents,
            assets=all_assets,
            local_link_edges=all_edges,
            html_file_count=len(assessment.html_files),
            manifest_row_count=(
                manifest_result.manifest.row_count if manifest_result.manifest else 0
            ),
            matched_html_count=len({entry.row.filename for entry in manifest_result.entries}),
            manifest_rows_without_files=missing_manifest_files,
            orphan_html_files=orphan_paths,
            duplicate_filenames=duplicate_filenames,
            duplicate_titles=duplicate_titles,
            encoding_failures=encoding_failures,
            html_parse_failures=parse_failures,
            heading_count=sum(scan.inventory.heading_count for scan in html_scans.values()),
            section_count=sum(scan.inventory.section_count for scan in html_scans.values()),
            table_count=sum(scan.inventory.table_count for scan in html_scans.values()),
            table_row_count=sum(scan.inventory.table_row_count for scan in html_scans.values()),
            image_svg_reference_count=sum(
                scan.inventory.image_svg_reference_count for scan in html_scans.values()
            ),
            missing_local_assets=missing_assets,
            local_links=sum(scan.links.local_count for scan in html_scans.values()),
            broken_local_links=sum(scan.links.broken_count for scan in html_scans.values()),
            external_links=sum(scan.inventory.external_link_count for scan in html_scans.values())
            + manifest_external_links,
            script_count=sum(scan.inventory.script_count for scan in html_scans.values()),
            style_count=sum(scan.inventory.style_count for scan in html_scans.values()),
            form_count=sum(scan.inventory.form_count for scan in html_scans.values()),
            source_instruction_signal_count=sum(
                scan.inventory.source_instruction_signal_count for scan in html_scans.values()
            ),
            unsupported_file_types=unsupported,
            total_corpus_size=total,
            corpus_fingerprint=fingerprint,
            issues=unique_issues,
            external_fetches=0,
            network_enabled=False,
        )


class EventCorpusAdapter:
    """Public ER-A interface: inspect, prepare, and compatibility smoke-test."""

    def __init__(
        self,
        aliases_path: Path | None = None,
        *,
        project_root: Path | None = None,
        pipeline_config_path: Path | None = None,
    ) -> None:
        root = project_root.resolve() if project_root else Path(__file__).resolve().parents[2]
        self.project_root = root
        self.pipeline_config_path = pipeline_config_path or root / "config" / "milestone2.toml"
        self.inspector = CorpusInspector(aliases_path)

    @classmethod
    def from_project_root(cls, project_root: Path) -> EventCorpusAdapter:
        """Construct an adapter from the repository's event-readiness config."""

        from riskon.config import load_event_readiness_config

        config = load_event_readiness_config(project_root / "config" / "event_readiness.toml")
        return cls(
            config.column_aliases,
            project_root=config.project_root,
            pipeline_config_path=config.pipeline_config,
        )

    def inspect(self, request: CorpusIntakeRequest) -> CorpusIntakeReport:
        """Inspect a source root without writing to it."""

        return self.inspector.inspect(request)

    def prepare(self, request: CorpusIntakeRequest) -> PreparedCorpus | None:
        """Return a descriptor-only prepared corpus, or ``None`` when blocked."""

        from riskon.event_intake.preparation import prepare_corpus

        report = self.inspect(request)
        return prepare_corpus(report, request)

    def smoke_test(
        self,
        prepared_corpus: PreparedCorpus | None,
        smoke_cases: tuple[CorpusSmokeCase, ...],
    ) -> CorpusCompatibilityReport:
        """Run the existing local ingestion/retrieval/verification path."""

        from riskon.event_intake.compatibility import CompatibilityRunner

        return CompatibilityRunner(
            self.project_root,
            self.pipeline_config_path,
        ).run(prepared_corpus, smoke_cases)


def _document_descriptor(entry: EventManifestEntry, inventory: HtmlInventory) -> DocumentDescriptor:
    """Convert an HTML inventory into the frozen descriptor contract."""

    descriptor_digest = hashlib.sha256(
        (entry.row.filename + inventory.sha256).encode("utf-8")
    ).hexdigest()
    return DocumentDescriptor(
        document_id=descriptor_digest,
        relative_path=entry.row.filename,
        title=entry.row.title,
        source_url=entry.source_url,
        sha256=inventory.sha256,
        encoding=inventory.encoding,
        section_count=inventory.section_count,
        heading_count=inventory.heading_count,
        table_count=inventory.table_count,
        table_row_count=inventory.table_row_count,
        image_svg_reference_count=inventory.image_svg_reference_count,
        asset_refs=inventory.asset_refs,
        local_link_refs=inventory.local_link_refs,
        broken_local_link_count=inventory.broken_local_link_count,
        script_count=inventory.script_count,
        style_count=inventory.style_count,
        form_count=inventory.form_count,
        source_instruction_signal_count=inventory.source_instruction_signal_count,
        size_bytes=inventory.size_bytes,
    )


def _report_from_empty(issues: list[CorpusIssue]) -> CorpusIntakeReport:
    """Create a complete zero-count report when the root cannot be inspected."""

    return CorpusIntakeReport(
        status=CorpusStatus.BLOCKED,
        manifest=None,
        documents=[],
        assets=[],
        local_link_edges=[],
        html_file_count=0,
        manifest_row_count=0,
        matched_html_count=0,
        manifest_rows_without_files=[],
        orphan_html_files=[],
        duplicate_filenames=[],
        duplicate_titles=[],
        encoding_failures=[],
        html_parse_failures=[],
        heading_count=0,
        section_count=0,
        table_count=0,
        table_row_count=0,
        image_svg_reference_count=0,
        missing_local_assets=[],
        local_links=0,
        broken_local_links=0,
        external_links=0,
        script_count=0,
        style_count=0,
        form_count=0,
        source_instruction_signal_count=0,
        unsupported_file_types=[],
        total_corpus_size=0,
        corpus_fingerprint="",
        issues=_unique_issues(issues),
    )


def _manifest_file_exists(relative: str, root: Path) -> bool:
    """Return whether a manifest HTML row resolves inside the source root."""

    candidate = (root / relative).resolve(strict=False)
    return candidate.is_relative_to(root.resolve(strict=False)) and candidate.is_file()


def _unsupported_files(assessment: PathAssessment) -> list[str]:
    """List non-event file types without inspecting their contents."""

    allowed = {
        ".html",
        ".htm",
        ".xlsx",
        ".json",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".css",
        ".txt",
        ".csv",
    }
    result = {
        path.relative_to(assessment.source_root).as_posix()
        for path in assessment.files
        if path.suffix.casefold() not in allowed
    }
    return sorted(result)


def _sum_sizes(assessment: PathAssessment) -> int:
    """Sum local regular-file sizes without following unsafe symlinks."""

    total = 0
    root = assessment.source_root.resolve(strict=False)
    for path in assessment.files:
        if path.is_symlink():
            target = path.resolve(strict=False)
            if not target.is_relative_to(root):
                continue
        if path.is_file():
            total += path.stat().st_size
    return total


def _fingerprint(assessment: PathAssessment) -> str:
    """Hash sorted relative paths and file hashes, never absolute paths."""

    digest = hashlib.sha256()
    root = assessment.source_root.resolve(strict=False)
    rows: list[str] = []
    for path in assessment.files:
        if path.is_symlink() and not path.resolve(strict=False).is_relative_to(root):
            continue
        if not path.is_file():
            continue
        rows.append(
            f"{path.relative_to(root).as_posix()}:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        )
    for row in sorted(rows):
        digest.update(row.encode("utf-8"))
    return digest.hexdigest()


def _duplicate_values(values: list[str]) -> list[str]:
    """Return duplicate values in first-seen order, case-insensitively."""

    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(key)
    return duplicates


def _unique_issues(issues: list[CorpusIssue]) -> list[CorpusIssue]:
    """Deduplicate issue rows across all inspection stages."""

    seen: set[tuple[str, IssueSeverity, str | None, str | None]] = set()
    result: list[CorpusIssue] = []
    for issue in issues:
        key = (issue.code, issue.severity, issue.relative_path, issue.detail)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result
