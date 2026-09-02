"""Final Task 7 end-to-end evaluation over the frozen Golden Core 17."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riskon.config import load_milestone5b_config
from riskon.event_eval.policy_atlas_probe import _CachedAtlasRouter, _ReplaySemanticRetriever
from riskon.event_eval.retrieval_probe import (
    _ranked_candidates,
    _source_hit_rank,
    _unique_documents,
)
from riskon.event_eval.runner import load_event_cases
from riskon.event_runtime.config import EventRuntimeConfig, load_event_runtime_config
from riskon.event_runtime.evidence_reasoning import (
    EventEvidenceReasoningResult,
    EventEvidenceReasoningRuntime,
)
from riskon.event_runtime.factory import EventRetrievalComponents, build_event_retrieval_components
from riskon.event_runtime.llm_client import (
    CLAIM_BUILDER_MODEL,
    CLAIM_BUILDER_REASONING,
    CONTEXT_INTERPRETER_MODEL,
    CONTEXT_INTERPRETER_REASONING,
    ROUTER_RETRY_MODEL,
    ROUTER_RETRY_REASONING,
    SKEPTIC_MODEL,
    SKEPTIC_REASONING,
    TITLE_ROUTER_MODEL,
    TITLE_ROUTER_REASONING,
    VISUAL_SCOUT_MODEL,
    VISUAL_SCOUT_REASONING,
    EventOpenAIClient,
    LLMConfigurationError,
    SemanticLLMError,
    Task7LLMConfig,
)
from riskon.event_runtime.page_cards import load_page_cards
from riskon.event_runtime.policy_atlas import (
    AtlasRetrievalApplication,
    PolicyAtlasRouter,
    apply_atlas_retrieval,
    load_answerability_graph,
    load_policy_atlas,
)
from riskon.event_runtime.policy_atlas_models import AtlasRoutingResult
from riskon.event_runtime.semantic_models import SufficiencyStatus
from riskon.event_runtime.semantic_retrieval import (
    SemanticEventRetriever,
    SemanticRetrievalOutcome,
)
from riskon.event_runtime.title_router import PageCardRouter
from riskon.models import Decision, QueryInput
from riskon.routing import ExpertRouter


class Task7CaseResult(BaseModel):
    """One final case row without prompts, image bytes, or generated evidence text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    actual_decision: str | None = None
    decision_match: bool = False
    expected_source_title_contains: list[str]
    source_titles: list[str]
    primary_source: str | None = None
    answer_or_clarification: str | None = None
    modality: str = "none"
    requires_image: bool = False
    retry_used: bool = False
    visual_call_used: bool = False
    visual_verification_used: bool = False
    visual_status: str | None = None
    material_objection_count: int = Field(ge=0)
    remaining_objection_or_failure: str | None = None
    final_failure_reason: str | None = None
    final_citation_valid: bool = False
    unsupported_released_claims: int = Field(ge=0)
    scope_violation_count: int = Field(ge=0)
    released_answer_scope_violations: int = Field(ge=0)
    critical_control_omission_count: int = Field(ge=0)
    released_answer_critical_control_omissions: int = Field(ge=0)
    deterministic_hit_rank: int | None = Field(default=None, ge=1)
    semantic_hit_rank: int | None = Field(default=None, ge=1)
    atlas_hit_rank: int | None = Field(default=None, ge=1)
    routing_count: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    runtime_error: str | None = None


class Task7Metrics(BaseModel):
    """Final correctness, safety, latency, and fixed-policy accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cases_executed: int = Field(ge=0)
    decision_match_count: int = Field(ge=0)
    answer_count: int = Field(ge=0)
    clarify_count: int = Field(ge=0)
    abstain_count: int = Field(ge=0)
    correct_clarification_count: int = Field(ge=0)
    final_citation_valid_count: int = Field(ge=0)
    final_citation_validity: float = Field(ge=0.0, le=1.0)
    unsupported_released_claims: int = Field(ge=0)
    scope_violation_count: int = Field(ge=0)
    released_answer_scope_violations: int = Field(ge=0)
    critical_control_omission_count: int = Field(ge=0)
    released_answer_critical_control_omissions: int = Field(ge=0)
    visual_case_count: int = Field(ge=0)
    visual_case_decision_match_count: int = Field(ge=0)
    verified_visual_support_count: int = Field(ge=0)
    routing_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    visual_call_count: int = Field(ge=0)
    visual_verification_call_count: int = Field(ge=0)
    runtime_error_count: int = Field(ge=0)
    median_latency_ms: float = Field(ge=0.0)
    llm_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    total_llm_latency_ms: float = Field(ge=0.0)
    hard_gates_passed: bool = False


class Task7Document(BaseModel):
    """Machine-readable ignored local diagnostic for the final stabilization run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    suite: str
    task: str
    metrics: Task7Metrics
    cases: list[Task7CaseResult]
    fixed_policy: dict[str, str]
    page_cards_reused: int = Field(ge=0)
    atlas_pages_reused: int = Field(ge=0)
    metadata_is_not_evidence: bool
    deterministic_answer_firewall_authoritative: bool
    network_enabled: bool
    event_data_copied: bool


