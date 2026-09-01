"""Read-only event corpus validation and rich HTML section loading."""

from __future__ import annotations

from urllib.parse import quote

from riskon.event_intake import (
    CorpusIntakeReport,
    CorpusIntakeRequest,
    CorpusStatus,
    EventCorpusAdapter,
)
from riskon.event_runtime.config import EventRuntimeConfig
from riskon.ingestion import KnowledgeIngestor
from riskon.models import ManifestEntry, Section
from riskon.orchestra.source_safety import LocalCorpus
from riskon.provenance import ProvenanceIndex


class EventRuntimeCorpusError(ValueError):
    """Raised when a real event corpus cannot enter the runtime."""


def ingest_event_sections(entries: list[ManifestEntry]) -> list[Section]:
    """Ingest event HTML while making the manifest title canonical."""

    ingested = KnowledgeIngestor().ingest(entries)
    titles = {entry.filename: entry.title for entry in entries}
    return [
        section.model_copy(update={"title": titles.get(section.filename, section.title)})
        for section in ingested
    ]


def load_event_corpus(
    config: EventRuntimeConfig,
    adapter: EventCorpusAdapter,
) -> tuple[LocalCorpus, CorpusIntakeReport]:
    """Validate the event package, then build local event provenance in memory."""

    request = CorpusIntakeRequest(
        source_root=config.source_root,
        manifest_path=config.manifest,
        column_mapping=config.column_mapping,
        output_root=config.generated_root / "intake",
    )
    report = adapter.inspect(request)
    if report.status is CorpusStatus.BLOCKED:
        codes = ", ".join(sorted({issue.code for issue in report.blocking_issues}))
        raise EventRuntimeCorpusError(f"Event corpus intake BLOCKED: {codes}")
    if report.manifest is None:
        raise EventRuntimeCorpusError("Event corpus intake produced no manifest descriptor")

    entries = [
        ManifestEntry(
            filename=row.filename,
            title=row.title,
            url=f"{config.url_prefix}{quote(row.filename, safe='/')}",
            source_path=str((config.source_root / row.filename).resolve()),
        )
        for row in report.manifest.rows
    ]
    sections = ingest_event_sections(entries)
    if not sections:
        raise EventRuntimeCorpusError("Event corpus contains no ingestible HTML sections")
    provenance = ProvenanceIndex(
        sections,
        knowledge_root=config.source_root,
        ref_style="m2",
    )
    return (
        LocalCorpus(
            sections=tuple(sections),
            provenance=provenance,
            knowledge_root=config.source_root.resolve(),
        ),
        report,
    )
