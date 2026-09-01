"""17-case deterministic-versus-LLM-assisted retrieval evaluation."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_eval.retrieval_probe import (
    _ranked_candidates,
    _source_hit_rank,
    _unique_documents,
)
from riskon.event_eval.runner import load_event_cases
from riskon.event_runtime.config import EventRuntimeConfig, load_event_runtime_config
from riskon.event_runtime.factory import (
    EventRetrievalComponents,
    build_event_retrieval_components,
)
from riskon.event_runtime.llm_client import (
    PAGE_CARD_MODEL,
    PAGE_CARD_REASONING,
    ROUTER_RETRY_MODEL,
    ROUTER_RETRY_REASONING,
    TITLE_ROUTER_MODEL,
    TITLE_ROUTER_REASONING,
    EventOpenAIClient,
    LLMConfigurationError,
    SemanticLLMError,
    Task4LLMConfig,
)
from riskon.event_runtime.page_cards import PageCardBuildResult, build_page_cards
from riskon.event_runtime.semantic_models import PageCard
from riskon.event_runtime.semantic_retrieval import SemanticEventRetriever
from riskon.event_runtime.title_router import PageCardRouter, RouterResult
from riskon.models import QueryInput


class HybridRouteSelection(BaseModel):
    """Safe routing diagnostic without page content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_ref: str = Field(min_length=1)
    rank: int = Field(ge=1, le=10)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=160)


class HybridProbeCase(BaseModel):
    """One bounded deterministic-versus-hybrid retrieval comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    expected_source_title_contains: list[str]
    deterministic_top_page_titles: list[str]
    hybrid_top_page_titles: list[str]
    deterministic_source_hit_rank: int | None = Field(default=None, ge=1)
    hybrid_source_hit_rank: int | None = Field(default=None, ge=1)
    deterministic_candidate_count: int = Field(ge=0)
    hybrid_selected_page_count: int = Field(ge=0, le=10)
    hybrid_selected_section_count: int = Field(ge=0)
    retry_count: int = Field(ge=0, le=1)
    sufficiency_status: str = Field(min_length=1)
    sufficiency_reason: str | None = None
    initial_route: list[HybridRouteSelection]
    retry_route: list[HybridRouteSelection]
    latency_ms: float = Field(ge=0.0)
    runtime_error: str | None = None


class HybridProbeMetrics(BaseModel):
    """Required retrieval metrics plus bounded LLM accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cases_executed: int = Field(ge=0)
    deterministic_hit_at_1: int = Field(ge=0)
    deterministic_hit_at_5: int = Field(ge=0)
    deterministic_hit_at_10: int = Field(ge=0)
    hybrid_hit_at_1: int = Field(ge=0)
    hybrid_hit_at_5: int = Field(ge=0)
    hybrid_hit_at_10: int = Field(ge=0)
    improved_case_ids: list[str]
    worsened_case_ids: list[str]
    retry_usage_count: int = Field(ge=0)
    runtime_error_count: int = Field(ge=0)
    median_query_latency_ms: float = Field(ge=0.0)
    mean_query_latency_ms: float = Field(ge=0.0)
    page_card_count: int = Field(ge=0)
    page_card_generated_count: int = Field(ge=0)
    page_card_reused_count: int = Field(ge=0)
    page_card_latency_ms: float = Field(ge=0.0)
    page_card_calls: int = Field(ge=0)
    title_router_calls: int = Field(ge=0)
    router_retry_calls: int = Field(ge=0)
    total_llm_calls: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    total_llm_latency_ms: float = Field(ge=0.0)


