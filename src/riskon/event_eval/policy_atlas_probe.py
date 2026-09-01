"""Task 6 Policy Atlas and answerability-graph evaluation."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riskon.config import load_milestone5b_config
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
from riskon.event_runtime.factory import (
    EventRetrievalComponents,
    build_event_retrieval_components,
)
from riskon.event_runtime.llm_client import (
    CLAIM_BUILDER_MODEL,
    CLAIM_BUILDER_REASONING,
    CONTEXT_INTERPRETER_MODEL,
    CONTEXT_INTERPRETER_REASONING,
    ELIGIBILITY_MODEL,
    ELIGIBILITY_REASONING,
    POLICY_ATLAS_MODEL,
    POLICY_ATLAS_REASONING,
    ROUTER_RETRY_MODEL,
    ROUTER_RETRY_REASONING,
    SKEPTIC_MODEL,
    SKEPTIC_REASONING,
    TITLE_ROUTER_MODEL,
    TITLE_ROUTER_REASONING,
    EventOpenAIClient,
    LLMConfigurationError,
    SemanticLLMError,
    Task6LLMConfig,
)
from riskon.event_runtime.page_cards import load_page_cards
from riskon.event_runtime.policy_atlas import (
    PolicyAtlasBuildResult,
    PolicyAtlasRouter,
    apply_atlas_retrieval,
    build_policy_atlas,
)
from riskon.event_runtime.policy_atlas_models import (
    AnswerabilityGraphDocument,
    AtlasRoutingResult,
    PolicyAtlasDocument,
)
from riskon.event_runtime.semantic_retrieval import (
    SemanticEventRetriever,
    SemanticRetrievalOutcome,
)
from riskon.event_runtime.title_router import PageCardRouter
from riskon.models import Decision, QueryInput
from riskon.routing import ExpertRouter


class Task6CaseResult(BaseModel):
    """One bounded comparison row without raw prompts or source evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    requires_image: bool = False
    visual_status: str | None = None
    expected_source_title_contains: list[str]
    deterministic_hit_rank: int | None = Field(default=None, ge=1)
    semantic_hit_rank: int | None = Field(default=None, ge=1)
    atlas_hit_rank: int | None = Field(default=None, ge=1)
    deterministic_top_titles: list[str]
    semantic_top_titles: list[str]
    atlas_top_titles: list[str]
    atlas_status_counts: dict[str, int]
    atlas_excluded_count: int = Field(ge=0)
    graph_neighbor_count: int = Field(ge=0)
    supporting_procedure_navigation: bool = False
    wrong_scope_suppressed: bool = False
    primary_source: str | None = None
    answer_or_clarification_snippet: str | None = None
    final_decision: str | None = None
    behavior_match: bool = False
    correct_clarification: bool = False
    final_citation_valid: bool = False
    final_retry_used: bool = False
    final_failure_reason: str | None = None
    material_objection_count: int = Field(ge=0)
    scope_violation_count: int = Field(ge=0)
    released_answer_scope_violations: int = Field(ge=0)
    critical_control_omission_count: int = Field(ge=0)
    released_answer_critical_control_omissions: int = Field(ge=0)
    unsupported_released_claims: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    runtime_error: str | None = None


