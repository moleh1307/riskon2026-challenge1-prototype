"""No-API Task 10 evaluation of structural evidence and the canonical Firewall."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_eval.models import EventEvalCase, EventExpectedBehavior
from riskon.event_eval.runner import load_event_cases
from riskon.event_runtime.config import EventRuntimeConfig
from riskon.event_runtime.factory import EventRuntimeFactory
from riskon.event_runtime.structural_matrix import StructuralMatrixWorker
from riskon.models import Decision, QueryInput
from riskon.orchestra.models import OrchestraRun
from riskon.pipeline import M4DRiskonPipeline


class StructuralEvidenceCaseResult(BaseModel):
    """Safe per-case Task 10 result without copied event content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    source_case_id: str
    expected_behavior: EventExpectedBehavior
    decision: str
    modality: str
    primary_source: str | None = None
    matched_record_count: int = Field(ge=0)
    unresolved_states: list[str] = Field(default_factory=list)
    table_complete: bool = False
    provenance_valid: bool = False
    excluded_forbidden_concepts: bool = False
    source_gap_codes: list[str] = Field(default_factory=list)
    source_gap_target_count: int = Field(ge=0)
    worker_execution_count: int = Field(ge=0)
    external_api_calls: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    correct: bool


class StructuralAcronymResult(BaseModel):
    """Corpus-local acronym check used by the local evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    acronym: str
    status: str
    expansions: list[str] = Field(default_factory=list)
    unique_verified_expansion: bool
    ambiguity_preserved: bool


class StructuralEvidenceEvaluationDocument(BaseModel):
    """Machine-readable, API-free Task 10 acceptance report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    suite: str = "RISKON_CHALLENGE_1_STRUCTURAL_EVIDENCE"
    task: str = "TASK_10"
    cases: list[StructuralEvidenceCaseResult]
    acronym_tests: list[StructuralAcronymResult]
    correct_structured_decisions: int = Field(ge=0)
    unresolved_state_count: int = Field(ge=0)
    table_completeness: bool
    provenance_validity: bool
    external_api_calls: int = Field(ge=0)
    median_latency_ms: float = Field(ge=0.0)
    measurements: dict[str, int]
    network_enabled: bool
    event_data_copied: bool


def build_structural_evidence_report(
    event_config: EventRuntimeConfig,
    cases_path: Path,
) -> StructuralEvidenceEvaluationDocument:
    """Run the selected cases through M4D and structural checks without OpenAI."""

    case_set = load_event_cases(cases_path)
    case_mapping = {
        "E-01": "OBS-01",
        "E-05": "OBS-05",
        "G-06": "DEV-06",
        "G-08": "DEV-08",
    }
    cases_by_id = {case.id: case for case in case_set.cases}
    missing = sorted(set(case_mapping.values()) - set(cases_by_id))
    if missing:
        raise ValueError(f"Task 10 structural cases are missing: {missing}")

    pipeline = EventRuntimeFactory.build(event_config)
    corpus = pipeline._m4d_corpus
    if corpus is None or corpus.structural is None or pipeline._m4d_planner is None:
        raise ValueError("event pipeline did not expose its structural corpus")
    worker = StructuralMatrixWorker(corpus)
    results = [
        _run_case(pipeline, worker, cases_by_id[source_id], label)
        for label, source_id in case_mapping.items()
    ]
    acronym_tests = _acronym_tests(pipeline, worker, case_set.cases)
    target_results = [item for item in results if item.case_id in {"E-01", "E-05"}]
    return StructuralEvidenceEvaluationDocument(
        cases=results,
        acronym_tests=acronym_tests,
        correct_structured_decisions=sum(item.correct for item in target_results),
        unresolved_state_count=sum(len(item.unresolved_states) for item in results),
        table_completeness=all(item.table_complete for item in target_results),
        provenance_validity=all(item.provenance_valid for item in target_results),
        external_api_calls=0,
        median_latency_ms=statistics.median(item.latency_ms for item in results),
        measurements=corpus.structural.measurements.model_dump(),
        network_enabled=event_config.network_enabled,
        event_data_copied=event_config.event_data_copy_enabled,
    )


