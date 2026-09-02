"""Deterministic structural evidence admission for the event runtime.

The structural substrate is deliberately kept separate from answer generation.  This
module selects and filters validated matrix records, checks their local provenance, and
returns typed source-package gaps.  It never interprets an icon without a page-declared
legend and never treats inferred metadata as scope evidence.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field

from riskon.event_structure.acronyms import normalise_expansion
from riskon.event_structure.models import StructuralTableData
from riskon.event_structure.records import ConfigurationRecord
from riskon.event_structure.references import Gap
from riskon.hybrid_retrieval import HybridRetrievalResult
from riskon.models import QueryInput, QueryPlan
from riskon.orchestra.source_safety import LocalCorpus
from riskon.provenance import ProvenanceIndex


class StructuralScopeState(StrEnum):
    """Scope state admitted by the original source only."""

    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class StructuralStatus(StrEnum):
    """Outcome of the deterministic structural path."""

    NOT_APPLICABLE = "NOT_APPLICABLE"
    SUFFICIENT = "SUFFICIENT"
    NO_DIRECT_SUPPORT = "NO_DIRECT_SUPPORT"
    WRONG_SCOPE = "WRONG_SCOPE"
    AMBIGUOUS_ACRONYM = "AMBIGUOUS_ACRONYM"
    PROVENANCE_INVALID = "PROVENANCE_INVALID"
    SOURCE_PACKAGE_ASSET_UNAVAILABLE = "SOURCE_PACKAGE_ASSET_UNAVAILABLE"


class StructuralEvidenceClaim(BaseModel):
    """One direct structural lookup with its exact local source address."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(min_length=1, max_length=200)
    claim_text: str = Field(min_length=1, max_length=2000)
    evidence_ref: str = Field(min_length=1, max_length=500)
    supporting_span: str = Field(min_length=1, max_length=2000)
    state: str = Field(min_length=1, max_length=80)
    state_meaning: str | None = Field(default=None, max_length=160)
    table_heading: str = Field(default="", max_length=300)
    column: str = Field(min_length=1, max_length=300)
    dimensions: dict[str, str] = Field(default_factory=dict)
    applicable_scope: dict[str, str] = Field(default_factory=dict)
    critical_control: bool = False
    unresolved_state: bool = False


class SourceGapResult(BaseModel):
    """Typed gap result passed to an existing Firewall decision boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    required: bool
    gaps: list[Gap] = Field(default_factory=list, max_length=64)
    firewall_code: str | None = None
    distinction: str = Field(min_length=1, max_length=240)


class StructuralMatrixResult(BaseModel):
    """Bounded, source-safe result of one structural matrix evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: StructuralStatus
    claims: list[StructuralEvidenceClaim] = Field(default_factory=list, max_length=64)
    evidence_refs: list[str] = Field(default_factory=list, max_length=64)
    source_refs: list[str] = Field(default_factory=list, max_length=32)
    primary_source: str | None = None
    table_heading: str | None = None
    scope_state: StructuralScopeState = StructuralScopeState.UNKNOWN
    inspected_row_count: int = Field(default=0, ge=0)
    inspected_column_count: int = Field(default=0, ge=0)
    inspected_record_count: int = Field(default=0, ge=0)
    matched_record_count: int = Field(default=0, ge=0)
    table_complete: bool = False
    provenance_valid: bool = False
    unresolved_states: list[str] = Field(default_factory=list, max_length=32)
    unresolved_state_refs: list[str] = Field(default_factory=list, max_length=64)
    source_package_gap_codes: list[str] = Field(default_factory=list, max_length=16)
    source_package_gap_targets: list[str] = Field(default_factory=list, max_length=64)
    acronym_expansions: dict[str, str] = Field(default_factory=dict)
    acronym_ambiguities: dict[str, list[str]] = Field(default_factory=dict)
    clarification_question: str | None = Field(default=None, max_length=500)
    reason: str = Field(default="", max_length=600)

    @property
    def handled(self) -> bool:
        """Return whether the structural path has a terminal deterministic outcome."""

        return self.status not in {
            StructuralStatus.NOT_APPLICABLE,
            StructuralStatus.NO_DIRECT_SUPPORT,
        }