class Task6Metrics(BaseModel):
    """Retrieval, answerability, safety, and fixed-policy accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cases_executed: int = Field(ge=0)
    deterministic_hit_at_1: int = Field(ge=0)
    deterministic_hit_at_5: int = Field(ge=0)
    deterministic_hit_at_10: int = Field(ge=0)
    semantic_hit_at_1: int = Field(ge=0)
    semantic_hit_at_5: int = Field(ge=0)
    semantic_hit_at_10: int = Field(ge=0)
    atlas_hit_at_1: int = Field(ge=0)
    atlas_hit_at_5: int = Field(ge=0)
    atlas_hit_at_10: int = Field(ge=0)
    rescued_by_semantic_case_ids: list[str]
    worsened_by_semantic_case_ids: list[str]
    rescued_by_atlas_case_ids: list[str]
    worsened_by_atlas_case_ids: list[str]
    wrong_scope_suppression_count: int = Field(ge=0)
    supporting_procedure_navigation_count: int = Field(ge=0)
    decision_match_count: int = Field(ge=0)
    answer_count: int = Field(ge=0)
    clarify_count: int = Field(ge=0)
    abstain_count: int = Field(ge=0)
    correct_clarification_count: int = Field(ge=0)
    unsupported_released_claims: int = Field(ge=0)
    released_answer_citation_valid_count: int = Field(ge=0)
    released_answer_citation_validity: float = Field(ge=0.0, le=1.0)
    scope_violation_count: int = Field(ge=0)
    released_answer_scope_violations: int = Field(ge=0)
    critical_control_omission_count: int = Field(ge=0)
    released_answer_critical_control_omissions: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    runtime_error_count: int = Field(ge=0)
    median_latency_ms: float = Field(ge=0.0)
    llm_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    total_llm_latency_ms: float = Field(ge=0.0)
    visual_capability_pending_case_ids: list[str]
    atlas_page_count: int = Field(ge=0)
    atlas_generated_count: int = Field(ge=0)
    atlas_reused_count: int = Field(ge=0)


class Task6Document(BaseModel):
    """Machine-readable Task 6 diagnostic report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    suite: str
    task: str
    metrics: Task6Metrics
    cases: list[Task6CaseResult]
    fixed_policy: dict[str, str]
    policy_atlas_path: str
    answerability_graph_path: str
    metadata_is_not_evidence: bool
    deterministic_answer_firewall_authoritative: bool
    network_enabled: bool
    event_data_copied: bool


class _ReplaySemanticRetriever:
    """Replay one in-memory retrieval observation so A-D stays comparable."""

    def __init__(
        self,
        base: SemanticEventRetriever,
        initial_by_trace: dict[str, SemanticRetrievalOutcome],
    ) -> None:
        self.base = base
        self.initial_by_trace = initial_by_trace
        # Atlas retrieval needs these deterministic helpers to apply context filtering
        # after the replayed semantic outcome has been selected.
        self.planner = base.planner
        self.deterministic_retriever = base.deterministic_retriever

    def retrieve_initial(self, request: QueryInput) -> SemanticRetrievalOutcome:
        return self.initial_by_trace[request.trace_id or ""]

    def retry_once(
        self,
        request: QueryInput,
        initial: SemanticRetrievalOutcome,
        failure_reason: Any,
    ) -> SemanticRetrievalOutcome:
        return self.base.retry_once(request, initial, failure_reason)


class _CachedAtlasRouter(PolicyAtlasRouter):
    """Reuse C's in-memory initial Atlas result when running D."""

    def __init__(
        self,
        base: PolicyAtlasRouter,
        cached: dict[tuple[str, ...], AtlasRoutingResult],
    ) -> None:
        super().__init__(base.atlas, base.graph, base.client, config=base.config)
        self.cached = cached

    def evaluate(self, *args: Any, **kwargs: Any) -> AtlasRoutingResult:
        candidate_refs = kwargs.get("candidate_refs")
        if candidate_refs is None and len(args) >= 4:
            candidate_refs = args[3]
        key = tuple(dict.fromkeys(candidate_refs or ()))[: self.config.atlas_candidate_limit]
        cached = self.cached.get(key)
        if cached is not None:
            return cached
        return super().evaluate(*args, **kwargs)