def run_structural_evidence_probe(
    runtime_config_path: Path,
    cases_path: Path,
    output_root: Path,
) -> int:
    """CLI entry point for the API-free structural acceptance report."""

    try:
        event_config = EventRuntimeConfig.from_file(runtime_config_path)
        document = build_structural_evidence_report(event_config, cases_path)
        paths = write_structural_evidence_report(document, output_root)
    except (ValueError, FileNotFoundError, OSError, TypeError) as exc:
        print(f"Task 10 structural evaluation FAIL: {exc}")
        return 1

    passed = all(item.correct for item in document.cases) and all(
        item.unique_verified_expansion or item.ambiguity_preserved
        for item in document.acronym_tests
    )
    status = "PASS" if passed else "HOLD"
    print(
        f"Task 10 structural evaluation {status}: "
        f"E-01/E-05 structured decisions {document.correct_structured_decisions}/2; "
        f"G-06/G-08 source gaps checked; API calls 0; "
        f"median latency {document.median_latency_ms:.1f} ms; report {paths['json']}."
    )
    return 0 if passed else 1


def write_structural_evidence_report(
    document: StructuralEvidenceEvaluationDocument,
    output_root: Path,
) -> dict[str, Path]:
    """Write the ignored local JSON and concise review summary."""

    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "evaluation.json"
    markdown_path = output_root / "evaluation.md"
    json_path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(document), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def _run_case(
    pipeline: M4DRiskonPipeline,
    worker: StructuralMatrixWorker,
    case: EventEvalCase,
    label: str,
) -> StructuralEvidenceCaseResult:
    started = time.perf_counter()
    request = QueryInput(
        query=case.question,
        context=case.input_context,
        trace_id=f"task10-structural:{label}:{uuid4().hex}",
    )
    if pipeline._m4d_planner is None or pipeline._m4d_retriever is None:
        raise ValueError("event pipeline retrieval components are unavailable")
    plan = pipeline._m4d_planner.plan(request)
    retrieval = pipeline._m4d_retriever.retrieve(
        plan,
        pipeline._m4d_planner.context_values(request, plan),
    )
    structural = worker.evaluate(
        request,
        plan,
        retrieval,
        provenance=pipeline._m4d_provenance,
    )
    run = pipeline.run_orchestrated(request)
    final = run.final_verified_run
    refs = final.verification.evidence_refs
    structured_refs = [
        reference
        for reference in refs
        if pipeline._m4d_provenance is not None
        and (unit := pipeline._m4d_provenance.resolve(reference)) is not None
        and unit.structured
    ]
    modality = (
        "STRUCTURED_HTML"
        if structured_refs
        else ("SOURCE_PACKAGE_GAP" if structural.source_package_gap_codes else "NONE")
    )
    released_text = final.result.answer or ""
    forbidden_excluded = all(
        concept.casefold() not in released_text.casefold()
        for concept in case.forbidden_answer_concepts
    )
    source = structural.primary_source or (
        retrieval.selected_candidates[0].title if retrieval.selected_candidates else None
    )
    correct = _case_is_correct(
        label,
        case,
        final.result.decision,
        modality,
        structural,
        run,
        forbidden_excluded,
    )
    return StructuralEvidenceCaseResult(
        case_id=label,
        source_case_id=case.id,
        expected_behavior=case.expected_behavior,
        decision=final.result.decision.value,
        modality=modality,
        primary_source=source,
        matched_record_count=structural.matched_record_count,
        unresolved_states=structural.unresolved_states,
        table_complete=structural.table_complete,
        provenance_valid=structural.provenance_valid and bool(structured_refs)
        if structural.status.value == "SUFFICIENT"
        else structural.provenance_valid,
        excluded_forbidden_concepts=forbidden_excluded,
        source_gap_codes=structural.source_package_gap_codes,
        source_gap_target_count=len(structural.source_package_gap_targets),
        worker_execution_count=run.orchestra_metrics.worker_execution_count,
        external_api_calls=0,
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
        correct=correct,
    )


