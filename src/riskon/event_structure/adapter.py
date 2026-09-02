"""Adapter from the structural substrate into the canonical event corpus."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_structure.acronyms import Glossary, build_glossary
from riskon.event_structure.ir import Document
from riskon.event_structure.matrix import classify_document
from riskon.event_structure.metadata import MetadataProposal, propose_metadata
from riskon.event_structure.models import StructuralTableData
from riskon.event_structure.parser import parse_page
from riskon.event_structure.records import unpivot_document
from riskon.event_structure.references import (
    Gap,
    ReferenceGraph,
    build_reference_graph,
    title_index_from_pairs,
)
from riskon.models import ManifestEntry, Section


class StructuralMeasurements(BaseModel):
    """Bounded corpus measurements; this is diagnostic metadata, not event evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pages: int = Field(ge=0)
    tables: int = Field(ge=0)
    status_icons: int = Field(ge=0)
    matrices: int = Field(ge=0)
    missing_attachments: int = Field(ge=0)
    dynamic_content_gaps: int = Field(ge=0)
    resolved_internal_links: int = Field(ge=0)
    unresolved_internal_links: int = Field(ge=0)
    merged_cells: int = Field(ge=0)
    quarantined_pages: int = Field(ge=0)
    verified_acronyms: int = Field(ge=0)
    acronym_collisions: int = Field(ge=0)


@dataclass(frozen=True)
class StructuralEventCorpus:
    """Read-only structural state attached to the one canonical LocalCorpus."""

    documents: tuple[Document, ...]
    reference_graph: ReferenceGraph
    glossary: Glossary
    metadata_proposals: tuple[MetadataProposal, ...]
    tables_by_page: tuple[tuple[str, tuple[StructuralTableData, ...]], ...]
    measurements: StructuralMeasurements

    def tables_for_page(self, page_id: str) -> tuple[StructuralTableData, ...]:
        return next(
            (tables for candidate, tables in self.tables_by_page if candidate == page_id),
            (),
        )

    def gaps_for_page(self, page_id: str) -> tuple[Gap, ...]:
        return self.reference_graph.gaps_for_page(page_id)


def build_structural_event_corpus(
    entries: Iterable[ManifestEntry],
    *,
    available_attachments: set[str] | None = None,
) -> StructuralEventCorpus:
    """Parse manifest-declared HTML and build structure, gaps, glossary, and records."""

    entries_list = list(entries)
    documents = tuple(parse_page(Path(entry.source_path)) for entry in entries_list)
    title_index = title_index_from_pairs([(entry.filename, entry.title) for entry in entries_list])
    graph = build_reference_graph(
        list(documents),
        title_index=title_index,
        available_attachments=available_attachments,
    )
    glossary = build_glossary(list(documents))
    metadata = tuple(propose_metadata(document) for document in documents)
    tables_by_page: list[tuple[str, tuple[StructuralTableData, ...]]] = []
    for document in documents:
        parsed_tables: list[StructuralTableData] = []
        datasets = unpivot_document(document)
        verdicts = {verdict.table_index: verdict for verdict in classify_document(document)}
        for table in document.tables:
            verdict = verdicts[table.index]
            dataset = datasets.get(table.index, (verdict, None))[1]
            parsed_tables.append(
                StructuralTableData(
                    table_index=table.index,
                    heading=table.heading,
                    heading_level=table.heading_level,
                    n_rows=table.n_rows,
                    n_cols=table.n_cols,
                    header_rows=table.header_rows,
                    headers=table.header_labels(),
                    quarantined=document.quarantined,
                    verdict=verdict,
                    records=list(dataset.records) if dataset is not None else [],
                    rejections=list(dataset.rejections) if dataset is not None else [],
                )
            )
        tables_by_page.append((document.page_id, tuple(parsed_tables)))
    measurements = _measurements(documents, graph, glossary)
    return StructuralEventCorpus(
        documents=documents,
        reference_graph=graph,
        glossary=glossary,
        metadata_proposals=metadata,
        tables_by_page=tuple(tables_by_page),
        measurements=measurements,
    )


def attach_structural_tables(
    sections: list[Section],
    structural: StructuralEventCorpus,
) -> list[Section]:
    """Add structural tables to existing sections without replacing canonical ingestion."""

    tables_by_page = dict(structural.tables_by_page)
    result: list[Section] = []
    for section in sections:
        candidates = tables_by_page.get(Path(section.filename).stem, ())
        heading = section.heading_path[-1] if section.heading_path else ""
        attached = tuple(table for table in candidates if table.heading == heading)
        if not attached and not heading:
            attached = tuple(table for table in candidates if not table.heading)
        if attached:
            result.append(section.model_copy(update={"structured_tables": list(attached)}))
        else:
            result.append(section)
    return result


def _measurements(
    documents: tuple[Document, ...],
    graph: ReferenceGraph,
    glossary: Glossary,
) -> StructuralMeasurements:
    matrices = sum(
        verdict.is_matrix for document in documents for verdict in classify_document(document)
    )
    merged_cells = sum(
        sum(cell.spanned for row in table.grid for cell in row)
        for document in documents
        for table in document.tables
    )
    gap_counts = graph.gaps_by_kind()
    return StructuralMeasurements(
        pages=len(documents),
        tables=sum(len(document.tables) for document in documents),
        status_icons=sum(document.icon_count for document in documents),
        matrices=matrices,
        missing_attachments=gap_counts.get("missing_attachment", 0),
        dynamic_content_gaps=gap_counts.get("dynamic_content", 0),
        resolved_internal_links=len(graph.edges),
        unresolved_internal_links=gap_counts.get("unresolved_link", 0),
        merged_cells=merged_cells,
        quarantined_pages=sum(document.quarantined for document in documents),
        verified_acronyms=len({entry.acronym for entry in glossary.entries if entry.verified}),
        acronym_collisions=len(glossary.collisions()),
    )