class SourceGapWorker:
    """Read the Task 9 gap register without interpreting missing assets."""

    def __init__(self, corpus: LocalCorpus) -> None:
        self.corpus = corpus

    def evaluate(
        self,
        source_refs: Sequence[str],
        *,
        required: bool = True,
        relevant_evidence_refs: Sequence[str] = (),
    ) -> SourceGapResult:
        """Return only missing assets materially attached to selected evidence sections.

        The gap register is page-level, while a Confluence export can contain several
        unrelated sections and images on that page.  Callers that already selected evidence
        units must therefore provide their refs so an asset is matched to the section that
        actually declares it.  The legacy page-level behavior is retained for callers with no
        evidence context (for example, a visual-only request with an otherwise empty page).
        """

        structural = self.corpus.structural
        if structural is None or not required:
            return SourceGapResult(
                required=required,
                distinction=(
                    "The source package was not inspected for an asset gap; this is not an "
                    "interpretation of an unavailable asset."
                ),
            )
        source_set = {ref.split("#", 1)[0] for ref in source_refs if ref}
        page_ids = {
            _page_id(section.filename)
            for section in self.corpus.sections
            if section.source_ref in source_set
        }
        gaps = [
            gap
            for page_id in sorted(page_ids)
            for gap in structural.gaps_for_page(page_id)
            if gap.kind == "missing_attachment"
        ]
        if relevant_evidence_refs:
            section_ids = {
                unit.section_id
                for ref in relevant_evidence_refs
                if (unit := self.corpus.provenance.resolve(ref)) is not None
                and unit.section_id is not None
            }
            relevant_targets = {
                target
                for section in self.corpus.sections
                if section.section_id in section_ids
                for target in _section_attachment_targets(self.corpus, section)
            }
            gaps = [gap for gap in gaps if Path(gap.target).name in relevant_targets]
        gaps = list(dict.fromkeys(gaps))
        return SourceGapResult(
            required=required,
            gaps=gaps,
            firewall_code=("SOURCE_PACKAGE_ASSET_UNAVAILABLE" if gaps else None),
            distinction=(
                "The required source asset was not delivered in the event package; this is "
                "different from an available asset that the AI cannot interpret."
            ),
        )


def _section_attachment_targets(corpus: LocalCorpus, section: Any) -> set[str]:
    """Read attachment declarations from one original heading-scoped HTML section."""

    root = corpus.knowledge_root
    if root is None:
        return set()
    source_path = (root / section.filename).resolve()
    if not source_path.is_file() or not source_path.is_relative_to(root.resolve()):
        return set()
    match = re.search(r"::section-(\d+)$", section.section_id)
    if match is None:
        return set()
    try:
        raw = source_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    soup = BeautifulSoup(raw, "html.parser")
    headings = soup.find_all(re.compile(r"^h[1-6]$", re.IGNORECASE))
    heading_index = int(match.group(1)) - 1
    if not 0 <= heading_index < len(headings):
        return set()
    heading = headings[heading_index]
    heading_name = str(heading.name)
    heading_level = int(heading_name[1:])
    targets: set[str] = set()
    for sibling in heading.next_siblings:
        name = getattr(sibling, "name", None)
        if isinstance(name, str) and re.fullmatch(r"h[1-6]", name, re.IGNORECASE):
            if int(name[1:]) <= heading_level:
                break
        tags = [sibling, *sibling.find_all(True)] if hasattr(sibling, "find_all") else []
        for tag in tags:
            attributes = getattr(tag, "attrs", {})
            if not isinstance(attributes, dict):
                continue
            for key in ("ri:filename", "filename", "src"):
                value = attributes.get(key)
                if isinstance(value, str) and value.strip():
                    targets.add(Path(value.strip()).name)
    return targets