def run_final_stabilization(
    runtime_config_path: Path,
    cases_path: Path,
    output_root: Path,
) -> int:
    """Run Task 7 against cached event metadata and write ignored diagnostics."""

    try:
        event_config = load_event_runtime_config(runtime_config_path)
        case_set = load_event_cases(cases_path)
        config = Task7LLMConfig()
        components = build_event_retrieval_components(event_config)
        client = EventOpenAIClient(config=config)
        cards = load_page_cards(components.corpus, event_config)
        atlas = load_policy_atlas(components.corpus, event_config)
        graph = load_answerability_graph(atlas, event_config)
        page_router = PageCardRouter(cards.cards, client, config=config)
        semantic = SemanticEventRetriever(
            components.planner,
            components.retriever,
            page_router,
            config=config,
        )
        atlas_router = PolicyAtlasRouter(atlas, graph, client, config=config)
        retrieval_rows, semantic_outcomes, atlas_results = _run_retrieval_variants(
            case_set.cases,
            components,
            semantic,
            atlas_router,
        )
        full_results = _run_full_reasoning(
            case_set.cases,
            components,
            semantic,
            event_config,
            client,
            config,
            atlas,
            graph,
            atlas_router,
            semantic_outcomes,
            atlas_results,
        )
        document = _build_document(
            retrieval_rows,
            full_results,
            client,
            event_config,
            len(cards.cards),
            len(atlas.fingerprints),
        )
        paths = write_final_reports(document, output_root)
    except LLMConfigurationError as exc:
        print(f"Task 7 FINAL BLOCKED: {exc}")
        return 2
    except SemanticLLMError as exc:
        print(
            "Task 7 FINAL BLOCKED: fixed-policy OpenAI call failed; "
            f"no model substitution was attempted ({exc})."
        )
        return 2
    except (ValueError, FileNotFoundError, OSError, TypeError) as exc:
        print(f"Task 7 FINAL FAIL: {exc}")
        return 1

    metrics = document.metrics
    print(
        f"Task 7 FINAL {'PASS' if metrics.hard_gates_passed else 'HOLD'}: "
        f"{metrics.cases_executed}/17; decision match {metrics.decision_match_count}/17; "
        f"ANSWER/CLARIFY/ABSTAIN {metrics.answer_count}/{metrics.clarify_count}/"
        f"{metrics.abstain_count}; citation {metrics.final_citation_validity:.1%}; "
        f"visual {metrics.visual_case_decision_match_count}/{metrics.visual_case_count}; "
        f"LLM calls {metrics.llm_calls}; median {metrics.median_latency_ms:.0f} ms; "
        f"report {paths['evaluation']}."
    )
    return 0 if metrics.hard_gates_passed else 1


