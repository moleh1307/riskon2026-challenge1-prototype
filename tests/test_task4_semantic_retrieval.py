"""Contract tests for the bounded Task 4 semantic retrieval path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from riskon.config import load_milestone2_config
from riskon.event_runtime.config import EventRuntimeConfig
from riskon.event_runtime.corpus_loader import ingest_event_sections
from riskon.event_runtime.llm_client import (
    PAGE_CARD_MODEL,
    PAGE_CARD_REASONING,
    ROUTER_RETRY_MODEL,
    ROUTER_RETRY_REASONING,
    TITLE_ROUTER_MODEL,
    TITLE_ROUTER_REASONING,
    LLMCallRecord,
    Task4LLMConfig,
)
from riskon.event_runtime.page_cards import build_page_cards
from riskon.event_runtime.query_planner import EventQueryPlanner
from riskon.event_runtime.retrieval import EventHybridRetriever
from riskon.event_runtime.semantic_models import (
    PageCard,
    PageCardPayload,
    RouterOutput,
    RouterSelection,
    SemanticFailureReason,
    SufficiencyStatus,
)
from riskon.event_runtime.semantic_retrieval import SemanticEventRetriever
from riskon.event_runtime.title_router import PageCardRouter, RouterResult
from riskon.hybrid_retrieval import HybridRetrievalResult
from riskon.models import ManifestEntry, QueryInput, RetrievalDiagnostics
from riskon.orchestra.source_safety import LocalCorpus
from riskon.provenance import ProvenanceIndex


class _FakeClient:
    def __init__(self, router_output: RouterOutput | None = None) -> None:
        self.router_output = router_output
        self.calls: list[str] = []
        self.prompts: list[str] = []

    def request_json(
        self,
        phase: str,
        response_model: type[Any],
        *,
        developer_prompt: str,
        user_prompt: str,
    ) -> tuple[Any, LLMCallRecord]:
        del developer_prompt
        self.calls.append(phase)
        self.prompts.append(user_prompt)
        call = LLMCallRecord(
            phase=phase,  # type: ignore[arg-type]
            model="test-model",
            reasoning_effort="none",  # type: ignore[arg-type]
            input_tokens=10,
            output_tokens=5,
            cached_input_tokens=0,
            latency_ms=1.0,
        )
        if response_model is PageCardPayload:
            return (
                PageCardPayload(
                    title="ignored by binder",
                    purpose="A concise page purpose for routing.",
                    topics=["policy", "guidance"],
                    acronyms=["ABC"],
                    likely_scope_terms=["CH"],
                    contains_table=False,
                    contains_visual=False,
                ),
                call,
            )
        if self.router_output is None:
            raise AssertionError("router output was not configured")
        return self.router_output, call


def _event_config(tmp_path: Path) -> EventRuntimeConfig:
    return EventRuntimeConfig(
        project_root=tmp_path,
        pipeline_config=tmp_path / "pipeline.toml",
        source_root=tmp_path,
        manifest=tmp_path / "manifest.xlsx",
        url_prefix="local://event-wiki/",
        generated_root=tmp_path / "generated",
        alias_registry=tmp_path / "aliases.json",
        routing_profile="default",
        overlay_enabled=False,
        event_data_copy_enabled=False,
        network_enabled=False,
        external_api_enabled=False,
    )


def _corpus(tmp_path: Path, names_and_text: list[tuple[str, str]]) -> LocalCorpus:
    entries: list[ManifestEntry] = []
    for index, (name, text) in enumerate(names_and_text):
        source = tmp_path / name
        source.write_text(
            f"<html><body><h1>Page {index}</h1><p>{text}</p></body></html>",
            encoding="utf-8",
        )
        entries.append(
            ManifestEntry(
                filename=name,
                title=f"Page {index}",
                url=f"local://event-wiki/{name}",
                source_path=str(source),
            )
        )
    sections = ingest_event_sections(entries)
    provenance = ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2")
    return LocalCorpus(
        sections=tuple(sections),
        provenance=provenance,
        knowledge_root=tmp_path,
    )


def _retrieval_components(
    corpus: LocalCorpus,
) -> tuple[EventQueryPlanner, EventHybridRetriever]:
    config = load_milestone2_config(Path("config/milestone2.toml"))
    planner = EventQueryPlanner.from_aliases(
        [],
        page_titles=[section.title for section in corpus.sections],
        config=config.query_planning,
    )
    return planner, EventHybridRetriever(list(corpus.sections), corpus.provenance, config.retrieval)


def _card(source_ref: str, filename: str, title: str, purpose: str) -> PageCard:
    return PageCard(
        title=title,
        purpose=purpose,
        topics=["target"],
        acronyms=[],
        likely_scope_terms=[],
        contains_table=False,
        contains_visual=False,
        source_ref=source_ref,
        filename=filename,
        source_hash="0" * 64,
    )


def test_task4_model_policy_is_exact_and_uses_no_sol() -> None:
    assert PAGE_CARD_MODEL == "gpt-5.6-luna"
    assert PAGE_CARD_REASONING == "none"
    assert TITLE_ROUTER_MODEL == "gpt-5.6-terra"
    assert TITLE_ROUTER_REASONING == "low"
    assert ROUTER_RETRY_MODEL == "gpt-5.6-terra"
    assert ROUTER_RETRY_REASONING == "medium"
    assert (
        "sol"
        not in " ".join(
            [
                PAGE_CARD_MODEL,
                TITLE_ROUTER_MODEL,
                ROUTER_RETRY_MODEL,
                PAGE_CARD_REASONING,
                TITLE_ROUTER_REASONING,
                ROUTER_RETRY_REASONING,
            ]
        ).casefold()
    )


def test_page_cards_reuse_unchanged_pages_and_regenerate_changed_hash(
    tmp_path: Path,
) -> None:
    corpus = _corpus(tmp_path, [("one.html", "A policy page.")])
    config = _event_config(tmp_path)
    first_client = _FakeClient()
    first = build_page_cards(corpus, config, first_client)
    assert first.generated_count == 1
    assert first.reused_count == 0
    first_hash = first.document.cards[0].source_hash

    second_client = _FakeClient()
    second = build_page_cards(corpus, config, second_client)
    assert second.generated_count == 0
    assert second.reused_count == 1
    assert second_client.calls == []

    (tmp_path / "one.html").write_text(
        "<html><body><h1>Page 0</h1><p>A changed policy page.</p></body></html>",
        encoding="utf-8",
    )
    changed_client = _FakeClient()
    changed = build_page_cards(corpus, config, changed_client)
    assert changed.generated_count == 1
    assert changed.document.cards[0].source_hash != first_hash


def test_title_router_bounds_shortlist_and_drops_unknown_refs(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path, [(f"{index}.html", f"topic {index}") for index in range(12)])
    cards = [
        _card(section.source_ref, section.filename, section.title, "routing purpose")
        for section in corpus.sections
    ]
    output = RouterOutput(
        selections=[
            RouterSelection(
                page_ref="local://event-wiki/unknown.html", rank=1, confidence=1.0, reason="bad"
            ),
            RouterSelection(page_ref=cards[0].source_ref, rank=2, confidence=0.8, reason="good"),
        ]
    )
    client = _FakeClient(output)
    router = PageCardRouter(
        cards,
        client,
        config=Task4LLMConfig(router_title_shortlist=10, router_card_limit=8),
    )
    planner, _retriever = _retrieval_components(corpus)
    request = QueryInput(query="topic 0")
    plan = planner.plan(request)
    result = router.route(request, plan, [cards[0].source_ref])
    assert len(result.shortlist_page_refs) <= 10
    assert [item.page_ref for item in result.selections] == [cards[0].source_ref]
    prompt = json.loads(client.prompts[0])
    assert len(prompt["title_shortlist"]) <= 10
    assert len(prompt["relevant_page_cards"]) <= 8


def test_retry_router_is_empty_when_no_alternative_page_exists(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path, [("only.html", "policy material")])
    card = _card(
        corpus.sections[0].source_ref,
        corpus.sections[0].filename,
        corpus.sections[0].title,
        "policy material",
    )
    client = _FakeClient(
        RouterOutput(
            selections=[
                RouterSelection(
                    page_ref=card.source_ref,
                    rank=1,
                    confidence=1.0,
                    reason="only page",
                )
            ]
        )
    )
    router = PageCardRouter([card], client)
    planner, _retriever = _retrieval_components(corpus)
    request = QueryInput(query="unrelated question")
    plan = planner.plan(request)

    result = router.route(
        request,
        plan,
        [card.source_ref],
        previous_attempted_refs=[card.source_ref],
        failure_reason=SemanticFailureReason.WRONG_PAGE,
    )

    assert result.retry
    assert result.selections == ()
    assert result.call is None
    assert client.calls == []


def test_hybrid_union_respects_ten_page_cap_and_keeps_router_page(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path, [(f"{index}.html", f"topic {index}") for index in range(12)])
    planner, deterministic = _retrieval_components(corpus)
    cards = [
        _card(section.source_ref, section.filename, section.title, "topic routing")
        for section in corpus.sections
    ]
    selected = tuple(
        RouterSelection(
            page_ref=cards[index].source_ref,
            rank=index + 1,
            confidence=1.0,
            reason="semantic match",
        )
        for index in range(10)
    )
    router = PageCardRouter(cards, _FakeClient(RouterOutput(selections=list(selected))))
    semantic = SemanticEventRetriever(
        planner,
        deterministic,
        router,
        config=Task4LLMConfig(max_selected_pages=10),
    )
    outcome = semantic.retrieve(QueryInput(query="topic 9"))
    assert len(outcome.hybrid_page_refs) <= 10
    assert cards[9].source_ref in outcome.hybrid_page_refs
    assert all(
        candidate.source_ref in outcome.hybrid_page_refs
        for candidate in outcome.selected_candidates
    )


def test_retry_is_exactly_one_and_uses_retry_phase(tmp_path: Path) -> None:
    corpus = _corpus(
        tmp_path, [("wrong.html", "unrelated material"), ("right.html", "target policy guidance")]
    )
    planner, real_retriever = _retrieval_components(corpus)
    cards = [
        _card(section.source_ref, section.filename, section.title, "unrelated")
        for section in corpus.sections
    ]
    cards[1] = cards[1].model_copy(update={"purpose": "target policy guidance"})

    class _RetryRouter:
        def __init__(self) -> None:
            self.cards = tuple(cards)
            self.calls = 0

        def route(self, *args: Any, **kwargs: Any) -> RouterResult:
            del args
            self.calls += 1
            retry = kwargs.get("failure_reason") is not None
            index = 1 if retry else 0
            phase = "router_retry" if retry else "title_router"
            return RouterResult(
                selections=(
                    RouterSelection(
                        page_ref=cards[index].source_ref,
                        rank=1,
                        confidence=1.0,
                        reason="test route",
                    ),
                ),
                attempted_page_refs=(cards[index].source_ref,),
                shortlist_page_refs=(cards[index].source_ref,),
                call=LLMCallRecord(
                    phase=phase,  # type: ignore[arg-type]
                    model="test-model",
                    reasoning_effort="medium" if retry else "low",  # type: ignore[arg-type]
                    input_tokens=0,
                    output_tokens=0,
                    cached_input_tokens=0,
                    latency_ms=0.0,
                ),
                retry=retry,
            )

    router = _RetryRouter()

    class _EmptyDeterministicRetriever:
        candidates = real_retriever.candidates
        _candidate_by_ref = real_retriever._candidate_by_ref
        config = real_retriever.config

        def retrieve(self, plan: Any, context: Any) -> HybridRetrievalResult:
            del plan, context
            return HybridRetrievalResult(
                final_candidates={},
                selected_candidates=(),
                diagnostics=RetrievalDiagnostics(),
            )

        def _context_conflict(self, *args: Any, **kwargs: Any) -> bool:
            del args, kwargs
            return False

    semantic = SemanticEventRetriever(planner, _EmptyDeterministicRetriever(), router)  # type: ignore[arg-type]
    outcome = semantic.retrieve(QueryInput(query="target policy"))
    assert router.calls == 2
    assert outcome.retry_count == 1
    assert outcome.retry_router is not None
    assert outcome.retry_router.call.phase == "router_retry"
    assert outcome.sufficiency.status is SufficiencyStatus.SUFFICIENT