def run_policy_atlas_probe(
    runtime_config_path: Path,
    cases_path: Path,
    output_root: Path,
) -> int:
    """Build/reuse the Atlas, compare A-D, and write ignored diagnostics."""

    try:
        event_config = load_event_runtime_config(runtime_config_path)
        case_set = load_event_cases(cases_path)
        config = Task6LLMConfig()
        components = build_event_retrieval_components(event_config)
        client = EventOpenAIClient(config=config)
        atlas_build = build_policy_atlas(
            components.corpus,
            event_config,
            client,
            config=config,
        )
        cards = load_page_cards(components.corpus, event_config)
        page_router = PageCardRouter(cards.cards, client, config=config)
        semantic = SemanticEventRetriever(
            components.planner,
            components.retriever,
            page_router,
            config=config,
        )
        atlas_router = PolicyAtlasRouter(
            atlas_build.document,
            atlas_build.graph,
            client,
            config=config,
        )
        retrieval_rows, semantic_outcomes, atlas_rows = _run_retrieval_variants(
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
            atlas_build.document,
            atlas_build.graph,
            atlas_router,
            semantic_outcomes,
            atlas_rows,
        )
        document = _build_document(
            retrieval_rows,
            full_results,
            atlas_build,
            client,
            event_config,
        )
        paths = write_policy_atlas_reports(document, output_root)
    except LLMConfigurationError as exc:
        print(f"Task 6 Policy Atlas BLOCKED: {exc}")
        return 2
    except SemanticLLMError as exc:
        print(
            "Task 6 Policy Atlas BLOCKED: fixed-policy OpenAI call failed; "
            f"no model substitution was attempted ({exc})."
        )
        return 2
    except (ValueError, FileNotFoundError, OSError, TypeError) as exc:
        print(f"Task 6 Policy Atlas FAIL: {exc}")
        return 1

    metrics = document.metrics
    safety_passed = (
        metrics.cases_executed == 17
        and metrics.runtime_error_count == 0
        and metrics.unsupported_released_claims == 0
        and metrics.released_answer_citation_validity == 1.0
        and metrics.released_answer_scope_violations == 0
        and metrics.released_answer_critical_control_omissions == 0
        and not document.network_enabled
        and not document.event_data_copied
    )
    status = "PASS" if safety_passed else "HOLD"
    print(
        f"Task 6 Policy Atlas {status}: {metrics.cases_executed}/17; "
        f"A/B/C hit@5 {metrics.deterministic_hit_at_5}/17,"
        f"{metrics.semantic_hit_at_5}/17,{metrics.atlas_hit_at_5}/17; "
        f"D match {metrics.decision_match_count}/17; "
        f"ANSWER/CLARIFY/ABSTAIN {metrics.answer_count}/"
        f"{metrics.clarify_count}/{metrics.abstain_count}; "
        f"LLM calls {metrics.llm_calls}; report {paths['evaluation']}."
    )
    return 0 if safety_passed else 1


def _run_retrieval_variants(
    cases: list[Any],
    components: EventRetrievalComponents,
    semantic: SemanticEventRetriever,
    atlas_router: PolicyAtlasRouter,
) -> tuple[
    list[dict[str, Any]], dict[str, SemanticRetrievalOutcome], dict[str, AtlasRoutingResult]
]:
    title_by_ref = {section.source_ref: section.title for section in components.corpus.sections}
    rows: list[dict[str, Any]] = []
    outcomes: dict[str, SemanticRetrievalOutcome] = {}
    atlas_results: dict[str, AtlasRoutingResult] = {}
    for case in cases:
        request = QueryInput(
            query=case.question,
            context=case.input_context,
            trace_id=f"task6:retrieval:{case.id}",
        )
        plan = components.planner.plan(request)
        deterministic = components.retriever.retrieve(
            plan,
            components.planner.context_values(request, plan),
        )
        semantic_outcome = semantic.retrieve_initial(request)
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
        b_refs = set(semantic_outcome.hybrid_page_refs)
        navigation = any(
            ref not in b_refs and ref in atlas_outcome.hybrid_page_refs
            for ref in atlas_application.atlas.supporting_procedure_refs
        )
        excluded = set(atlas_application.atlas.excluded_page_refs)
        suppressed = bool(excluded.intersection(b_refs)) and bool(
            set(atlas_outcome.hybrid_page_refs) - b_refs
        )
        rows.append(
            {
                "case": case,
                "deterministic_titles": deterministic_titles,
                "semantic_titles": semantic_titles,
                "atlas_titles": atlas_titles,
                "atlas": atlas_application.atlas,
                "navigation": navigation,
                "suppressed": suppressed,
            }
        )
    return rows, outcomes, atlas_results


def _run_full_reasoning(
    cases: list[Any],
    components: EventRetrievalComponents,
    semantic: SemanticEventRetriever,
    event_config: EventRuntimeConfig,
    client: EventOpenAIClient,
    config: Task6LLMConfig,
    atlas: PolicyAtlasDocument,
    graph: AnswerabilityGraphDocument,
    atlas_router: PolicyAtlasRouter,
    semantic_outcomes: dict[str, SemanticRetrievalOutcome],
    atlas_results: dict[str, AtlasRoutingResult],
) -> dict[str, EventEvidenceReasoningResult | Exception]:
    base_config = load_milestone5b_config(event_config.pipeline_config)
    m0_config = base_config.base.base.base.base.base.base.base.base
    expert_router = ExpertRouter.from_files(
        m0_config.paths.data_root / "experts.json",
        m0_config.paths.data_root / "routing_policy.json",
    )
    initial_by_trace = {f"task6:reasoning:{case.id}": semantic_outcomes[case.id] for case in cases}
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
    )
    results: dict[str, EventEvidenceReasoningResult | Exception] = {}
    for case in cases:
        try:
            results[case.id] = runtime.run(
                QueryInput(
                    query=case.question,
                    context=case.input_context,
                    trace_id=f"task6:reasoning:{case.id}",
                )
            )
        except SemanticLLMError:
            raise
        except Exception as exc:  # pragma: no cover - defensive report boundary
            results[case.id] = exc
    return results


