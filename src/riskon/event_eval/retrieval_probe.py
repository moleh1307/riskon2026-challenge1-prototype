"""Retrieval-only diagnostics for the external event corpus."""

from __future__ import annotations

import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_eval.runner import load_event_cases
from riskon.event_runtime.config import EventRuntimeConfig, load_event_runtime_config
from riskon.event_runtime.factory import (
    EventRetrievalComponents,
    build_event_retrieval_components,
)
from riskon.event_runtime.retrieval import EventHybridRetriever
from riskon.models import QueryInput


class RetrievalProbeCandidate(BaseModel):
    """One bounded candidate diagnostic without full source content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: int = Field(ge=1, le=20)
    candidate_ref: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    title: str = Field(min_length=1)
    heading_path: list[str]
    excerpt: str = Field(max_length=200)
    fused_score: float = Field(ge=0.0)
    channel_scores: dict[str, float]


class RetrievalProbeCase(BaseModel):
    """Bounded retrieval trace for one Golden Map question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    canonical_terms: list[str]
    detected_intent: str = Field(min_length=1)
    subqueries: list[str]
    top_candidate_refs: list[str]
    top_page_titles: list[str]
    top_headings: list[list[str]]
    channel_scores: dict[str, dict[str, float]]
    fused_ranks: dict[str, int]
    candidates: list[RetrievalProbeCandidate]
    expected_source_title_contains: list[str]
    source_hit_rank: int | None = Field(default=None, ge=1)
    selected_section_count: int = Field(ge=0)
    empty_retrieval: bool
    latency_ms: float = Field(ge=0.0)
    runtime_error: str | None = None


class RetrievalProbeMetrics(BaseModel):
    """Aggregate retrieval-only measurements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cases_executed: int = Field(ge=0)
    source_hit_at_1: int = Field(ge=0)
    source_hit_at_5: int = Field(ge=0)
    source_hit_at_10: int = Field(ge=0)
    source_hit_at_20: int = Field(ge=0)
    empty_retrieval_count: int = Field(ge=0)
    mean_selected_sections: float = Field(ge=0.0)
    median_retrieval_latency_ms: float = Field(ge=0.0)
    runtime_error_count: int = Field(ge=0)


class RetrievalProbeDocument(BaseModel):
    """Machine-readable retrieval probe report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    suite: str
    metrics: RetrievalProbeMetrics
    cases: list[RetrievalProbeCase]
    network_enabled: bool
    event_data_copied: bool


def run_retrieval_probe(
    runtime_config_path: Path,
    cases_path: Path,
    output_root: Path,
) -> int:
    """Run the event planner and retriever without terminal answer execution."""

    try:
        event_config = load_event_runtime_config(runtime_config_path)
        case_set = load_event_cases(cases_path)
        components = build_event_retrieval_components(event_config)
        document = build_probe_document(case_set.cases, components, event_config)
        paths = write_probe_reports(document, output_root)
    except (ValueError, FileNotFoundError, OSError, TypeError) as exc:
        print(f"Event retrieval evaluation FAIL: {exc}")
        return 1

    metrics = document.metrics
    total = metrics.cases_executed
    gate_passed = (
        total == 17
        and metrics.runtime_error_count == 0
        and metrics.empty_retrieval_count == 0
        and metrics.source_hit_at_5 >= 15
        and metrics.source_hit_at_10 == total
    )
    status = "PASS" if gate_passed else "HOLD"
    print(
        f"Event retrieval {status}: {total}/17 cases; "
        f"hit@5 {metrics.source_hit_at_5}/{total}; "
        f"hit@10 {metrics.source_hit_at_10}/{total}; "
        f"hit@20 {metrics.source_hit_at_20}/{total}; "
        f"empty {metrics.empty_retrieval_count}; "
        f"runtime errors {metrics.runtime_error_count}; "
        f"report {paths['evaluation']}."
    )
    return 0 if gate_passed else 1


def build_probe_document(
    cases: list[Any],
    components: EventRetrievalComponents,
    event_config: EventRuntimeConfig,
) -> RetrievalProbeDocument:
    """Build a safe probe document from planner/retriever observations."""

    results = [_probe_case(case, components.planner, components.retriever) for case in cases]
    latencies = [item.latency_ms for item in results]
    selected = [item.selected_section_count for item in results]
    metrics = RetrievalProbeMetrics(
        cases_executed=len(results),
        source_hit_at_1=sum(
            item.source_hit_rank is not None and item.source_hit_rank <= 1 for item in results
        ),
        source_hit_at_5=sum(
            item.source_hit_rank is not None and item.source_hit_rank <= 5 for item in results
        ),
        source_hit_at_10=sum(
            item.source_hit_rank is not None and item.source_hit_rank <= 10 for item in results
        ),
        source_hit_at_20=sum(
            item.source_hit_rank is not None and item.source_hit_rank <= 20 for item in results
        ),
        empty_retrieval_count=sum(item.empty_retrieval for item in results),
        mean_selected_sections=statistics.mean(selected) if selected else 0.0,
        median_retrieval_latency_ms=statistics.median(latencies) if latencies else 0.0,
        runtime_error_count=sum(item.runtime_error is not None for item in results),
    )
    return RetrievalProbeDocument(
        schema_version="1.0",
        suite="RISKON_CHALLENGE_1",
        metrics=metrics,
        cases=results,
        network_enabled=event_config.network_enabled,
        event_data_copied=event_config.event_data_copy_enabled,
    )