def _run_retrieval_variants(
    cases: list[Any],
    components: EventRetrievalComponents,
    semantic: SemanticEventRetriever,
    atlas_router: PolicyAtlasRouter,
) -> tuple[
    list[dict[str, Any]], dict[str, SemanticRetrievalOutcome], dict[str, AtlasRoutingResult]
]:
    """Reuse deterministic and semantic retrieval traces without rebuilding caches."""

    title_by_ref = {section.source_ref: section.title for section in components.corpus.sections}
    rows: list[dict[str, Any]] = []
    outcomes: dict[str, SemanticRetrievalOutcome] = {}
    atlas_results: dict[str, AtlasRoutingResult] = {}
    for case in cases:
        request = QueryInput(
            query=case.question,
            context=case.input_context,
            trace_id=f"task7:retrieval:{case.id}",
        )
        plan = components.planner.plan(request)
        deterministic = components.retriever.retrieve(
            plan,
            components.planner.context_values(request, plan),
        )
        semantic_outcome = semantic.retrieve_initial(request)
        if _retrieval_is_strong(semantic_outcome):
            atlas_application = AtlasRetrievalApplication(
                retrieval=semantic_outcome,
                atlas=AtlasRoutingResult(),
            )
        else:
            atlas_application = apply_atlas_retrieval(
                semantic,
                semantic_outcome,
                request,
                case.input_context,
                atlas_router,
            )
        atlas_outcome = atlas_application.retrieval
        outcomes[case.id] = semantic_outcome
        atlas_results[case.id] = atlas_application.atlas
        deterministic_titles = [
            item.title
            for item in _unique_documents(_ranked_candidates(deterministic, components.retriever))
        ]
        semantic_titles = _titles_for_refs(semantic_outcome.hybrid_page_refs, title_by_ref)
        atlas_titles = _titles_for_refs(atlas_outcome.hybrid_page_refs, title_by_ref)
        semantic_refs = set(semantic_outcome.hybrid_page_refs)
        supporting_refs = set(atlas_application.atlas.supporting_procedure_refs)
        rows.append(
            {
                "case": case,
                "deterministic_titles": deterministic_titles,
                "semantic_titles": semantic_titles,
                "atlas_titles": atlas_titles,
                "atlas": atlas_application.atlas,
                "navigation": bool(supporting_refs - semantic_refs),
                "suppressed": bool(
                    set(atlas_application.atlas.excluded_page_refs).intersection(semantic_refs)
                ),
            }
        )
    return rows, outcomes, atlas_results


def _run_full_reasoning(
    cases: list[Any],
    components: EventRetrievalComponents,
    semantic: SemanticEventRetriever,
    event_config: EventRuntimeConfig,
    client: EventOpenAIClient,
    config: Task7LLMConfig,
    atlas: Any,
    graph: Any,
    atlas_router: PolicyAtlasRouter,
    semantic_outcomes: dict[str, SemanticRetrievalOutcome],
    atlas_results: dict[str, AtlasRoutingResult],
) -> dict[str, EventEvidenceReasoningResult | Exception]:
    """Run the final firewall runtime against replayed initial retrieval outcomes."""

    base_config = load_milestone5b_config(event_config.pipeline_config)
    m0_config = base_config.base.base.base.base.base.base.base.base
    expert_router = ExpertRouter.from_files(
        m0_config.paths.data_root / "experts.json",
        m0_config.paths.data_root / "routing_policy.json",
    )
    initial_by_trace = {f"task7:reasoning:{case.id}": semantic_outcomes[case.id] for case in cases}
    replay = _ReplaySemanticRetriever(semantic, initial_by_trace)
    cached_atlas = {
        _atlas_candidate_key(
            semantic_outcomes[case.id], config.atlas_candidate_limit
        ): atlas_results[case.id]
        for case in cases
    }
    cached_router = _CachedAtlasRouter(atlas_router, cached_atlas)
    runtime = EventEvidenceReasoningRuntime(
        components.corpus,
        replay,  # type: ignore[arg-type]
        client,
        expert_router,
        config=config,
        policy_atlas=atlas,
        answerability_graph=graph,
        atlas_router=cached_router,
        skip_atlas_when_retrieval_strong=True,
    )
    results: dict[str, EventEvidenceReasoningResult | Exception] = {}
    for case in cases:
        try:
            results[case.id] = runtime.run(
                QueryInput(
                    query=case.question,
                    context=case.input_context,
                    trace_id=f"task7:reasoning:{case.id}",
                )
            )
        except SemanticLLMError:
            raise
        except Exception as exc:  # pragma: no cover - defensive report boundary
            results[case.id] = exc
    return results