def _atlas_candidate_key(
    outcome: SemanticRetrievalOutcome,
    limit: int,
) -> tuple[str, ...]:
    refs = list(outcome.hybrid_page_refs)
    refs.extend(item.source_ref for item in outcome.ranked_candidates)
    refs.extend(item.source_ref for item in outcome.deterministic_result.selected_candidates)
    return tuple(dict.fromkeys(refs))[:limit]


def _titles_for_refs(refs: Any, title_by_ref: dict[str, str]) -> list[str]:
    return [title_by_ref[ref] for ref in dict.fromkeys(refs) if ref in title_by_ref]


def _build_document(
    retrieval_rows: list[dict[str, Any]],
    full_results: dict[str, EventEvidenceReasoningResult | Exception],
    atlas_build: PolicyAtlasBuildResult,
    client: EventOpenAIClient,
    event_config: EventRuntimeConfig,
) -> Task6Document:
    case_results: list[Task6CaseResult] = []
    for row in retrieval_rows:
        case = row["case"]
        result = full_results.get(case.id)
        atlas_diagnostic = row["atlas"]
        if isinstance(result, EventEvidenceReasoningResult):
            final_decision = result.decision.value
            behavior_match = _behavior_matches(case.expected_behavior.value, result)
            citation_valid = _citation_valid(result)
            failure_reason = _failure_reason(result)
            scope_count = result.scope_violation_count
            released_scope = scope_count if result.decision is Decision.ANSWER else 0
            control_count = result.critical_control_omission_count
            released_control = control_count if result.decision is Decision.ANSWER else 0
            unsupported = result.unsupported_released_claims
            retry_used = result.retry_used
            material_objections = len(result.material_objections)
            latency_ms = result.latency_ms
            runtime_error = None
            primary_source = result.primary_source
            answer_or_clarification = _snippet(result.answer or result.clarifying_question)
        else:
            final_decision = None
            behavior_match = False
            citation_valid = False
            failure_reason = (
                type(result).__name__ if isinstance(result, Exception) else "RUNTIME_ERROR"
            )
            scope_count = 0
            released_scope = 0
            control_count = 0
            released_control = 0
            unsupported = 0
            retry_used = False
            material_objections = 0
            latency_ms = 0.0
            runtime_error = (
                type(result).__name__ if isinstance(result, Exception) else "RUNTIME_ERROR"
            )
            primary_source = None
            answer_or_clarification = None

        status_counts: dict[str, int] = {}
        for decision in atlas_diagnostic.decisions:
            status = decision.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        case_results.append(
            Task6CaseResult(
                case_id=case.id,
                expected_behavior=case.expected_behavior.value,
                requires_image=case.requires_image,
                visual_status="VISUAL_CAPABILITY_PENDING" if case.requires_image else None,
                expected_source_title_contains=list(case.expected_source_title_contains),
                deterministic_hit_rank=_source_hit_rank(
                    row["deterministic_titles"], case.expected_source_title_contains
                ),
                semantic_hit_rank=_source_hit_rank(
                    row["semantic_titles"], case.expected_source_title_contains
                ),
                atlas_hit_rank=_source_hit_rank(
                    row["atlas_titles"], case.expected_source_title_contains
                ),
                deterministic_top_titles=list(row["deterministic_titles"][:10]),
                semantic_top_titles=list(row["semantic_titles"][:10]),
                atlas_top_titles=list(row["atlas_titles"][:10]),
                atlas_status_counts=status_counts,
                atlas_excluded_count=len(atlas_diagnostic.excluded_page_refs),
                graph_neighbor_count=len(atlas_diagnostic.graph_neighbor_refs),
                supporting_procedure_navigation=bool(row["navigation"]),
                wrong_scope_suppressed=bool(row["suppressed"]),
                primary_source=primary_source,
                answer_or_clarification_snippet=answer_or_clarification,
                final_decision=final_decision,
                behavior_match=behavior_match,
                correct_clarification=(
                    case.expected_behavior.value == "CLARIFY"
                    and final_decision == Decision.CLARIFY.value
                ),
                final_citation_valid=citation_valid,
                final_retry_used=retry_used,
                final_failure_reason=failure_reason,
                material_objection_count=material_objections,
                scope_violation_count=scope_count,
                released_answer_scope_violations=released_scope,
                critical_control_omission_count=control_count,
                released_answer_critical_control_omissions=released_control,
                unsupported_released_claims=unsupported,
                latency_ms=latency_ms,
                runtime_error=runtime_error,
            )
        )

    answer_cases = [item for item in case_results if item.final_decision == Decision.ANSWER.value]
    valid_answers = sum(item.final_citation_valid for item in answer_cases)
    answer_validity = valid_answers / len(answer_cases) if answer_cases else 1.0
    latencies = [item.latency_ms for item in case_results]
    usage = client.usage
    metrics = Task6Metrics(
        cases_executed=len(case_results),
        deterministic_hit_at_1=_count_hit(case_results, "deterministic_hit_rank", 1),
        deterministic_hit_at_5=_count_hit(case_results, "deterministic_hit_rank", 5),
        deterministic_hit_at_10=_count_hit(case_results, "deterministic_hit_rank", 10),
        semantic_hit_at_1=_count_hit(case_results, "semantic_hit_rank", 1),
        semantic_hit_at_5=_count_hit(case_results, "semantic_hit_rank", 5),
        semantic_hit_at_10=_count_hit(case_results, "semantic_hit_rank", 10),
        atlas_hit_at_1=_count_hit(case_results, "atlas_hit_rank", 1),
        atlas_hit_at_5=_count_hit(case_results, "atlas_hit_rank", 5),
        atlas_hit_at_10=_count_hit(case_results, "atlas_hit_rank", 10),
        rescued_by_semantic_case_ids=[
            item.case_id
            for item in case_results
            if not _hit(item.deterministic_hit_rank, 10) and _hit(item.semantic_hit_rank, 10)
        ],
        worsened_by_semantic_case_ids=[
            item.case_id
            for item in case_results
            if _hit(item.deterministic_hit_rank, 10) and not _hit(item.semantic_hit_rank, 10)
        ],
        rescued_by_atlas_case_ids=[
            item.case_id
            for item in case_results
            if not _hit(item.semantic_hit_rank, 10) and _hit(item.atlas_hit_rank, 10)
        ],
        worsened_by_atlas_case_ids=[
            item.case_id
            for item in case_results
            if _hit(item.semantic_hit_rank, 10) and not _hit(item.atlas_hit_rank, 10)
        ],
        wrong_scope_suppression_count=sum(item.wrong_scope_suppressed for item in case_results),
        supporting_procedure_navigation_count=sum(
            item.supporting_procedure_navigation for item in case_results
        ),
        decision_match_count=sum(item.behavior_match for item in case_results),
        answer_count=sum(item.final_decision == Decision.ANSWER.value for item in case_results),
        clarify_count=sum(item.final_decision == Decision.CLARIFY.value for item in case_results),
        abstain_count=sum(item.final_decision == Decision.ABSTAIN.value for item in case_results),
        correct_clarification_count=sum(item.correct_clarification for item in case_results),
        unsupported_released_claims=sum(item.unsupported_released_claims for item in case_results),
        released_answer_citation_valid_count=valid_answers,
        released_answer_citation_validity=answer_validity,
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
        retry_count=sum(item.final_retry_used for item in case_results),
        runtime_error_count=sum(item.runtime_error is not None for item in case_results),
        median_latency_ms=statistics.median(latencies) if latencies else 0.0,
        llm_calls=usage.total_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        total_llm_latency_ms=usage.latency_ms,
        visual_capability_pending_case_ids=[
            item.case_id for item in case_results if item.requires_image
        ],
        atlas_page_count=len(atlas_build.document.fingerprints),
        atlas_generated_count=atlas_build.generated_count,
        atlas_reused_count=atlas_build.reused_count,
    )
    return Task6Document(
        schema_version="1.0",
        suite="RISKON_CHALLENGE_1",
        task="TASK_6_POLICY_ATLAS",
        metrics=metrics,
        cases=case_results,
        fixed_policy={
            "policy_atlas": f"{POLICY_ATLAS_MODEL}/{POLICY_ATLAS_REASONING}",
            "eligibility": f"{ELIGIBILITY_MODEL}/{ELIGIBILITY_REASONING}",
            "title_router": f"{TITLE_ROUTER_MODEL}/{TITLE_ROUTER_REASONING}",
            "router_retry": f"{ROUTER_RETRY_MODEL}/{ROUTER_RETRY_REASONING}",
            "context_interpreter": f"{CONTEXT_INTERPRETER_MODEL}/{CONTEXT_INTERPRETER_REASONING}",
            "claim_builder": f"{CLAIM_BUILDER_MODEL}/{CLAIM_BUILDER_REASONING}",
            "skeptic": f"{SKEPTIC_MODEL}/{SKEPTIC_REASONING}",
        },
        policy_atlas_path=str(atlas_build.path),
        answerability_graph_path=str(atlas_build.graph_path),
        metadata_is_not_evidence=True,
        deterministic_answer_firewall_authoritative=True,
        network_enabled=event_config.network_enabled,
        event_data_copied=event_config.event_data_copy_enabled,
    )


