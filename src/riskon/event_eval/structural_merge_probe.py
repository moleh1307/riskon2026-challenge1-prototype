"""No-API structural acceptance probe for the live RiskON corpus."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_runtime.factory import EventRetrievalComponents
from riskon.event_structure.adapter import StructuralMeasurements


class StructuralCaseResult(BaseModel):
    """Safe per-case structural result without source dumps or event content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    source_title: str | None = None
    page_id: str | None = None
    modality: str = "none"
    direct_structured_html: bool = False
    structural_evidence_rows: int = Field(ge=0)
    legend_mapped_rows: int = Field(ge=0)
    unresolved_icon_states: list[str] = Field(default_factory=list)
    raster_asset_units: int = Field(ge=0)
    source_package_gap_codes: list[str] = Field(default_factory=list)
    source_package_gap_count: int = Field(ge=0)


class StructuralMergeReport(BaseModel):
    """Machine-readable local acceptance result for Task 9."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    suite: str = "RISKON_CHALLENGE_1_STRUCTURAL_MERGE"
    measurements: StructuralMeasurements
    cases: list[StructuralCaseResult]


def build_structural_merge_report(
    components: EventRetrievalComponents,
    cases: list[Any],
) -> StructuralMergeReport:
    """Check E-01/E-05 structural rows and G-06/G-08 package gaps locally."""

    structural = components.corpus.structural
    if structural is None:
        raise ValueError("event corpus has no structural adapter")
    results: list[StructuralCaseResult] = []
    for case in cases:
        source_title = _matching_title(case.expected_source_title_contains, components)
        source_sections = [
            section for section in components.corpus.sections if section.title == source_title
        ]
        page_id = _page_id(source_sections[0].filename) if source_sections else None
        source_units = [
            unit
            for section in source_sections
            for unit in components.corpus.provenance.units_for_section(section.section_id)
        ]
        structural_units = [unit for unit in source_units if unit.structured]
        matching_units = [unit for unit in structural_units if _case_matches(case, unit.text)]
        mapped = [unit for unit in matching_units if "declared meaning:" in unit.text]
        states = sorted(
            {
                match.group(1).strip()
                for unit in matching_units
                if (match := re.search(r"(?:^|; )state: ([^;]+)", unit.text))
                and "declared meaning:" not in unit.text
                and match.group(1).strip() != "absent"
            }
        )
        gaps = structural.gaps_for_page(page_id) if page_id else ()
        gap_codes = sorted({gap.firewall_code for gap in gaps if gap.kind == "missing_attachment"})
        direct = bool(matching_units) and not any(unit.kind == "asset" for unit in source_units)
        results.append(
            StructuralCaseResult(
                case_id=case.id,
                source_title=source_title,
                page_id=page_id,
                modality="STRUCTURED_HTML" if direct else "none",
                direct_structured_html=direct,
                structural_evidence_rows=len(matching_units),
                legend_mapped_rows=len(mapped),
                unresolved_icon_states=states,
                raster_asset_units=sum(unit.kind == "asset" for unit in source_units),
                source_package_gap_codes=gap_codes,
                source_package_gap_count=sum(gap.kind == "missing_attachment" for gap in gaps),
            )
        )
    return StructuralMergeReport(measurements=structural.measurements, cases=results)


def _matching_title(expected: list[str], components: EventRetrievalComponents) -> str | None:
    exact = {
        section.title.casefold(): section.title
        for section in components.corpus.sections
        if any(section.title.casefold() == value.casefold() for value in expected)
    }
    if exact:
        return next(iter(exact.values()))
    for section in components.corpus.sections:
        if any(value.casefold() in section.title.casefold() for value in expected):
            return section.title
    return None


def _page_id(filename: str) -> str:
    return filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _case_matches(case: Any, text: str) -> bool:
    lowered = text.casefold()
    if case.id in {"E-01", "E-05"}:
        direct = (
            "heading: 1. advisory location ch (bc ch)" in lowered
            and "service model: advice premium" in lowered
        )
        if case.id == "E-05":
            return direct and (
                "declared meaning: only session" in lowered
                or "declared meaning: session and overnight" in lowered
            )
        return direct
    return True
