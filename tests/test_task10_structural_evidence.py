"""Task 10 structural evidence, gap, and no-LLM fast-path contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from riskon.config import load_milestone2_config
from riskon.event_runtime.answer_presentation import format_structural_answer
from riskon.event_runtime.corpus_loader import ingest_event_sections
from riskon.event_runtime.evidence_reasoning import EventEvidenceReasoningRuntime
from riskon.event_runtime.retrieval import EventHybridRetriever
from riskon.event_runtime.semantic_retrieval import SemanticEventRetriever
from riskon.event_runtime.structural_matrix import (
    SourceGapResult,
    SourceGapWorker,
    StructuralMatrixWorker,
    StructuralStatus,
)
from riskon.event_structure.adapter import attach_structural_tables, build_structural_event_corpus
from riskon.models import (
    ManifestEntry,
    QueryInput,
    QueryIntent,
    QueryPlan,
    RetrievalChannel,
)
from riskon.orchestra.source_safety import LocalCorpus
from riskon.provenance import ProvenanceIndex


def _entry(tmp_path: Path, filename: str, title: str, html: str) -> ManifestEntry:
    source = tmp_path / filename
    source.write_text(html, encoding="utf-8")
    return ManifestEntry(
        filename=filename,
        title=title,
        url=f"local://event-wiki/{filename}",
        source_path=str(source),
    )


def _matrix_html() -> str:
    return """<html><body>
    <p><ac:emoticon ac:name="tick"/> Session and Overnight
       <ac:emoticon ac:name="warning"/> only session
       <ac:emoticon ac:name="information"/> only overnight</p>
    <h2>Advisory Location CH (BC CH)</h2>
    <table>
      <tr><th rowspan="2">Service Model</th><th colspan="4">Alerts</th></tr>
      <tr><th>Alert A</th><th>Alert B</th><th>Alert C</th><th>Alert D</th></tr>
      <tr><td>Advice Premium</td><td><ac:emoticon ac:name="tick"/></td>
          <td><ac:emoticon ac:name="warning"/></td>
          <td><ac:emoticon ac:name="information"/></td>
          <td><ac:image ac:alt="(error)"><ri:url
          ri:value="https://wiki.example/icons/emoticons/error.svg"/></ac:image></td></tr>
      <tr><td>Advice Basic</td><td><ac:emoticon ac:name="warning"/></td>
          <td><ac:emoticon ac:name="tick"/></td>
          <td><ac:emoticon ac:name="information"/></td>
          <td><ac:image ac:alt="(error)"><ri:url
          ri:value="https://wiki.example/icons/emoticons/error.svg"/></ac:image></td></tr>
    </table></body></html>"""


def _corpus(tmp_path: Path) -> LocalCorpus:
    entry = _entry(tmp_path, "matrix.html", "Matrix", _matrix_html())
    structural = build_structural_event_corpus([entry])
    sections = attach_structural_tables(ingest_event_sections([entry]), structural)
    provenance = ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2")
    return LocalCorpus(
        sections=tuple(sections),
        provenance=provenance,
        knowledge_root=tmp_path,
        structural=structural,
    )


def _plan() -> QueryPlan:
    return QueryPlan(
        plan_id="task10-test",
        original_query="Which alerts apply for Advice Premium in Advisory Location CH?",
        normalised_query="which alerts apply for advice premium in advisory location ch",
        intent=QueryIntent.CONFIGURATION_LOOKUP,
        canonical_terms=["alerts", "advice premium", "advisory location"],
        required_context_fields=[],
        missing_context_fields=[],
        subqueries=["which alerts apply for advice premium in advisory location ch"],
        retrieval_channels=[RetrievalChannel.EXACT, RetrievalChannel.TABLE_ROW],
        retrieval_skipped=False,
    )


def _retriever(corpus: LocalCorpus) -> EventHybridRetriever:
    config = load_milestone2_config(Path("config/milestone2.toml"))
    return EventHybridRetriever(list(corpus.sections), corpus.provenance, config.retrieval)


def test_structural_worker_filters_session_rows_and_preserves_error(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    retriever = _retriever(corpus)
    plan = _plan()
    request = QueryInput(
        query="Which session alerts are triggered for Advice Premium in Advisory Location CH?",
        context={"region": "CH", "service_model": "Advice Premium"},
    )
    retrieval = retriever.retrieve(plan, {"region": "CH", "service_model": "Advice Premium"})
    result = StructuralMatrixWorker(corpus).evaluate(request, plan, retrieval)

    assert result.status is StructuralStatus.SUFFICIENT
    assert result.matched_record_count == 2
    assert result.unresolved_states == ["error"]
    assert result.table_complete
    assert result.provenance_valid
    assert len(result.claims) == 2
    assert all("information" not in claim.claim_text for claim in result.claims)


def test_equivalent_k_and_e_expansions_are_not_ambiguous(tmp_path: Path) -> None:
    entry = _entry(
        tmp_path,
        "glossary.html",
        "Glossary",
        "<html><body><p>Knowledge &amp; Experience (K&amp;E).</p>"
        "<p>Knowledge and Experience (K&amp;E).</p></body></html>",
    )
    structural = build_structural_event_corpus([entry])
    sections = attach_structural_tables(ingest_event_sections([entry]), structural)
    corpus = LocalCorpus(
        sections=tuple(sections),
        provenance=ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2"),
        knowledge_root=tmp_path,
        structural=structural,
    )

    expansions, ambiguities = StructuralMatrixWorker(corpus)._acronym_state(
        QueryInput(query="Is K&E required?", context={})
    )

    assert expansions == {"K&E": "Knowledge & Experience"}
    assert ambiguities == {}


def test_source_gap_worker_reports_missing_package_asset(tmp_path: Path) -> None:
    entry = _entry(
        tmp_path,
        "diagram.html",
        "Diagram",
        "<html><body><h1>Diagram</h1><ac:image><ri:attachment "
        'ri:filename="missing.png"/></ac:image></body></html>',
    )
    structural = build_structural_event_corpus([entry])
    sections = attach_structural_tables(ingest_event_sections([entry]), structural)
    corpus = LocalCorpus(
        sections=tuple(sections),
        provenance=ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2"),
        knowledge_root=tmp_path,
        structural=structural,
    )
    source_ref = sections[0].source_ref
    result = SourceGapWorker(corpus).evaluate([source_ref])

    assert result.firewall_code == "SOURCE_PACKAGE_ASSET_UNAVAILABLE"
    assert result.gaps[0].target == "missing.png"
    assert "not delivered" in result.distinction


def test_gap_result_merges_existing_acronym_metadata(tmp_path: Path) -> None:
    worker = StructuralMatrixWorker(_corpus(tmp_path))
    gap = SourceGapResult(
        required=True,
        distinction="The required source asset was not delivered in the event package.",
    )

    result = worker._gap_result(
        gap,
        {"LOD": "Line of Defence"},
        {},
        acronym_expansions={"LOD": "Line of Defence"},
        source_refs=["local://event-wiki/matrix.html"],
    )

    assert result.status is StructuralStatus.SOURCE_PACKAGE_ASSET_UNAVAILABLE
    assert result.acronym_expansions == {"LOD": "Line of Defence"}
    assert result.source_refs == ["local://event-wiki/matrix.html"]


def test_structural_fast_path_does_not_call_router_or_llm(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    retriever = _retriever(corpus)
    plan = _plan()

    class _Planner:
        def plan(self, _request: QueryInput) -> QueryPlan:
            return plan

        def context_values(
            self,
            request: QueryInput,
            _plan: QueryPlan,
        ) -> dict[str, str]:
            return dict(request.context)

    class _NoRouter:
        cards: tuple[Any, ...] = ()

        def route(self, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("structural fast path called the semantic router")

    class _NoLLM:
        calls = 0

        def request_json(self, *_args: Any, **_kwargs: Any) -> Any:
            self.calls += 1
            raise AssertionError("structural fast path called an LLM")

    semantic = SemanticEventRetriever(_Planner(), retriever, _NoRouter())  # type: ignore[arg-type]
    client = _NoLLM()
    runtime = EventEvidenceReasoningRuntime(
        corpus,
        semantic,
        client,  # type: ignore[arg-type]
        SimpleNamespace(),
    )
    result = runtime.run(
        QueryInput(
            query="Which alerts apply for Advice Premium in Advisory Location CH?",
            context={"region": "CH", "service_model": "Advice Premium"},
        )
    )

    assert result.decision.value == "ANSWER"
    assert result.skeptic is None
    assert client.calls == 0


def test_structural_answer_groups_declared_states_and_keeps_unresolved_visible(
    tmp_path: Path,
) -> None:
    corpus = _corpus(tmp_path)
    retriever = _retriever(corpus)
    plan = _plan()
    request = QueryInput(
        query="Which alerts apply for Advice Premium in Advisory Location CH?",
        context={"region": "CH", "service_model": "Advice Premium"},
    )
    retrieval = retriever.retrieve(plan, {"region": "CH", "service_model": "Advice Premium"})
    result = StructuralMatrixWorker(corpus).evaluate(request, plan, retrieval)

    answer = format_structural_answer(result.claims)

    assert "Scope: Advisory Location CH (BC CH) · Service Model: Advice Premium" in answer
    assert "Source-declared alert configuration" in answer
    assert "Session and overnight (tick)" in answer
    assert "Only session (warning)" in answer
    assert "Only overnight (information)" in answer
    assert "Unresolved source state" in answer
    assert "state: error; the source declares no meaning" in answer
    assert "heading:" not in answer
    assert "icon encoding:" not in answer