def _build_document(
    retrieval_rows: list[dict[str, Any]],
    full_results: dict[str, EventEvidenceReasoningResult | Exception],
    client: EventOpenAIClient,
    event_config: EventRuntimeConfig,
    page_cards_reused: int,
    atlas_pages_reused: int,
) -> Task7Document:
    case_results: list[Task7CaseResult] = []
    for row in retrieval_rows:
        case = row["case"]
        result = full_results.get(case.id)
        if isinstance(result, EventEvidenceReasoningResult):
            actual = result.decision.value
            decision_match = _behavior_matches(case.expected_behavior.value, result)
            citation_valid = _citation_valid(result)
            source_titles = list(dict.fromkeys(item.title for item in result.result.evidence))
            if not source_titles and result.primary_source:
                source_titles = [result.primary_source]
            answer_or_clarification = _snippet(result.answer or result.clarifying_question)
            visual = result.visual_analysis
            visual_call_used = bool(visual and visual.primary_call_used)
            visual_verification_used = bool(visual and visual.verification_call_used)
            visual_status = _visual_status(result)
            remaining = _remaining_failure(result)
            failure = _failure_reason(result)
            modality = _modality(result)
            retry_used = result.retry_used
            material_objections = len(result.material_objections)
            scope_count = result.scope_violation_count
            released_scope = scope_count if result.decision is Decision.ANSWER else 0
            control_count = result.critical_control_omission_count
            released_control = control_count if result.decision is Decision.ANSWER else 0
            unsupported = result.unsupported_released_claims
            latency_ms = result.latency_ms
            runtime_error = None
            primary_source = result.primary_source
        else:
            actual = None
            decision_match = False
            citation_valid = False
            source_titles = []
            answer_or_clarification = None
            visual_call_used = False
            visual_verification_used = False
            visual_status = None
            remaining = type(result).__name__ if isinstance(result, Exception) else "RUNTIME_ERROR"
            failure = remaining
            modality = "none"
            retry_used = False
            material_objections = 0
            scope_count = 0
            released_scope = 0
            control_count = 0
            released_control = 0
            unsupported = 0
            latency_ms = 0.0
            runtime_error = remaining
            primary_source = None

        case_results.append(
            Task7CaseResult(
                case_id=case.id,
                expected_behavior=case.expected_behavior.value,
                actual_decision=actual,
                decision_match=decision_match,
                expected_source_title_contains=list(case.expected_source_title_contains),
                source_titles=source_titles,
                primary_source=primary_source,
                answer_or_clarification=answer_or_clarification,
                modality=modality,
                requires_image=case.requires_image,
                retry_used=retry_used,
                visual_call_used=visual_call_used,
                visual_verification_used=visual_verification_used,
                visual_status=visual_status,
                material_objection_count=material_objections,
                remaining_objection_or_failure=remaining,
                final_failure_reason=failure,
                final_citation_valid=citation_valid,
                unsupported_released_claims=unsupported,
                scope_violation_count=scope_count,
                released_answer_scope_violations=released_scope,
                critical_control_omission_count=control_count,
                released_answer_critical_control_omissions=released_control,
                deterministic_hit_rank=_source_hit_rank(
                    row["deterministic_titles"], case.expected_source_title_contains
                ),
                semantic_hit_rank=_source_hit_rank(
                    row["semantic_titles"], case.expected_source_title_contains
                ),
                atlas_hit_rank=_source_hit_rank(
                    row["atlas_titles"], case.expected_source_title_contains
                ),
                routing_count=int(actual is not None and result.route is not None)
                if isinstance(result, EventEvidenceReasoningResult)
                else 0,
                latency_ms=latency_ms,
                runtime_error=runtime_error,
            )
        )

    answer_cases = [item for item in case_results if item.actual_decision == Decision.ANSWER.value]
    valid_answers = sum(item.final_citation_valid for item in answer_cases)
    latencies = [item.latency_ms for item in case_results]
    usage = client.usage
    metrics = Task7Metrics(
        cases_executed=len(case_results),
        decision_match_count=sum(item.decision_match for item in case_results),
        answer_count=sum(item.actual_decision == Decision.ANSWER.value for item in case_results),
        clarify_count=sum(item.actual_decision == Decision.CLARIFY.value for item in case_results),
        abstain_count=sum(item.actual_decision == Decision.ABSTAIN.value for item in case_results),
        correct_clarification_count=sum(
            item.expected_behavior == Decision.CLARIFY.value
            and item.actual_decision == Decision.CLARIFY.value
            for item in case_results
        ),
        final_citation_valid_count=valid_answers,
        final_citation_validity=valid_answers / len(answer_cases) if answer_cases else 1.0,
        unsupported_released_claims=sum(item.unsupported_released_claims for item in case_results),
        scope_violation_count=sum(item.scope_violation_count for item in case_results),
        released_answer_scope_violations=sum(
            item.released_answer_scope_violations for item in case_results
        ),
        critical_control_omission_count=sum(
            item.critical_control_omission_count for item in case_results
        ),
        released_answer_critical_control_omissions=sum(
            item.released_answer_critical_control_omissions for item in case_results
        ),
        visual_case_count=sum(item.requires_image for item in case_results),
        visual_case_decision_match_count=sum(
            item.requires_image and item.decision_match for item in case_results
        ),
        verified_visual_support_count=sum(
            1 for item in case_results if item.visual_status == "VERIFIED"
        ),
        routing_count=sum(item.routing_count for item in case_results),
        retry_count=sum(item.retry_used for item in case_results),
        visual_call_count=sum(item.visual_call_used for item in case_results),
        visual_verification_call_count=sum(item.visual_verification_used for item in case_results),
        runtime_error_count=sum(item.runtime_error is not None for item in case_results),
        median_latency_ms=statistics.median(latencies) if latencies else 0.0,
        llm_calls=usage.total_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        total_llm_latency_ms=usage.latency_ms,
        hard_gates_passed=(
            len(case_results) == 17
            and all(item.runtime_error is None for item in case_results)
            and sum(item.unsupported_released_claims for item in case_results) == 0
            and (valid_answers == len(answer_cases))
            and sum(item.released_answer_scope_violations for item in case_results) == 0
            and sum(item.released_answer_critical_control_omissions for item in case_results) == 0
            and not event_config.network_enabled
            and not event_config.event_data_copy_enabled
        ),
    )
    return Task7Document(
        schema_version="1.0",
        suite="RISKON_CHALLENGE_1",
        task="TASK_7_FINAL_STABILIZATION",
        metrics=metrics,
        cases=case_results,
        fixed_policy={
            "title_router": f"{TITLE_ROUTER_MODEL}/{TITLE_ROUTER_REASONING}",
            "router_retry": f"{ROUTER_RETRY_MODEL}/{ROUTER_RETRY_REASONING}",
            "context_interpreter": f"{CONTEXT_INTERPRETER_MODEL}/{CONTEXT_INTERPRETER_REASONING}",
            "claim_builder": f"{CLAIM_BUILDER_MODEL}/{CLAIM_BUILDER_REASONING}",
            "skeptic": f"{SKEPTIC_MODEL}/{SKEPTIC_REASONING}",
            "visual_scout": f"{VISUAL_SCOUT_MODEL}/{VISUAL_SCOUT_REASONING}",
            "visual_verification": f"{VISUAL_SCOUT_MODEL}/{VISUAL_SCOUT_REASONING}",
        },
        page_cards_reused=page_cards_reused,
        atlas_pages_reused=atlas_pages_reused,
        metadata_is_not_evidence=True,
        deterministic_answer_firewall_authoritative=True,
        network_enabled=event_config.network_enabled,
        event_data_copied=event_config.event_data_copy_enabled,
    )


