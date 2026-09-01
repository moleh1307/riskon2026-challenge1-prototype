"""Golden Core 17 evaluation for the bounded Task 5 evidence firewall."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_eval.models import EventEvalCase, EventExpectedBehavior
from riskon.event_eval.runner import load_event_cases
from riskon.event_runtime.config import EventRuntimeConfig, load_event_runtime_config
from riskon.event_runtime.evidence_reasoning import (
    EventEvidenceReasoningResult,
    build_event_evidence_reasoning_runtime,
)
from riskon.event_runtime.evidence_reasoning_models import (
    CLAIM_BUILDER_MODEL,
    CLAIM_BUILDER_REASONING,
    CONTEXT_INTERPRETER_MODEL,
    CONTEXT_INTERPRETER_REASONING,
    SKEPTIC_MODEL,
    SKEPTIC_REASONING,
)
from riskon.event_runtime.llm_client import (
    PAGE_CARD_MODEL,
    PAGE_CARD_REASONING,
    ROUTER_RETRY_MODEL,
    ROUTER_RETRY_REASONING,
    TITLE_ROUTER_MODEL,
    TITLE_ROUTER_REASONING,
    LLMConfigurationError,
    SemanticLLMError,
    Task5LLMConfig,
)
from riskon.models import Decision, QueryInput


class Task5Objection(BaseModel):
    """Bounded report view of one material or non-material skeptic finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: str = Field(min_length=1)
    material: bool
    detail: str = Field(min_length=1, max_length=500)
    target_claim_id: str = Field(min_length=1)


class Task5CaseResult(BaseModel):
    """One Golden Core 17 result without raw evidence or prompt content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    expected_behavior: EventExpectedBehavior
    decision: str | None = None
    behavior_match: bool = False
    primary_source: str | None = None
    answer_snippet: str | None = Field(default=None, max_length=1200)
    clarification_snippet: str | None = Field(default=None, max_length=600)
    retry_used: bool = False
    context_clarification: bool = False
    material_objections: list[Task5Objection] = Field(default_factory=list)
    final_failure_reason: str | None = Field(default=None, max_length=1000)
    evidence_sufficiency: str | None = None
    claim_count: int = Field(default=0, ge=0)
    approved_claim_count: int = Field(default=0, ge=0)
    evidence_refs: list[str] = Field(default_factory=list)
    citation_valid: bool = False
    validation_errors: list[str] = Field(default_factory=list)
    scope_violation_count: int = Field(default=0, ge=0)
    critical_control_omission_count: int = Field(default=0, ge=0)
    unsupported_released_claims: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    runtime_error: str | None = None


class Task5Metrics(BaseModel):
    """Aggregate safety, decision, retry, and fixed-policy accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cases_executed: int = Field(ge=0)
    decision_match_count: int = Field(ge=0)
    answer_count: int = Field(ge=0)
    clarify_count: int = Field(ge=0)
    abstain_count: int = Field(ge=0)
    answer_citation_valid_count: int = Field(ge=0)
    answer_citation_validity: float = Field(ge=0.0, le=1.0)
    citation_validity: float = Field(ge=0.0, le=1.0)
    retrieval_retry_count: int = Field(ge=0)
    context_clarification_count: int = Field(ge=0)
    scope_violation_count: int = Field(ge=0)
    critical_control_omission_count: int = Field(ge=0)
    unsupported_released_claims: int = Field(ge=0)
    runtime_error_count: int = Field(ge=0)
    median_latency_ms: float = Field(ge=0.0)
    llm_calls: int = Field(ge=0)
    context_interpreter_calls: int = Field(ge=0)
    claim_builder_calls: int = Field(ge=0)
    skeptic_calls: int = Field(ge=0)
    title_router_calls: int = Field(ge=0)
    router_retry_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    total_llm_latency_ms: float = Field(ge=0.0)


