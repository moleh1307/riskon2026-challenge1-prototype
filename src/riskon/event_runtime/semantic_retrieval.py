"""Hybrid deterministic-plus-semantic retrieval for Task 4."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from riskon.event_runtime.llm_client import Task4LLMConfig
from riskon.event_runtime.retrieval import EventHybridRetriever
from riskon.event_runtime.semantic_models import (
    EvidenceSufficiency,
    SemanticFailureReason,
    SufficiencyStatus,
)
from riskon.event_runtime.title_router import PageCardRouter, RouterResult
from riskon.hybrid_retrieval import HybridRetrievalResult, RetrievalCandidate
from riskon.models import QueryInput, QueryPlan


class EventPlanner(Protocol):
    """Planner surface needed by the semantic retrieval adapter."""

    def plan(self, request: QueryInput) -> QueryPlan:
        """Build a deterministic query plan."""

    def context_values(self, request: QueryInput, plan: QueryPlan) -> dict[str, str]:
        """Return normalized context for deterministic filtering."""


@dataclass(frozen=True)
class SemanticRetrievalOutcome:
    """Safe retrieval output; all candidate evidence remains source-derived."""

    plan: QueryPlan
    deterministic_result: HybridRetrievalResult
    ranked_candidates: tuple[RetrievalCandidate, ...]
    selected_candidates: tuple[RetrievalCandidate, ...]
    deterministic_page_refs: tuple[str, ...]
    hybrid_page_refs: tuple[str, ...]
    initial_router: RouterResult
    retry_router: RouterResult | None
    sufficiency: EvidenceSufficiency
    retry_count: int
    latency_ms: float


@dataclass(frozen=True)
class _PageScore:
    source_ref: str
    deterministic_rank: int | None
    deterministic_score: float
    router_score: float
    total_score: float


class SemanticEventRetriever:
    """Add bounded title routing while leaving deterministic retrieval authoritative."""

    def __init__(
        self,
        planner: EventPlanner,
        deterministic_retriever: EventHybridRetriever,
        router: PageCardRouter,
        *,
        config: Task4LLMConfig | None = None,
    ) -> None:
        self.planner = planner
        self.deterministic_retriever = deterministic_retriever
        self.router = router
        self.config = config or Task4LLMConfig()

    def retrieve(self, request: QueryInput) -> SemanticRetrievalOutcome:
        """Run deterministic retrieval, one initial route, and at most one retry."""

        initial = self.retrieve_initial(request)
        if (
            initial.sufficiency.status is SufficiencyStatus.RETRY
            and initial.sufficiency.reason is not None
        ):
            return self.retry_once(request, initial, initial.sufficiency.reason)
        return initial

    def retrieve_initial(self, request: QueryInput) -> SemanticRetrievalOutcome:
        """Run deterministic retrieval and the initial title route without retrying."""

        started = time.perf_counter()
        plan = self.planner.plan(request)
        context = self.planner.context_values(request, plan)
        deterministic_result = self.deterministic_retriever.retrieve(plan, context)
        deterministic_scores, deterministic_page_refs = _deterministic_page_scores(
            deterministic_result,
            self.deterministic_retriever,
        )
        initial_router = self.router.route(request, plan, deterministic_page_refs)
        routes = [initial_router]
        page_scores = _merge_page_scores(deterministic_scores, routes)
        hybrid_page_refs = tuple(
            item.source_ref for item in page_scores[: self.config.max_selected_pages]
        )
        ranked_candidates, selected_candidates, raw_candidates = self._retrieve_sections(
            request,
            plan,
            context,
            hybrid_page_refs,
            deterministic_result,
        )
        sufficiency = self._check_sufficiency(
            request,
            plan,
            hybrid_page_refs,
            ranked_candidates,
            selected_candidates,
            raw_candidates,
        )

        return SemanticRetrievalOutcome(
            plan=plan,
            deterministic_result=deterministic_result,
            ranked_candidates=tuple(ranked_candidates),
            selected_candidates=tuple(selected_candidates),
            deterministic_page_refs=tuple(deterministic_page_refs),
            hybrid_page_refs=hybrid_page_refs,
            initial_router=initial_router,
            retry_router=None,
            sufficiency=sufficiency,
            retry_count=0,
            latency_ms=_elapsed_ms(started),
        )

    def retry_once(
        self,
        request: QueryInput,
        initial: SemanticRetrievalOutcome,
        failure_reason: SemanticFailureReason,
    ) -> SemanticRetrievalOutcome:
        """Run exactly one alternative-page route and rebuild section candidates."""

        started = time.perf_counter()
        retry_router = self.router.route(
            request,
            initial.plan,
            initial.deterministic_page_refs,
            previous_attempted_refs=tuple(
                dict.fromkeys(
                    [
                        *initial.hybrid_page_refs,
                        *initial.initial_router.attempted_page_refs,
                    ]
                )
            ),
            failure_reason=failure_reason,
        )
        routes = [initial.initial_router, retry_router]
        deterministic_scores, _deterministic_page_refs = _deterministic_page_scores(
            initial.deterministic_result,
            self.deterministic_retriever,
        )
        page_scores = _merge_page_scores(deterministic_scores, routes)
        hybrid_page_refs = tuple(
            item.source_ref for item in page_scores[: self.config.max_selected_pages]
        )
        context = self.planner.context_values(request, initial.plan)
        ranked_candidates, selected_candidates, raw_candidates = self._retrieve_sections(
            request,
            initial.plan,
            context,
            hybrid_page_refs,
            initial.deterministic_result,
        )
        sufficiency = self._check_sufficiency(
            request,
            initial.plan,
            hybrid_page_refs,
            ranked_candidates,
            selected_candidates,
            raw_candidates,
        )
        return SemanticRetrievalOutcome(
            plan=initial.plan,
            deterministic_result=initial.deterministic_result,
            ranked_candidates=tuple(ranked_candidates),
            selected_candidates=tuple(selected_candidates),
            deterministic_page_refs=initial.deterministic_page_refs,
            hybrid_page_refs=hybrid_page_refs,
            initial_router=initial.initial_router,
            retry_router=retry_router,
            sufficiency=sufficiency,
            retry_count=1,
            latency_ms=round(initial.latency_ms + _elapsed_ms(started), 3),
        )

    def _retrieve_sections(
        self,
        request: QueryInput,
        plan: QueryPlan,
        context: dict[str, str],
        page_refs: Sequence[str],
        deterministic_result: HybridRetrievalResult,
    ) -> tuple[
        list[RetrievalCandidate],
        list[RetrievalCandidate],
        list[RetrievalCandidate],
    ]:
        page_set = set(page_refs)
        all_page_candidates = [
            candidate
            for candidate in self.deterministic_retriever.candidates
            if candidate.source_ref in page_set
        ]
        raw_candidates = list(all_page_candidates)
        eligible = [
            candidate
            for candidate in all_page_candidates
            if not self.deterministic_retriever._context_conflict(
                candidate,
                plan,
                context,
                plan.normalised_query,
            )
        ]
        deterministic_scores = _candidate_deterministic_scores(deterministic_result)
        query_terms = _query_terms(request, plan)
        scored: list[tuple[float, str, RetrievalCandidate]] = []
        for candidate in eligible:
            direct_score = _candidate_support_score(candidate, query_terms, request.query)
            score = direct_score + 100.0 * deterministic_scores.get(candidate.candidate_ref, 0.0)
            scored.append((score, candidate.candidate_ref, candidate))
        scored.sort(key=lambda item: (-item[0], item[1]))
        limit = max(20, self.deterministic_retriever.config.top_k)
        ranked = [candidate for _score, _ref, candidate in scored[:limit]]
        selected = ranked[: self.deterministic_retriever.config.top_k]
        return ranked, selected, raw_candidates

    def _check_sufficiency(
        self,
        request: QueryInput,
        plan: QueryPlan,
        page_refs: Sequence[str],
        ranked_candidates: Sequence[RetrievalCandidate],
        selected_candidates: Sequence[RetrievalCandidate],
        raw_candidates: Sequence[RetrievalCandidate],
    ) -> EvidenceSufficiency:
        if not raw_candidates:
            return EvidenceSufficiency(
                status=SufficiencyStatus.RETRY,
                reason=SemanticFailureReason.NO_DIRECT_SUPPORT,
                detail="Selected pages yielded no source sections or table rows.",
            )
        if not ranked_candidates:
            return EvidenceSufficiency(
                status=SufficiencyStatus.RETRY,
                reason=SemanticFailureReason.WRONG_SCOPE,
                detail="Selected pages were excluded by deterministic context checks.",
            )
        query_terms = _query_terms(request, plan)
        direct_support = max(
            (
                _candidate_support_score(candidate, query_terms, request.query)
                for candidate in selected_candidates
            ),
            default=0.0,
        )
        if direct_support > 0.0:
            return EvidenceSufficiency(
                status=SufficiencyStatus.SUFFICIENT,
                detail="Selected source sections contain deterministic query support.",
            )
        metadata_support = _metadata_support(page_refs, self.router.cards, query_terms)
        reason = (
            SemanticFailureReason.NO_DIRECT_SUPPORT
            if metadata_support
            else SemanticFailureReason.WRONG_PAGE
        )
        return EvidenceSufficiency(
            status=SufficiencyStatus.RETRY,
            reason=reason,
            detail="Selected page metadata did not yield direct deterministic section support.",
        )


def _deterministic_page_scores(
    result: HybridRetrievalResult,
    retriever: EventHybridRetriever,
) -> tuple[dict[str, tuple[int, float]], list[str]]:
    by_candidate: dict[str, float] = defaultdict(float)
    for entry in result.diagnostics.entries:
        by_candidate[entry.candidate_ref] += float(entry.rrf_contribution)
    source_scores: dict[str, float] = defaultdict(float)
    for candidate_ref, score in by_candidate.items():
        candidate = retriever._candidate_by_ref.get(candidate_ref)
        if candidate is not None:
            source_scores[candidate.source_ref] = max(source_scores[candidate.source_ref], score)
    ordered = sorted(source_scores, key=lambda source: (-source_scores[source], source))
    ranked = ordered[:20]
    return (
        {source: (rank, source_scores[source]) for rank, source in enumerate(ranked, start=1)},
        ranked,
    )


def _merge_page_scores(
    deterministic_scores: dict[str, tuple[int, float]],
    routes: Sequence[RouterResult],
) -> list[_PageScore]:
    scores: dict[str, _PageScore] = {}
    for source_ref, (rank, score) in deterministic_scores.items():
        scores[source_ref] = _PageScore(
            source_ref=source_ref,
            deterministic_rank=rank,
            deterministic_score=0.75 / rank + score,
            router_score=0.0,
            total_score=0.75 / rank + score,
        )
    for route_index, route in enumerate(routes):
        route_weight = 1.0 + 0.1 * route_index
        for selection in route.selections:
            current = scores.get(selection.page_ref)
            deterministic_rank = current.deterministic_rank if current is not None else None
            deterministic_score = current.deterministic_score if current is not None else 0.0
            router_score = (11 - selection.rank) / 10.0 + selection.confidence
            router_score *= route_weight
            previous_router = current.router_score if current is not None else 0.0
            scores[selection.page_ref] = _PageScore(
                source_ref=selection.page_ref,
                deterministic_rank=deterministic_rank,
                deterministic_score=deterministic_score,
                router_score=previous_router + router_score,
                total_score=deterministic_score + previous_router + router_score,
            )
    return sorted(
        scores.values(),
        key=lambda item: (-item.total_score, item.deterministic_rank or 10**9, item.source_ref),
    )


def _candidate_deterministic_scores(result: HybridRetrievalResult) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for entry in result.diagnostics.entries:
        scores[entry.candidate_ref] += float(entry.rrf_contribution)
    return dict(scores)


def _query_terms(request: QueryInput, plan: QueryPlan) -> set[str]:
    text = " ".join(
        [
            request.query,
            plan.normalised_query,
            *plan.canonical_terms,
            *plan.subqueries,
        ]
    )
    return {
        token
        for token in re.findall(r"[A-Za-z0-9]+", text.casefold())
        if len(token) >= 3 and token not in _STOP_WORDS
    }


def _candidate_support_score(
    candidate: RetrievalCandidate,
    terms: set[str],
    original_query: str,
) -> float:
    document = " ".join(
        [
            candidate.title,
            *candidate.heading_path,
            candidate.excerpt,
            *[" ".join(row) for row in candidate.table_rows],
        ]
    ).casefold()
    document_terms = set(re.findall(r"[A-Za-z0-9]+", document))
    overlap = len(terms & document_terms)
    score = float(overlap)
    query_phrase = " ".join(re.findall(r"[a-z0-9]+", original_query.casefold()))
    if query_phrase and query_phrase in document:
        score += 10.0
    title_terms = set(re.findall(r"[A-Za-z0-9]+", candidate.title.casefold()))
    score += 2.0 * len(terms & title_terms)
    if candidate.is_table_row:
        score += 0.25
    return score


def _metadata_support(
    page_refs: Sequence[str],
    cards: Sequence[object],
    terms: set[str],
) -> bool:
    selected = set(page_refs)
    for card in cards:
        if getattr(card, "source_ref", None) not in selected:
            continue
        text = " ".join(
            [
                str(getattr(card, "title", "")),
                str(getattr(card, "purpose", "")),
                *[str(item) for item in getattr(card, "topics", [])],
                *[str(item) for item in getattr(card, "acronyms", [])],
                *[str(item) for item in getattr(card, "likely_scope_terms", [])],
            ]
        )
        if terms & set(re.findall(r"[A-Za-z0-9]+", text.casefold())):
            return True
    return False


_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "can",
        "could",
        "did",
        "does",
        "for",
        "from",
        "have",
        "has",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "please",
        "should",
        "that",
        "the",
        "these",
        "this",
        "to",
        "when",
        "where",
        "which",
        "why",
        "with",
        "would",
        "you",
        "your",
    }
)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