def _retrieval_is_strong(retrieval: SemanticRetrievalOutcome) -> bool:
    return retrieval.sufficiency.status is SufficiencyStatus.SUFFICIENT and bool(
        retrieval.selected_candidates
    )


def _atlas_candidate_key(outcome: SemanticRetrievalOutcome, limit: int) -> tuple[str, ...]:
    refs = list(outcome.hybrid_page_refs)
    refs.extend(item.source_ref for item in outcome.ranked_candidates)
    refs.extend(item.source_ref for item in outcome.deterministic_result.selected_candidates)
    return tuple(dict.fromkeys(refs))[:limit]


def _titles_for_refs(refs: Any, title_by_ref: dict[str, str]) -> list[str]:
    return [title_by_ref[ref] for ref in dict.fromkeys(refs) if ref in title_by_ref]


def _behavior_matches(expected: str, result: EventEvidenceReasoningResult) -> bool:
    if expected == Decision.ANSWER.value:
        return result.decision is Decision.ANSWER
    if expected == Decision.CLARIFY.value:
        return result.decision is Decision.CLARIFY
    return result.decision is Decision.ABSTAIN and result.route is not None


def _citation_valid(result: EventEvidenceReasoningResult) -> bool:
    if result.decision is not Decision.ANSWER:
        return True
    if not result.validated_claims or not result.evidence_refs or not result.result.evidence:
        return False
    if result.unsupported_released_claims:
        return False
    if result.scope_violation_count or result.critical_control_omission_count:
        return False
    local_refs = {unit.evidence_ref for unit in result.final_evidence_units}
    return all(
        ref in local_refs and any(ref in claim.evidence_refs for claim in result.validated_claims)
        for ref in result.evidence_refs
    )