class StructuralMatrixWorker:
    """Select, filter, and validate source-declared matrix records deterministically."""

    _matrix_intents = frozenset({"ALERT_RESOLUTION", "CONFIGURATION_LOOKUP"})
    _matrix_terms = frozenset(
        {
            "alert",
            "alerts",
            "configuration",
            "configured",
            "triggered",
            "matrix",
            "status",
            "state",
            "apply",
            "applies",
            "activated",
        }
    )
    _session_meanings = frozenset({"only session", "session and overnight"})

    def __init__(self, corpus: LocalCorpus) -> None:
        self.corpus = corpus
        self.gap_worker = SourceGapWorker(corpus)

    def evaluate(
        self,
        request: QueryInput,
        plan: QueryPlan,
        retrieval: HybridRetrievalResult | Any,
        *,
        provenance: ProvenanceIndex | None = None,
    ) -> StructuralMatrixResult:
        """Evaluate a matrix question over validated structural records only."""

        structural = self.corpus.structural
        if structural is None:
            return StructuralMatrixResult(
                status=StructuralStatus.NOT_APPLICABLE,
                reason="No structural event corpus is attached.",
            )

        expansions, ambiguities = self._acronym_state(request)
        if ambiguities:
            return StructuralMatrixResult(
                status=StructuralStatus.AMBIGUOUS_ACRONYM,
                acronym_expansions=expansions,
                acronym_ambiguities=ambiguities,
                clarification_question="Please clarify the acronym before I answer.",
                reason="The corpus contains multiple verified expansions for a queried acronym.",
            )

        if not self._is_matrix_question(request, plan):
            return StructuralMatrixResult(
                status=StructuralStatus.NOT_APPLICABLE,
                acronym_expansions=expansions,
                acronym_ambiguities=ambiguities,
                reason="The question is not a structural matrix lookup.",
            )

        active_provenance = provenance or self.corpus.provenance
        table_candidates = self._table_candidates(retrieval)
        if not table_candidates:
            gap_result = self.gap_worker.evaluate(
                _retrieval_source_refs(retrieval),
                required=True,
                relevant_evidence_refs=_retrieval_evidence_refs(retrieval),
            )
            if gap_result.firewall_code is not None:
                return self._gap_result(gap_result, expansions, ambiguities)
            return StructuralMatrixResult(
                status=StructuralStatus.NO_DIRECT_SUPPORT,
                acronym_expansions=expansions,
                acronym_ambiguities=ambiguities,
                reason="No relevant validated structural matrix was selected.",
            )

        selected_section, table = max(
            table_candidates,
            key=lambda item: self._table_score(item[0], item[1], request),
        )
        source_refs = [selected_section.source_ref]
        scope_state, scope_reason = self._scope_state(request, table)
        base = dict(
            acronym_expansions=expansions,
            acronym_ambiguities=ambiguities,
            source_refs=source_refs,
            primary_source=selected_section.title,
            table_heading=table.heading,
            scope_state=scope_state,
            inspected_row_count=max(0, table.n_rows - table.header_rows),
            inspected_column_count=len(table.verdict.state_columns),
            inspected_record_count=len(table.records) + len(table.rejections),
            table_complete=_table_is_complete(table),
        )
        if scope_state is StructuralScopeState.FALSE:
            return StructuralMatrixResult(
                status=StructuralStatus.WRONG_SCOPE,
                reason=scope_reason,
                **base,
            )

        requested_dimensions = [
            (dimension, requested)
            for dimension in _table_dimensions(table)
            if (requested := self._requested_dimension(request, table, dimension)) is not None
        ]
        records = [
            record
            for record in table.records
            if all(
                self._record_matches(record, requested, dimension)
                for dimension, requested in requested_dimensions
            )
        ]
        columns = self._requested_columns(request, table)
        records = [record for record in records if record.column in columns]
        unresolved: list[ConfigurationRecord] = []
        if _asks_for_session(request.query):
            session_records: list[ConfigurationRecord] = []
            for record in records:
                meaning = _normalise_meaning(record.state_meaning)
                if meaning in self._session_meanings:
                    session_records.append(record)
                elif record.state_meaning is None and record.state != "absent":
                    unresolved.append(record)
            records = session_records
        else:
            unresolved = [record for record in records if record.state_meaning is None]

        claims: list[StructuralEvidenceClaim] = []
        invalid_refs: list[str] = []
        unresolved_states = sorted({record.state for record in unresolved})
        unresolved_refs: list[str] = []
        for record in unresolved:
            reference = self._record_ref(selected_section, table, record, active_provenance)
            if reference:
                unresolved_refs.append(reference)

        for record in records:
            reference = self._record_ref(selected_section, table, record, active_provenance)
            if reference is None:
                invalid_refs.append(
                    f"{selected_section.source_ref}:structured-table-{table.table_index + 1}:"
                    f"row-{record.provenance.row + 1}:col-{record.provenance.col + 1}"
                )
                continue
            unit = active_provenance.resolve(reference)
            if (
                unit is None
                or not unit.structured
                or unit.kind != "table_row"
                or unit.text != record.evidence_text()
            ):
                invalid_refs.append(reference)
                continue
            claim_scope = dict(record.dimensions)
            claims.append(
                StructuralEvidenceClaim(
                    claim_id=f"structured:{record.provenance.page_id}:"
                    f"{record.provenance.table_index}:{record.provenance.row}:"
                    f"{record.provenance.col}",
                    claim_text=unit.text,
                    evidence_ref=reference,
                    supporting_span=unit.text,
                    state=record.state,
                    state_meaning=record.state_meaning,
                    table_heading=record.provenance.heading,
                    column=record.column,
                    dimensions=dict(record.dimensions),
                    applicable_scope=claim_scope,
                    critical_control=_has_control_term(unit.text),
                    unresolved_state=record.state_meaning is None and record.state != "absent",
                )
            )

        base.update(
            matched_record_count=len(records),
            unresolved_states=unresolved_states,
            unresolved_state_refs=list(dict.fromkeys(unresolved_refs)),
        )
        if invalid_refs:
            return StructuralMatrixResult(
                status=StructuralStatus.PROVENANCE_INVALID,
                provenance_valid=False,
                evidence_refs=[],
                reason="One or more structural records failed local provenance validation.",
                **base,
            )
        if not claims:
            gap_result = self.gap_worker.evaluate(
                source_refs,
                required=True,
                relevant_evidence_refs=_retrieval_evidence_refs(retrieval),
            )
            if gap_result.firewall_code is not None:
                return self._gap_result(gap_result, expansions, ambiguities, **base)
            return StructuralMatrixResult(
                status=StructuralStatus.NO_DIRECT_SUPPORT,
                provenance_valid=not invalid_refs,
                reason=(
                    "No source-declared rows match the requested dimensions and session state."
                ),
                **base,
            )
        return StructuralMatrixResult(
            status=StructuralStatus.SUFFICIENT,
            claims=claims,
            evidence_refs=[claim.evidence_ref for claim in claims],
            provenance_valid=True,
            reason=(
                f"Inspected all {base['inspected_row_count']} relevant rows and "
                f"{base['inspected_column_count']} state columns; admitted "
                f"{len(claims)} directly supported records."
            ),
            **base,
        )

    def _gap_result(
        self,
        gap_result: SourceGapResult,
        expansions: dict[str, str],
        ambiguities: dict[str, list[str]],
        **extra: Any,
    ) -> StructuralMatrixResult:
        fields = dict(extra)
        fields.setdefault("acronym_expansions", expansions)
        fields.setdefault("acronym_ambiguities", ambiguities)
        return StructuralMatrixResult(
            status=StructuralStatus.SOURCE_PACKAGE_ASSET_UNAVAILABLE,
            source_package_gap_codes=[gap_result.firewall_code] if gap_result.firewall_code else [],
            source_package_gap_targets=[gap.target for gap in gap_result.gaps],
            reason=gap_result.distinction,
            **fields,
        )

    def _is_matrix_question(self, request: QueryInput, plan: QueryPlan) -> bool:
        if plan.intent.value in self._matrix_intents:
            return True
        terms = set(_tokens(" ".join((request.query, plan.normalised_query))))
        if "dtm" in terms and bool(terms & {"state", "status"}):
            return True
        return bool(terms & self._matrix_terms) and (
            "alert" in terms or "alerts" in terms or "configuration" in terms or "matrix" in terms
        )

    def _table_candidates(
        self,
        retrieval: HybridRetrievalResult | Any,
    ) -> list[tuple[Any, StructuralTableData]]:
        selected = _retrieval_candidates(retrieval)
        selected_section_ids = {
            candidate.section_id for candidate in selected if candidate.section_id is not None
        }
        selected_sources = {candidate.source_ref for candidate in selected}
        exact: list[tuple[Any, StructuralTableData]] = []
        source: list[tuple[Any, StructuralTableData]] = []
        all_tables: list[tuple[Any, StructuralTableData]] = []
        for section in self.corpus.sections:
            for table in section.structured_tables:
                if table.quarantined or not table.verdict.is_matrix:
                    continue
                item = (section, table)
                all_tables.append(item)
                if section.section_id in selected_section_ids:
                    exact.append(item)
                elif section.source_ref in selected_sources:
                    source.append(item)
        return exact or source or all_tables

    def _table_score(
        self,
        section: Any,
        table: StructuralTableData,
        request: QueryInput,
    ) -> tuple[int, int, str]:
        query = _normalised_text(request.query)
        query_tokens = set(_tokens(request.query))
        corpus_text = " ".join(
            (
                section.title,
                *section.heading_path,
                table.heading,
                *table.headers,
                *(value for record in table.records for value in record.dimensions.values()),
            )
        )
        overlap = len(query_tokens & set(_tokens(corpus_text)))
        selected_score = 0
        if table.heading and _normalised_text(table.heading) in query:
            selected_score += 100
        requested_region = _requested_region(request)
        if requested_region and _heading_has_code(table.heading, requested_region):
            selected_score += 80
        requested_service = request.context.get("service_model") or request.context.get("mandate")
        if requested_service and any(
            _same_value(requested_service, value)
            for record in table.records
            for key, value in record.dimensions.items()
            if _is_dimension(key, "service model")
        ):
            selected_score += 60
        return (selected_score + overlap, -table.table_index, section.section_id)

    def _scope_state(
        self,
        request: QueryInput,
        table: StructuralTableData,
    ) -> tuple[StructuralScopeState, str]:
        requested_region = _requested_region(request)
        heading_declares_location = bool(
            re.search(r"\badvisory locations?\b|\bbc\s+[A-Za-z]{2,3}\b", table.heading, re.I)
        )
        region_state: StructuralScopeState | None = None
        if requested_region:
            if _heading_has_code(table.heading, requested_region):
                region_state = StructuralScopeState.TRUE
            elif heading_declares_location:
                region_state = StructuralScopeState.FALSE
            else:
                region_state = StructuralScopeState.UNKNOWN

        requested_service = self._requested_dimension(request, table, "service model")
        declared_service_values = [
            value
            for record in table.records
            for key, value in record.dimensions.items()
            if _is_dimension(key, "service model")
        ]
        service_state: StructuralScopeState | None = None
        if requested_service:
            if any(_same_value(requested_service, value) for value in declared_service_values):
                service_state = StructuralScopeState.TRUE
            elif declared_service_values:
                service_state = StructuralScopeState.FALSE
            else:
                service_state = StructuralScopeState.UNKNOWN

        states = [state for state in (region_state, service_state) if state is not None]
        if StructuralScopeState.FALSE in states:
            return (
                StructuralScopeState.FALSE,
                "The selected table explicitly declares a conflicting scope.",
            )
        if StructuralScopeState.TRUE in states:
            return (
                StructuralScopeState.TRUE,
                "The selected table explicitly covers the requested scope.",
            )
        return (
            StructuralScopeState.UNKNOWN,
            "The source does not explicitly declare the requested scope.",
        )

    def _requested_dimension(
        self,
        request: QueryInput,
        table: StructuralTableData,
        dimension: str,
    ) -> str | None:
        for key, value in request.context.items():
            if _is_dimension(key, dimension) or (
                dimension == "service model" and _is_dimension(key, "mandate")
            ):
                if value.strip():
                    return value.strip()
        for record in table.records:
            for key, value in record.dimensions.items():
                if _is_dimension(key, dimension) and _contains_value(request.query, value):
                    return value
        return None

    def _record_matches(
        self,
        record: ConfigurationRecord,
        requested: str | None,
        dimension: str,
    ) -> bool:
        if requested is None:
            return True
        values = [
            value for key, value in record.dimensions.items() if _is_dimension(key, dimension)
        ]
        return any(_same_value(requested, value) for value in values)

    def _requested_columns(
        self,
        request: QueryInput,
        table: StructuralTableData,
    ) -> set[str]:
        headers = [
            table.headers[index]
            for index in table.verdict.state_columns
            if index < len(table.headers) and table.headers[index]
        ]
        query = _normalised_text(request.query)
        specific = {
            header
            for header in headers
            if _normalised_text(header) in query
            or (
                len(_tokens(header)) >= 2
                and set(_tokens(header)).issubset(set(_tokens(request.query)))
            )
            or any(_contains_value(request.query, acronym) for acronym in _header_acronyms(header))
        }
        return specific or set(headers)

    def _record_ref(
        self,
        section: Any,
        table: StructuralTableData,
        record: ConfigurationRecord,
        provenance: ProvenanceIndex,
    ) -> str | None:
        reference = (
            f"{provenance.section_ref(section)}:structured-table-{table.table_index + 1}:"
            f"row-{record.provenance.row + 1}:col-{record.provenance.col + 1}"
        )
        return reference if provenance.resolve(reference) is not None else None

    def _acronym_state(
        self,
        request: QueryInput,
    ) -> tuple[dict[str, str], dict[str, list[str]]]:
        structural = self.corpus.structural
        if structural is None:
            return {}, {}
        query = request.query
        requested_region = _requested_region(request)
        found: dict[str, dict[str, str]] = defaultdict(dict)
        for entry in structural.glossary.entries:
            if not entry.verified:
                continue
            # Two-letter corpus glossary entries can also be jurisdiction/location
            # codes in a source heading (for example a country code followed by a
            # booking-centre code).  In that explicit dimension context they are
            # not acronym ambiguity signals.
            if requested_region and _is_location_code(entry.acronym, requested_region, query):
                continue
            if re.search(rf"(?<!\w){re.escape(entry.acronym)}(?!\w)", query, re.I):
                found[entry.acronym.casefold()].setdefault(
                    normalise_expansion(entry.expansion), entry.expansion
                )
        expansions: dict[str, str] = {}
        ambiguities: dict[str, list[str]] = {}
        for key, values in found.items():
            ordered = sorted(values.values(), key=str.casefold)
            if len(ordered) == 1:
                expansions[key.upper()] = ordered[0]
            elif ordered:
                ambiguities[key.upper()] = ordered
        return expansions, ambiguities