class HybridProbeDocument(BaseModel):
    """Machine-readable Task 4 retrieval report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    suite: str
    metrics: HybridProbeMetrics
    cases: list[HybridProbeCase]
    fixed_policy: dict[str, str]
    page_card_cache_path: str
    semantic_metadata_is_not_evidence: bool
    deterministic_firewall_remains_authoritative: bool
    network_enabled: bool
    event_data_copied: bool


def run_hybrid_retrieval_probe(
    runtime_config_path: Path,
    cases_path: Path,
    output_root: Path,
) -> int:
    """Run the bounded Page Card/router path and write comparison artifacts."""

    try:
        event_config = load_event_runtime_config(runtime_config_path)
        case_set = load_event_cases(cases_path)
        components = build_event_retrieval_components(event_config)
        llm_config = Task4LLMConfig()
        llm_client = EventOpenAIClient(config=llm_config)
        cards = build_page_cards(
            components.corpus,
            event_config,
            llm_client,
            config=llm_config,
        )
        router = PageCardRouter(cards.document.cards, llm_client, config=llm_config)
        retriever = SemanticEventRetriever(
            components.planner,
            components.retriever,
            router,
            config=llm_config,
        )
        results = [_run_case(case, retriever, components) for case in case_set.cases]
        document = _build_document(
            results,
            cards,
            llm_client,
            event_config,
        )
        paths = write_hybrid_probe_reports(document, output_root)
    except LLMConfigurationError as exc:
        print(f"Task 4 retrieval BLOCKED: {exc}")
        return 2
    except SemanticLLMError as exc:
        print(
            "Task 4 retrieval BLOCKED: fixed-policy OpenAI call failed; "
            f"no model substitution was attempted ({exc})."
        )
        return 2
    except (ValueError, FileNotFoundError, OSError, TypeError) as exc:
        print(f"Task 4 retrieval FAIL: {exc}")
        return 1

    metrics = document.metrics
    total = metrics.cases_executed
    passed = (
        total == 17
        and metrics.runtime_error_count == 0
        and metrics.hybrid_hit_at_5 >= 15
        and metrics.hybrid_hit_at_10 == total
        and all(case.hybrid_selected_page_count <= 10 for case in document.cases)
    )
    status = "PASS" if passed else "HOLD"
    print(
        f"Task 4 hybrid retrieval {status}: {total}/17; "
        f"deterministic hit@1/5/10 "
        f"{metrics.deterministic_hit_at_1}/{total},"
        f"{metrics.deterministic_hit_at_5}/{total},"
        f"{metrics.deterministic_hit_at_10}/{total}; "
        f"hybrid hit@1/5/10 "
        f"{metrics.hybrid_hit_at_1}/{total},"
        f"{metrics.hybrid_hit_at_5}/{total},"
        f"{metrics.hybrid_hit_at_10}/{total}; "
        f"retries {metrics.retry_usage_count}; "
        f"LLM calls {metrics.total_llm_calls}; report {paths['evaluation']}."
    )
    return 0 if passed else 1


def _run_case(
    case: Any,
    retriever: SemanticEventRetriever,
    components: EventRetrievalComponents,
) -> HybridProbeCase:
    try:
        outcome = retriever.retrieve(
            QueryInput(
                query=case.question,
                context=case.input_context,
                trace_id=f"event-hybrid-retrieval:{case.id}",
            )
        )
    except SemanticLLMError:
        raise
    except Exception as exc:  # pragma: no cover - defensive report boundary
        return HybridProbeCase(
            case_id=case.id,
            query=case.question,
            expected_source_title_contains=list(case.expected_source_title_contains),
            deterministic_top_page_titles=[],
            hybrid_top_page_titles=[],
            deterministic_candidate_count=0,
            hybrid_selected_page_count=0,
            hybrid_selected_section_count=0,
            retry_count=0,
            sufficiency_status="ERROR",
            sufficiency_reason=None,
            initial_route=[],
            retry_route=[],
            latency_ms=0.0,
            runtime_error=type(exc).__name__,
        )

    deterministic_ranked = _ranked_candidates(
        outcome.deterministic_result,
        components.retriever,
    )
    deterministic_documents = _unique_documents(deterministic_ranked)
    deterministic_titles = [item.title for item in deterministic_documents]
    cards_by_ref = {card.source_ref: card for card in retriever.router.cards}
    candidate_title_by_source = _candidate_title_by_source(components)
    hybrid_titles = [
        _title_for_ref(source_ref, cards_by_ref, candidate_title_by_source)
        for source_ref in outcome.hybrid_page_refs
    ]
    selected_sections = len(
        {
            candidate.section_id
            for candidate in outcome.selected_candidates
            if candidate.section_id is not None
        }
    )
    return HybridProbeCase(
        case_id=case.id,
        query=case.question,
        expected_source_title_contains=list(case.expected_source_title_contains),
        deterministic_top_page_titles=deterministic_titles[:20],
        hybrid_top_page_titles=hybrid_titles[:10],
        deterministic_source_hit_rank=_source_hit_rank(
            deterministic_titles,
            case.expected_source_title_contains,
        ),
        hybrid_source_hit_rank=_source_hit_rank(
            hybrid_titles,
            case.expected_source_title_contains,
        ),
        deterministic_candidate_count=len(deterministic_ranked),
        hybrid_selected_page_count=len(outcome.hybrid_page_refs),
        hybrid_selected_section_count=selected_sections,
        retry_count=outcome.retry_count,
        sufficiency_status=outcome.sufficiency.status.value,
        sufficiency_reason=outcome.sufficiency.reason.value
        if outcome.sufficiency.reason is not None
        else None,
        initial_route=_route_selections(outcome.initial_router),
        retry_route=_route_selections(outcome.retry_router),
        latency_ms=outcome.latency_ms,
    )


def _build_document(
    results: list[HybridProbeCase],
    cards: PageCardBuildResult,
    llm_client: EventOpenAIClient,
    event_config: EventRuntimeConfig,
) -> HybridProbeDocument:
    usage = llm_client.usage
    latencies = [case.latency_ms for case in results]
    metrics = HybridProbeMetrics(
        cases_executed=len(results),
        deterministic_hit_at_1=_count_hit(results, "deterministic_source_hit_rank", 1),
        deterministic_hit_at_5=_count_hit(results, "deterministic_source_hit_rank", 5),
        deterministic_hit_at_10=_count_hit(results, "deterministic_source_hit_rank", 10),
        hybrid_hit_at_1=_count_hit(results, "hybrid_source_hit_rank", 1),
        hybrid_hit_at_5=_count_hit(results, "hybrid_source_hit_rank", 5),
        hybrid_hit_at_10=_count_hit(results, "hybrid_source_hit_rank", 10),
        improved_case_ids=[case.case_id for case in results if _improved(case)],
        worsened_case_ids=[case.case_id for case in results if _worsened(case)],
        retry_usage_count=sum(case.retry_count for case in results),
        runtime_error_count=sum(case.runtime_error is not None for case in results),
        median_query_latency_ms=statistics.median(latencies) if latencies else 0.0,
        mean_query_latency_ms=statistics.mean(latencies) if latencies else 0.0,
        page_card_count=len(cards.document.cards),
        page_card_generated_count=cards.generated_count,
        page_card_reused_count=cards.reused_count,
        page_card_latency_ms=cards.latency_ms,
        page_card_calls=usage.page_card_calls,
        title_router_calls=usage.title_router_calls,
        router_retry_calls=usage.router_retry_calls,
        total_llm_calls=usage.total_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        total_llm_latency_ms=usage.latency_ms,
    )
    return HybridProbeDocument(
        schema_version="1.0",
        suite="RISKON_CHALLENGE_1",
        metrics=metrics,
        cases=results,
        fixed_policy={
            "page_card_model": PAGE_CARD_MODEL,
            "page_card_reasoning": PAGE_CARD_REASONING,
            "title_router_model": TITLE_ROUTER_MODEL,
            "title_router_reasoning": TITLE_ROUTER_REASONING,
            "router_retry_model": ROUTER_RETRY_MODEL,
            "router_retry_reasoning": ROUTER_RETRY_REASONING,
        },
        page_card_cache_path=str(cards.path),
        semantic_metadata_is_not_evidence=True,
        deterministic_firewall_remains_authoritative=True,
        network_enabled=event_config.network_enabled,
        event_data_copied=event_config.event_data_copy_enabled,
    )


def write_hybrid_probe_reports(
    document: HybridProbeDocument,
    output_root: Path,
) -> dict[str, Path]:
    """Write bounded JSON, JSONL, and Markdown comparison reports."""

    root = output_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    evaluation = root / "evaluation.json"
    case_results = root / "case_results.jsonl"
    summary = root / "evaluation.md"
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
    return {"evaluation": evaluation, "case_results": case_results, "summary": summary}


def _candidate_title_by_source(components: EventRetrievalComponents) -> dict[str, str]:
    result: dict[str, str] = {}
    for candidate in components.retriever.candidates:
        result.setdefault(candidate.source_ref, candidate.title)
    return result


def _title_for_ref(
    source_ref: str,
    cards_by_ref: dict[str, PageCard],
    candidate_title_by_source: dict[str, str],
) -> str:
    card = cards_by_ref.get(source_ref)
    if card is not None:
        return card.title
    return candidate_title_by_source.get(source_ref, source_ref)


def _route_selections(router: RouterResult | None) -> list[HybridRouteSelection]:
    if router is None:
        return []
    return [
        HybridRouteSelection(
            page_ref=item.page_ref,
            rank=item.rank,
            confidence=item.confidence,
            reason=item.reason,
        )
        for item in router.selections
    ]


def _count_hit(results: list[HybridProbeCase], field: str, cutoff: int) -> int:
    return sum(
        getattr(item, field) is not None and getattr(item, field) <= cutoff for item in results
    )


def _improved(case: HybridProbeCase) -> bool:
    deterministic = case.deterministic_source_hit_rank
    hybrid = case.hybrid_source_hit_rank
    return hybrid is not None and (deterministic is None or hybrid < deterministic)


def _worsened(case: HybridProbeCase) -> bool:
    deterministic = case.deterministic_source_hit_rank
    hybrid = case.hybrid_source_hit_rank
    return deterministic is not None and (hybrid is None or hybrid > deterministic)


def _summary_markdown(document: HybridProbeDocument) -> str:
    metrics = document.metrics
    lines = [
        "# RiskON Task 4 hybrid retrieval probe",
        "",
        "This report evaluates retrieval only. Page Cards and router output are routing "
        "metadata, never answer evidence; the deterministic Answer Firewall remains authoritative.",
        "",
        "## Fixed policy",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in document.fixed_policy.items())
    lines.extend(
        [
            "",
            "## Metrics",
            "",
            f"- Cases executed: {metrics.cases_executed}/17",
            "- Deterministic hit@1/@5/@10: "
            f"{metrics.deterministic_hit_at_1}/{metrics.deterministic_hit_at_5}/"
            f"{metrics.deterministic_hit_at_10}",
            "- Hybrid hit@1/@5/@10: "
            f"{metrics.hybrid_hit_at_1}/{metrics.hybrid_hit_at_5}/"
            f"{metrics.hybrid_hit_at_10}",
            f"- Improved cases: {', '.join(metrics.improved_case_ids) or 'none'}",
            f"- Worsened cases: {', '.join(metrics.worsened_case_ids) or 'none'}",
            f"- Retry usage: {metrics.retry_usage_count}",
            f"- Runtime errors: {metrics.runtime_error_count}",
            "- Query latency median/mean: "
            f"{metrics.median_query_latency_ms:.1f}/{metrics.mean_query_latency_ms:.1f} ms",
            "- Page Cards: "
            f"{metrics.page_card_count} total; {metrics.page_card_generated_count} generated; "
            f"{metrics.page_card_reused_count} reused",
            "- LLM calls: "
            f"{metrics.total_llm_calls} total; page cards {metrics.page_card_calls}; "
            f"initial routers {metrics.title_router_calls}; retries {metrics.router_retry_calls}",
            "- Tokens input/output/cached: "
            f"{metrics.input_tokens}/{metrics.output_tokens}/{metrics.cached_input_tokens}",
            f"- LLM latency total: {metrics.total_llm_latency_ms:.1f} ms",
            f"- Network enabled in deterministic event config: {document.network_enabled}",
            f"- Event data copied: {document.event_data_copied}",
            "",
            "## Cases outside hybrid hit@5",
            "",
            "| Case | Deterministic rank | Hybrid rank | Expected title(s) | Hybrid top 5 |",
            "|---|---:|---:|---|---|",
        ]
    )
    failed = [
        item
        for item in document.cases
        if item.expected_source_title_contains
        and (item.hybrid_source_hit_rank is None or item.hybrid_source_hit_rank > 5)
    ]
    for item in failed:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.case_id,
                    str(item.deterministic_source_hit_rank or "not found"),
                    str(item.hybrid_source_hit_rank or "not found"),
                    "; ".join(item.expected_source_title_contains),
                    "; ".join(item.hybrid_top_page_titles[:5]) or "(none)",
                ]
            )
            + "|"
        )
    if not failed:
        lines.append("| — | — | — | none | all expected titles found |")
    lines.extend(
        [
            "",
            "The Golden Map was read-only and unchanged. No Claim Builder or Skeptic was run.",
            "",
        ]
    )
    return "\n".join(lines)