class Task5Document(BaseModel):
    """Machine-readable Task 5 report with no event-data copy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    suite: str
    task: str
    metrics: Task5Metrics
    cases: list[Task5CaseResult]
    fixed_policy: dict[str, str]
    page_card_cache_path: str
    page_cards_are_routing_only: bool
    original_evidence_only: bool
    deterministic_answer_firewall_authoritative: bool
    network_enabled: bool
    event_data_copied: bool


def run_evidence_reasoning_probe(
    runtime_config_path: Path,
    cases_path: Path,
    output_root: Path,
) -> int:
    """Execute Task 5 against the frozen Golden Core 17 and write diagnostics."""

    try:
        event_config = load_event_runtime_config(runtime_config_path)
        case_set = load_event_cases(cases_path)
        config = Task5LLMConfig()
        runtime = build_event_evidence_reasoning_runtime(event_config, config=config)
        results = [_run_case(case, runtime) for case in case_set.cases]
        document = _build_document(results, runtime, event_config)
        paths = write_task5_reports(document, output_root)
    except LLMConfigurationError as exc:
        print(f"Task 5 evidence reasoning BLOCKED: {exc}")
        return 2
    except SemanticLLMError as exc:
        print(
            "Task 5 evidence reasoning BLOCKED: fixed-policy OpenAI call failed; "
            f"no model substitution was attempted ({exc})."
        )
        return 2
    except (ValueError, FileNotFoundError, OSError, TypeError) as exc:
        print(f"Task 5 evidence reasoning FAIL: {exc}")
        return 1

    metrics = document.metrics
    safety_passed = (
        metrics.cases_executed == 17
        and metrics.runtime_error_count == 0
        and metrics.unsupported_released_claims == 0
        and metrics.scope_violation_count == 0
        and metrics.critical_control_omission_count == 0
        and metrics.answer_citation_validity == 1.0
        and not document.network_enabled
        and not document.event_data_copied
    )
    status = "PASS" if safety_passed else "HOLD"
    print(
        f"Task 5 evidence reasoning {status}: {metrics.cases_executed}/17; "
        f"decision match {metrics.decision_match_count}/17; "
        f"ANSWER/CLARIFY/ABSTAIN {metrics.answer_count}/"
        f"{metrics.clarify_count}/{metrics.abstain_count}; "
        f"answer citation validity {metrics.answer_citation_valid_count}/"
        f"{metrics.answer_count}; retries {metrics.retrieval_retry_count}; "
        f"LLM calls {metrics.llm_calls}; report {paths['evaluation']}."
    )
    return 0 if safety_passed else 1


def _run_case(
    case: EventEvalCase,
    runtime: Any,
) -> Task5CaseResult:
    try:
        started = time.perf_counter()
        result = runtime.run(
            QueryInput(
                query=case.question,
                context=case.input_context,
                trace_id=f"event-task5:{case.id}",
            )
        )
        elapsed = round((time.perf_counter() - started) * 1000, 3)
        return _case_result(case, result, elapsed)
    except SemanticLLMError:
        raise
    except Exception as exc:  # pragma: no cover - defensive report boundary
        return Task5CaseResult(
            case_id=case.id,
            expected_behavior=case.expected_behavior,
            final_failure_reason=type(exc).__name__,
            latency_ms=0.0,
            runtime_error=type(exc).__name__,
        )


def _case_result(
    case: EventEvalCase,
    result: EventEvidenceReasoningResult,
    elapsed_ms: float,
) -> Task5CaseResult:
    actual = result.decision.value
    behavior_match = _behavior_matches(case.expected_behavior, result)
    citation_valid = _citation_valid(result)
    objections = [
        Task5Objection(
            category=item.category.value,
            material=item.material,
            detail=item.detail,
            target_claim_id=item.target_claim_id,
        )
        for item in (result.skeptic.objections if result.skeptic is not None else [])
        if item.material
    ]
    failure_reason = _failure_reason(result)
    final_analysis = result.final_analysis
    return Task5CaseResult(
        case_id=case.id,
        expected_behavior=case.expected_behavior,
        decision=actual,
        behavior_match=behavior_match,
        primary_source=result.primary_source,
        answer_snippet=_clip(result.answer, 1200),
        clarification_snippet=_clip(result.clarifying_question, 600),
        retry_used=result.retry_used,
        context_clarification=bool(result.context_assessment.missing_context_fields),
        material_objections=objections,
        final_failure_reason=failure_reason,
        evidence_sufficiency=(
            final_analysis.evidence_sufficiency.value if final_analysis is not None else None
        ),
        claim_count=len(final_analysis.material_claims) if final_analysis is not None else 0,
        approved_claim_count=len(result.validated_claims),
        evidence_refs=list(result.evidence_refs),
        citation_valid=citation_valid,
        validation_errors=list(result.validation_errors),
        scope_violation_count=result.scope_violation_count,
        critical_control_omission_count=result.critical_control_omission_count,
        unsupported_released_claims=result.unsupported_released_claims,
        latency_ms=elapsed_ms,
    )


def _build_document(
    results: list[Task5CaseResult],
    runtime: Any,
    event_config: EventRuntimeConfig,
) -> Task5Document:
    usage = runtime.client.usage
    answer_cases = [item for item in results if item.decision == Decision.ANSWER.value]
    valid_answers = sum(item.citation_valid for item in answer_cases)
    answer_validity = valid_answers / len(answer_cases) if answer_cases else 1.0
    latencies = [item.latency_ms for item in results]
    metrics = Task5Metrics(
        cases_executed=len(results),
        decision_match_count=sum(item.behavior_match for item in results),
        answer_count=sum(item.decision == Decision.ANSWER.value for item in results),
        clarify_count=sum(item.decision == Decision.CLARIFY.value for item in results),
        abstain_count=sum(item.decision == Decision.ABSTAIN.value for item in results),
        answer_citation_valid_count=valid_answers,
        answer_citation_validity=answer_validity,
        citation_validity=answer_validity,
        retrieval_retry_count=sum(item.retry_used for item in results),
        context_clarification_count=sum(
            item.context_clarification and item.decision == Decision.CLARIFY.value
            for item in results
        ),
        scope_violation_count=sum(item.scope_violation_count for item in results),
        critical_control_omission_count=sum(
            item.critical_control_omission_count for item in results
        ),
        unsupported_released_claims=sum(item.unsupported_released_claims for item in results),
        runtime_error_count=sum(item.runtime_error is not None for item in results),
        median_latency_ms=statistics.median(latencies) if latencies else 0.0,
        llm_calls=usage.total_calls,
        context_interpreter_calls=usage.context_interpreter_calls,
        claim_builder_calls=usage.claim_builder_calls,
        skeptic_calls=usage.skeptic_calls,
        title_router_calls=usage.title_router_calls,
        router_retry_calls=usage.router_retry_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        total_llm_latency_ms=usage.latency_ms,
    )
    return Task5Document(
        schema_version="1.0",
        suite="RISKON_CHALLENGE_1",
        task="TASK_5_EVIDENCE_REASONING",
        metrics=metrics,
        cases=results,
        fixed_policy={
            "context_interpreter": f"{CONTEXT_INTERPRETER_MODEL}/{CONTEXT_INTERPRETER_REASONING}",
            "claim_builder": f"{CLAIM_BUILDER_MODEL}/{CLAIM_BUILDER_REASONING}",
            "skeptic": f"{SKEPTIC_MODEL}/{SKEPTIC_REASONING}",
            "page_card": f"{PAGE_CARD_MODEL}/{PAGE_CARD_REASONING}",
            "title_router": f"{TITLE_ROUTER_MODEL}/{TITLE_ROUTER_REASONING}",
            "router_retry": f"{ROUTER_RETRY_MODEL}/{ROUTER_RETRY_REASONING}",
        },
        page_card_cache_path=str(event_config.generated_root / "semantic" / "page_cards.json"),
        page_cards_are_routing_only=True,
        original_evidence_only=True,
        deterministic_answer_firewall_authoritative=True,
        network_enabled=event_config.network_enabled,
        event_data_copied=event_config.event_data_copy_enabled,
    )


def _behavior_matches(
    case_expected: EventExpectedBehavior, result: EventEvidenceReasoningResult
) -> bool:
    if case_expected is EventExpectedBehavior.ANSWER:
        return result.decision is Decision.ANSWER
    if case_expected is EventExpectedBehavior.CLARIFY:
        return result.decision is Decision.CLARIFY
    return result.decision is Decision.ABSTAIN and result.route is not None


def _citation_valid(result: EventEvidenceReasoningResult) -> bool:
    if result.decision is not Decision.ANSWER:
        return True
    if not result.validated_claims or not result.evidence_refs:
        return False
    if (
        result.scope_violation_count
        or result.unsupported_released_claims
        or not result.result.evidence
    ):
        return False
    return all(
        ref in claim.evidence_refs
        for ref in result.evidence_refs
        for claim in result.validated_claims
        if ref in claim.evidence_refs
    )


def _failure_reason(result: EventEvidenceReasoningResult) -> str | None:
    if result.decision is Decision.ANSWER:
        return None
    if result.reason_codes:
        return ",".join(reason.value for reason in result.reason_codes)
    if result.final_analysis is not None and result.final_analysis.unresolved_issues:
        return "; ".join(result.final_analysis.unresolved_issues[:3])
    return "NO_RELEASED_ANSWER"


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return " ".join(value.split())[:limit]


def write_task5_reports(document: Task5Document, output_root: Path) -> dict[str, Path]:
    """Write ignored bounded JSON, JSONL, and Markdown diagnostics."""

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    evaluation = output_root / "evaluation.json"
    case_results = output_root / "case_results.jsonl"
    summary = output_root / "evaluation.md"
    payload = document.model_dump(mode="json")
    evaluation.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
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
    return {"evaluation": evaluation, "case_results": case_results, "summary": summary}


def _summary_markdown(document: Task5Document) -> str:
    metrics = document.metrics
    lines = [
        "# Task 5 Evidence Reasoning Evaluation",
        "",
        "This is an ignored local diagnostic. It contains no raw event evidence, prompts, "
        "Page Cards, or secrets.",
        "",
        f"- Cases: {metrics.cases_executed}/17",
        f"- Decision match: {metrics.decision_match_count}/17",
        f"- ANSWER / CLARIFY / ABSTAIN: {metrics.answer_count} / "
        f"{metrics.clarify_count} / {metrics.abstain_count}",
        f"- ANSWER citation validity: {metrics.answer_citation_valid_count}/"
        f"{metrics.answer_count} ({metrics.answer_citation_validity:.3f})",
        f"- Retrieval retries: {metrics.retrieval_retry_count}",
        f"- Context clarifications: {metrics.context_clarification_count}",
        f"- Scope violations: {metrics.scope_violation_count}",
        f"- Critical-control omissions: {metrics.critical_control_omission_count}",
        f"- Unsupported released claims: {metrics.unsupported_released_claims}",
        f"- LLM calls: {metrics.llm_calls}; input/output tokens: "
        f"{metrics.input_tokens}/{metrics.output_tokens}",
        f"- Median latency: {metrics.median_latency_ms:.3f} ms",
        "",
        "| Case | Expected | Decision | Primary source | Retry | Failure |",
        "|---|---|---|---|---:|---|",
    ]
    for case in document.cases:
        lines.append(
            f"| {case.case_id} | {case.expected_behavior.value} | "
            f"{case.decision or 'ERROR'} | {_md(case.primary_source)} | "
            f"{'yes' if case.retry_used else 'no'} | {_md(case.final_failure_reason)} |"
        )
    lines.extend(
        [
            "",
            "The deterministic Answer Firewall remains authoritative; Page Cards and router "
            "outputs are routing metadata only.",
        ]
    )
    return "\n".join(lines) + "\n"


def _md(value: str | None) -> str:
    return (value or "-").replace("|", "\\|").replace("\n", " ")


__all__ = [
    "Task5CaseResult",
    "Task5Document",
    "Task5Metrics",
    "run_evidence_reasoning_probe",
    "write_task5_reports",
]