def _retrieval_candidates(retrieval: HybridRetrievalResult | Any) -> tuple[Any, ...]:
    if isinstance(retrieval, HybridRetrievalResult):
        return tuple(retrieval.selected_candidates)
    deterministic = getattr(retrieval, "deterministic_result", None)
    if deterministic is not None:
        return tuple(getattr(deterministic, "selected_candidates", ()))
    return tuple(getattr(retrieval, "selected_candidates", ()))


def _retrieval_source_refs(retrieval: HybridRetrievalResult | Any) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(candidate.source_ref for candidate in _retrieval_candidates(retrieval))
    )


def _retrieval_evidence_refs(retrieval: HybridRetrievalResult | Any) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            ref
            for candidate in _retrieval_candidates(retrieval)
            for ref in getattr(candidate, "unit_refs", ())
        )
    )


def _page_id(filename: str) -> str:
    return Path(filename).name.rsplit(".", 1)[0]


def _table_is_complete(table: StructuralTableData) -> bool:
    expected = max(0, table.n_rows - table.header_rows) * len(table.verdict.state_columns)
    return (
        table.verdict.is_matrix
        and table.verdict.has_declared_header
        and expected == len(table.records) + len(table.rejections)
        and not table.rejections
    )


def _table_dimensions(table: StructuralTableData) -> tuple[str, ...]:
    """Return dimension headings in stable first-seen order."""

    return tuple(
        dict.fromkeys(key for record in table.records for key in record.dimensions if key.strip())
    )