def _count_hit(cases: list[Task6CaseResult], field: str, cutoff: int) -> int:
    return sum(_hit(getattr(case, field), cutoff) for case in cases)


def _hit(rank: int | None, cutoff: int) -> bool:
    return rank is not None and rank <= cutoff


def _behavior_matches(expected: str, result: EventEvidenceReasoningResult) -> bool:
    if expected == "ANSWER":
        return result.decision is Decision.ANSWER
    if expected == "CLARIFY":
        return result.decision is Decision.CLARIFY
    return result.decision is Decision.ABSTAIN and result.route is not None


def _citation_valid(result: EventEvidenceReasoningResult) -> bool:
    if result.decision is not Decision.ANSWER:
        return True
    if not result.validated_claims or not result.evidence_refs or not result.result.evidence:
        return False
    if result.unsupported_released_claims or result.scope_violation_count:
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
    return "NO_RELEASED_ANSWER"


def _snippet(value: str | None, limit: int = 800) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def write_policy_atlas_reports(document: Task6Document, output_root: Path) -> dict[str, Path]:
    """Write ignored bounded Task 6 reports."""

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


def _summary_markdown(document: Task6Document) -> str:
    metrics = document.metrics
    lines = [
        "# Task 6 Policy Atlas Evaluation",
        "",
        "Ignored local diagnostic; Atlas/graph metadata is not evidence.",
        "",
        f"- Cases: {metrics.cases_executed}/17",
        f"- A/B/C hit@1: {metrics.deterministic_hit_at_1}/"
        f"{metrics.semantic_hit_at_1}/{metrics.atlas_hit_at_1}",
        f"- A/B/C hit@5: {metrics.deterministic_hit_at_5}/"
        f"{metrics.semantic_hit_at_5}/{metrics.atlas_hit_at_5}",
        f"- A/B/C hit@10: {metrics.deterministic_hit_at_10}/"
        f"{metrics.semantic_hit_at_10}/{metrics.atlas_hit_at_10}",
        f"- D decision match: {metrics.decision_match_count}/17",
        f"- D ANSWER / CLARIFY / ABSTAIN: {metrics.answer_count} / "
        f"{metrics.clarify_count} / {metrics.abstain_count}",
        f"- Released citation validity: {metrics.released_answer_citation_valid_count}/"
        f"{metrics.answer_count} ({metrics.released_answer_citation_validity:.3f})",
        f"- Released unsupported/scope/control: {metrics.unsupported_released_claims}/"
        f"{metrics.released_answer_scope_violations}/"
        f"{metrics.released_answer_critical_control_omissions}",
        "",
        "| Case | Expected | Decision | A rank | B rank | C rank | Retry | Visual |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for case in document.cases:
        lines.append(
            f"| {case.case_id} | {case.expected_behavior} | {case.final_decision or 'ERROR'} | "
            f"{case.deterministic_hit_rank or '-'} | {case.semantic_hit_rank or '-'} | "
            f"{case.atlas_hit_rank or '-'} | {'yes' if case.final_retry_used else 'no'} | "
            f"{case.visual_status or '-'} |"
        )
    lines.extend(
        [
            "",
            "The deterministic Answer Firewall remains authoritative. Visual-dependent cases are "
            "labeled VISUAL_CAPABILITY_PENDING and are not treated as Atlas failures.",
        ]
    )
    return "\n".join(lines) + "\n"


__all__ = [
    "Task6CaseResult",
    "Task6Document",
    "Task6Metrics",
    "run_policy_atlas_probe",
    "write_policy_atlas_reports",
]