def write_probe_reports(
    document: RetrievalProbeDocument,
    output_root: Path,
) -> dict[str, Path]:
    """Write bounded JSON, JSONL, Markdown, and error-diagnosis artifacts."""

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    evaluation = output_root / "evaluation.json"
    case_results = output_root / "case_results.jsonl"
    summary = output_root / "evaluation.md"
    diagnosis = output_root / "runtime_error_diagnosis.md"
    evaluation.write_text(
        json.dumps(
            document.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    case_results.write_text(
        "".join(
            json.dumps(item.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) + "\n"
            for item in document.cases
        ),
        encoding="utf-8",
    )
    summary.write_text(_summary_markdown(document), encoding="utf-8")
    diagnosis.write_text(_runtime_error_diagnosis(document), encoding="utf-8")
    return {
        "evaluation": evaluation,
        "case_results": case_results,
        "summary": summary,
        "diagnosis": diagnosis,
    }


def _probe_case(
    case: Any,
    planner: Any,
    retriever: EventHybridRetriever,
) -> RetrievalProbeCase:
    started = time.perf_counter()
    try:
        request = QueryInput(
            query=case.question,
            context=case.input_context,
            trace_id=f"event-retrieval:{case.id}",
        )
        plan = planner.plan(request)
        retrieval = retriever.retrieve(plan, planner.context_values(request, plan))
        ranked = _ranked_candidates(retrieval, retriever)
        documents = _unique_documents(ranked)
        titles = [item.title for item in documents[:20]]
        hit_rank = _source_hit_rank(titles, case.expected_source_title_contains)
        selected_sections = len(
            {
                candidate.section_id
                for candidate in retrieval.selected_candidates
                if candidate.section_id is not None
            }
        )
        return RetrievalProbeCase(
            case_id=case.id,
            query=case.question,
            canonical_terms=list(plan.canonical_terms),
            detected_intent=plan.intent.value,
            subqueries=list(plan.subqueries or [plan.normalised_query]),
            top_candidate_refs=[item.candidate_ref for item in ranked[:20]],
            top_page_titles=titles,
            top_headings=[list(item.heading_path) for item in ranked[:20]],
            channel_scores={item.candidate_ref: item.channel_scores for item in ranked[:20]},
            fused_ranks={item.candidate_ref: item.rank for item in ranked[:20]},
            candidates=ranked[:20],
            expected_source_title_contains=list(case.expected_source_title_contains),
            source_hit_rank=hit_rank,
            selected_section_count=selected_sections,
            empty_retrieval=not ranked,
            latency_ms=_elapsed_ms(started),
        )
    except Exception as exc:  # pragma: no cover - defensive probe boundary
        return RetrievalProbeCase(
            case_id=case.id,
            query=case.question,
            canonical_terms=[],
            detected_intent="UNKNOWN",
            subqueries=[],
            top_candidate_refs=[],
            top_page_titles=[],
            top_headings=[],
            channel_scores={},
            fused_ranks={},
            candidates=[],
            expected_source_title_contains=list(case.expected_source_title_contains),
            selected_section_count=0,
            empty_retrieval=True,
            latency_ms=_elapsed_ms(started),
            runtime_error=type(exc).__name__,
        )


def _ranked_candidates(
    retrieval: Any,
    retriever: EventHybridRetriever,
) -> list[RetrievalProbeCandidate]:
    by_ref: dict[str, dict[str, Any]] = {}
    for entry in retrieval.diagnostics.entries:
        candidate = retriever._candidate_by_ref.get(entry.candidate_ref)
        if candidate is None:
            continue
        record = by_ref.setdefault(
            candidate.candidate_ref,
            {
                "candidate": candidate,
                "fused_score": 0.0,
                "channel_scores": {},
            },
        )
        record["fused_score"] += float(entry.rrf_contribution)
        channel_scores = record["channel_scores"]
        channel = entry.channel.value
        channel_scores[channel] = max(
            float(channel_scores.get(channel, 0.0)),
            float(entry.raw_score),
        )
    ranked_records = sorted(
        (record for record in by_ref.values() if record["fused_score"] > 0.0),
        key=lambda item: (-item["fused_score"], item["candidate"].candidate_ref),
    )
    ranked = []
    for rank, record in enumerate(ranked_records[:20], start=1):
        candidate = record["candidate"]
        ranked.append(
            RetrievalProbeCandidate(
                rank=rank,
                candidate_ref=candidate.candidate_ref,
                source_ref=candidate.source_ref,
                title=candidate.title,
                heading_path=list(candidate.heading_path),
                excerpt=_clip(candidate.excerpt, 200),
                fused_score=round(float(record["fused_score"]), 8),
                channel_scores={
                    key: round(float(value), 8)
                    for key, value in sorted(record["channel_scores"].items())
                },
            )
        )
    return ranked


def _unique_documents(
    candidates: list[RetrievalProbeCandidate],
) -> list[RetrievalProbeCandidate]:
    seen: set[str] = set()
    documents: list[RetrievalProbeCandidate] = []
    for candidate in candidates:
        if candidate.source_ref in seen:
            continue
        seen.add(candidate.source_ref)
        documents.append(candidate)
    return documents


def _source_hit_rank(titles: list[str], expected: list[str]) -> int | None:
    normalized = [" ".join(value.casefold().split()) for value in expected]
    if not normalized:
        return None
    for rank, title in enumerate(titles, start=1):
        current = " ".join(title.casefold().split())
        if any(value in current for value in normalized):
            return rank
    return None


def _summary_markdown(document: RetrievalProbeDocument) -> str:
    metrics = document.metrics
    lines = [
        "# RiskON retrieval-only probe",
        "",
        "This report measures event planning and retrieval only. It does not grade "
        "claims, answers, verification, or routing.",
        "",
        "## Metrics",
        "",
        f"- Cases executed: {metrics.cases_executed}/17",
        f"- Raw source hit@1: {metrics.source_hit_at_1}/{metrics.cases_executed}",
        f"- Raw source hit@5: {metrics.source_hit_at_5}/{metrics.cases_executed}",
        f"- Raw source hit@10: {metrics.source_hit_at_10}/{metrics.cases_executed}",
        f"- Raw source hit@20: {metrics.source_hit_at_20}/{metrics.cases_executed}",
        f"- Empty retrieval count: {metrics.empty_retrieval_count}",
        f"- Mean selected sections: {metrics.mean_selected_sections:.2f}",
        f"- Median retrieval latency: {metrics.median_retrieval_latency_ms:.1f} ms",
        f"- Retrieval runtime errors: {metrics.runtime_error_count}",
        f"- Network enabled: {document.network_enabled}",
        f"- Event data copied: {document.event_data_copied}",
        "",
        "## Failed source-hit cases",
        "",
        "| Case | Hit rank | Expected source title(s) | Top 5 actual titles |",
        "|---|---:|---|---|",
    ]
    failed = [
        item
        for item in document.cases
        if item.expected_source_title_contains
        and (item.source_hit_rank is None or item.source_hit_rank > 5)
    ]
    for item in failed:
        expected = "; ".join(item.expected_source_title_contains) or "(none declared)"
        actual = "; ".join(item.top_page_titles[:5]) or "(none)"
        rank = item.source_hit_rank or "not found"
        lines.append(f"| {item.case_id} | {rank} | {expected} | {actual} |")
    if not failed:
        lines.append("| — | — | none | all expected titles found |")
    lines.extend(
        [
            "",
            "Top candidate diagnostics contain only refs, manifest titles, headings, scores, "
            "and excerpts clipped to 200 characters; full page contents are not stored.",
            "",
        ]
    )
    return "\n".join(lines)


def _runtime_error_diagnosis(document: RetrievalProbeDocument) -> str:
    observed = ", ".join(item.case_id for item in document.cases if item.runtime_error is not None)
    observed_text = observed or "none in retrieval-only probe"
    return "\n".join(
        [
            "# workflow_stage runtime-error diagnosis",
            "",
            "The pre-repair deterministic event baseline reproduced two "
            "CounterfactualDimensionNotImplementedError failures.",
            "",
            "Call path:",
            "",
            "M4DQueryPlanner -> ALERT_RESOLUTION required_context_fields -> "
            "UnifiedOrchestraRuntime counterfactual planning -> "
            "CounterfactualExecutionPolicy.build_variant -> "
            "ContextValueRegistry.dimension",
            "",
            "The registered M4C dimensions are region and service_model. A workflow_stage "
            "dimension therefore fails closed with: M4C dimension is not implemented: "
            "workflow_stage.",
            "",
            "This task does not redesign or fix Counterfactual Sentinel. The retrieval-only "
            "probe bypasses terminal orchestration, so its expected retrieval runtime error "
            "count is zero. Observed probe errors: " + observed_text + ".",
            "",
            "Status: REAL_CORPUS_CLAIM_EXTRACTION_PENDING",
            "",
        ]
    )


def _clip(value: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    cleaned = re.sub(r"(?:/Users|/Volumes|/private/var|/tmp)/[^\s,;]+", "[path]", cleaned)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