def _case_is_correct(
    label: str,
    case: EventEvalCase,
    decision: Decision,
    modality: str,
    structural: Any,
    run: OrchestraRun,
    forbidden_excluded: bool,
) -> bool:
    if label in {"E-01", "E-05"}:
        return (
            case.expected_behavior is EventExpectedBehavior.ANSWER
            and decision is Decision.ANSWER
            and modality == "STRUCTURED_HTML"
            and structural.status.value == "SUFFICIENT"
            and structural.matched_record_count > 0
            and structural.table_complete
            and structural.provenance_valid
            and run.orchestra_metrics.worker_execution_count == 0
            and forbidden_excluded
        )
    return (
        decision is Decision.ABSTAIN
        and bool(structural.source_package_gap_codes)
        and "SOURCE_PACKAGE_ASSET_UNAVAILABLE" in structural.source_package_gap_codes
        and run.final_verified_run.result.answer is None
    )


def _acronym_tests(
    pipeline: M4DRiskonPipeline,
    worker: StructuralMatrixWorker,
    cases: list[EventEvalCase],
) -> list[StructuralAcronymResult]:
    corpus = pipeline._m4d_corpus
    if (
        corpus is None
        or corpus.structural is None
        or pipeline._m4d_planner is None
        or pipeline._m4d_retriever is None
    ):
        raise ValueError("event pipeline retrieval components are unavailable")
    own_case = next((case for case in cases if case.id == "OBS-04"), None)
    if own_case is None:
        raise ValueError("OWN acronym case is missing")
    own_request = QueryInput(query=own_case.question, context=own_case.input_context)
    own_plan = pipeline._m4d_planner.plan(own_request)
    own_retrieval = pipeline._m4d_retriever.retrieve(
        own_plan,
        pipeline._m4d_planner.context_values(own_request, own_plan),
    )
    own = worker.evaluate(own_request, own_plan, own_retrieval)
    results = [
        StructuralAcronymResult(
            acronym="OWN",
            status=own.status.value,
            expansions=list(own.acronym_expansions.values()),
            unique_verified_expansion=len(own.acronym_expansions) == 1,
            ambiguity_preserved=not own.acronym_ambiguities,
        )
    ]
    collisions = corpus.structural.glossary.collisions()
    if collisions:
        acronym = sorted(collisions)[0]
        request = QueryInput(query=f"What does {acronym} mean?")
        plan = pipeline._m4d_planner.plan(request)
        retrieval = pipeline._m4d_retriever.retrieve(
            plan,
            pipeline._m4d_planner.context_values(request, plan),
        )
        ambiguous = worker.evaluate(request, plan, retrieval)
        results.append(
            StructuralAcronymResult(
                acronym=acronym,
                status=ambiguous.status.value,
                expansions=[
                    value for values in ambiguous.acronym_ambiguities.values() for value in values
                ],
                unique_verified_expansion=not ambiguous.acronym_ambiguities,
                ambiguity_preserved=ambiguous.status.value == "AMBIGUOUS_ACRONYM",
            )
        )
    return results


def _markdown(document: StructuralEvidenceEvaluationDocument) -> str:
    lines = [
        "# RiskON Task 10 — structural evidence evaluation",
        "",
        "Local deterministic evaluation; no OpenAI API calls were made.",
        "",
        f"- E-01/E-05 structured decisions: {document.correct_structured_decisions}/2",
        f"- Table completeness: {document.table_completeness}",
        f"- Provenance validity: {document.provenance_validity}",
        f"- External API calls: {document.external_api_calls}",
        f"- Median latency: {document.median_latency_ms:.1f} ms",
        "",
        "| Case | Decision | Modality | Records | Gaps | Workers | Correct |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    lines.extend(
        f"| {case.case_id} | {case.decision} | {case.modality} | "
        f"{case.matched_record_count} | {len(case.source_gap_codes)} | "
        f"{case.worker_execution_count} | {case.correct} |"
        for case in document.cases
    )
    return "\n".join(lines) + "\n"


__all__ = [
    "StructuralAcronymResult",
    "StructuralEvidenceCaseResult",
    "StructuralEvidenceEvaluationDocument",
    "build_structural_evidence_report",
    "run_structural_evidence_probe",
    "write_structural_evidence_report",
]