def _failure_reason(result: EventEvidenceReasoningResult) -> str | None:
    if result.decision is Decision.ANSWER:
        return None
    if result.reason_codes:
        return ",".join(reason.value for reason in result.reason_codes)
    return "NO_RELEASED_ANSWER"


def _remaining_failure(result: EventEvidenceReasoningResult) -> str | None:
    parts = [
        *result.validation_errors[:2],
        *(item.detail for item in result.material_objections[:2]),
    ]
    if parts:
        return _snippet("; ".join(parts), 400)
    return _failure_reason(result)


def _visual_status(result: EventEvidenceReasoningResult) -> str | None:
    if any(
        unit.structured_html and unit.evidence_ref in set(result.evidence_refs)
        for unit in result.final_evidence_units
    ):
        return "STRUCTURED_HTML"
    visual = result.visual_analysis
    if visual is None:
        return "NOT_TRIGGERED"
    if visual.usable:
        return "VERIFIED"
    return visual.failure_reason or "UNVERIFIED"


def _modality(result: EventEvidenceReasoningResult) -> str:
    refs = set(result.evidence_refs)
    if not refs:
        refs = {
            support.asset_evidence_ref
            for support in (result.visual_analysis.supports if result.visual_analysis else ())
        }
    kinds = {unit.kind for unit in result.final_evidence_units if unit.evidence_ref in refs}
    if any(
        unit.structured_html and unit.evidence_ref in refs for unit in result.final_evidence_units
    ):
        return "STRUCTURED_HTML"
    labels: list[str] = []
    if kinds.intersection({"sentence", "section"}):
        labels.append("text")
    if "table_row" in kinds:
        labels.append("table")
    if "asset" in kinds:
        labels.append("image")
    return "+".join(labels) or "none"


def _snippet(value: str | None, limit: int = 800) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def write_final_reports(document: Task7Document, output_root: Path) -> dict[str, Path]:
    """Write ignored JSON, JSONL, and Markdown Task 7 diagnostics."""

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    evaluation = output_root / "evaluation.json"
    case_results = output_root / "case_results.jsonl"
    summary = output_root / "evaluation.md"
    evaluation.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
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
    return {"evaluation": evaluation, "case_results": case_results, "summary": summary}


def _summary_markdown(document: Task7Document) -> str:
    metrics = document.metrics
    lines = [
        "# Task 7 Final Stabilization Evaluation",
        "",
        "Ignored local diagnostic. Page Cards/Atlas are routing metadata, never evidence.",
        "",
        f"- Cases: {metrics.cases_executed}/17",
        f"- Decision match: {metrics.decision_match_count}/17",
        f"- ANSWER / CLARIFY / ABSTAIN: {metrics.answer_count} / "
        f"{metrics.clarify_count} / {metrics.abstain_count}",
        f"- Citation validity for released answers: {metrics.final_citation_validity:.1%}",
        f"- Unsupported released / scope / control: {metrics.unsupported_released_claims} / "
        f"{metrics.released_answer_scope_violations} / "
        f"{metrics.released_answer_critical_control_omissions}",
        f"- Visual cases decision-correct: {metrics.visual_case_decision_match_count}/"
        f"{metrics.visual_case_count}",
        f"- Routing / retry / visual calls: {metrics.routing_count} / {metrics.retry_count} / "
        f"{metrics.visual_call_count} (+{metrics.visual_verification_call_count} verification)",
        f"- LLM calls/tokens: {metrics.llm_calls} / {metrics.input_tokens} in / "
        f"{metrics.output_tokens} out",
        f"- Median latency: {metrics.median_latency_ms:.1f} ms",
        f"- Hard gates: {'PASS' if metrics.hard_gates_passed else 'HOLD'}",
        "",
        "| Case | Expected | Actual | Sources | Modality | Retry | Visual | Failure |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for case in document.cases:
        sources = ", ".join(case.source_titles[:3]) or "-"
        lines.append(
            f"| {case.case_id} | {case.expected_behavior} | {case.actual_decision or 'ERROR'} | "
            f"{_md(sources)} | {case.modality} | {'yes' if case.retry_used else 'no'} | "
            f"{_md(case.visual_status or '-')} | {_md(case.final_failure_reason or '-')} |"
        )
    return "\n".join(lines) + "\n"


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


__all__ = [
    "Task7CaseResult",
    "Task7Document",
    "Task7Metrics",
    "run_final_stabilization",
    "write_final_reports",
]