def _header_acronyms(header: str) -> tuple[str, ...]:
    """Return explicit parenthesized abbreviations from a table heading."""

    return tuple(
        match
        for match in re.findall(r"\(([A-Za-z][A-Za-z0-9&/.-]{1,15})\)", header)
        if len(match) >= 2
    )


def _normalised_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.casefold()) if len(token) >= 3]


def _normalise_value(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _same_value(left: str, right: str) -> bool:
    left_value = _normalise_value(left).replace("region ", "").replace("service ", "")
    right_value = _normalise_value(right).replace("region ", "").replace("service ", "")
    return left_value == right_value


def _contains_value(query: str, value: str) -> bool:
    query_text = _normalised_text(query)
    value_text = _normalised_text(value)
    return bool(value_text) and value_text in query_text


def _is_dimension(key: str, dimension: str) -> bool:
    return _normalised_text(key) == _normalised_text(dimension)


def _requested_region(request: QueryInput) -> str | None:
    for key, value in request.context.items():
        if _normalised_text(key) in {"region", "location", "advisory location"} and value.strip():
            return _region_code(value)
    for pattern in (
        r"\badvisory location\s+([A-Za-z]{2,3})\b",
        r"\bbc\s+([A-Za-z]{2,3})\b",
    ):
        match = re.search(pattern, request.query, re.I)
        if match:
            return match.group(1).upper()
    return None


def _region_code(value: str) -> str:
    return re.sub(r"^region[_ -]?", "", value.strip(), flags=re.I).split()[0].upper()


def _heading_has_code(heading: str, code: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z]){re.escape(code)}(?![A-Za-z])", heading, re.I))


def _is_location_code(acronym: str, region: str, query: str) -> bool:
    """Avoid treating explicitly paired location codes as semantic ambiguity."""

    if acronym.casefold() == region.casefold():
        return True
    if len(acronym) > 3:
        return False
    return bool(
        re.search(
            rf"(?<!\w)(?:{re.escape(acronym)}\s+{re.escape(region)}|"
            rf"{re.escape(region)}\s+{re.escape(acronym)})(?!\w)",
            query,
            re.I,
        )
    )


def _normalise_meaning(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _asks_for_session(query: str) -> bool:
    lowered = query.casefold()
    return ("session" in lowered and "alert" in lowered) or "interactive session" in lowered


def _has_control_term(text: str) -> bool:
    lowered = text.casefold()
    return any(
        re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered)
        for term in ("must", "cannot", "required", "prohibited", "must not")
    )


__all__ = [
    "SourceGapResult",
    "SourceGapWorker",
    "StructuralEvidenceClaim",
    "StructuralMatrixResult",
    "StructuralMatrixWorker",
    "StructuralScopeState",
    "StructuralStatus",
]
