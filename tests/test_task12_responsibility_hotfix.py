"""Task 12 regression tests for generic responsibility-table questions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from riskon.config import load_milestone2_config
from riskon.event_runtime.corpus_loader import ingest_event_sections
from riskon.event_runtime.evidence_reasoning import (
    EventEvidenceReasoningRuntime,
    _validated_claim,
)
from riskon.event_runtime.evidence_reasoning_models import (
    ContextAssessment,
    EvidenceClaim,
    SupportingSpan,
)
from riskon.event_runtime.retrieval import EventHybridRetriever
from riskon.event_runtime.semantic_retrieval import SemanticEventRetriever
from riskon.models import (
    Decision,
    ManifestEntry,
    QueryInput,
    QueryIntent,
    QueryPlan,
    RetrievalChannel,
    Route,
)
from riskon.orchestra.source_safety import LocalCorpus
from riskon.provenance import ProvenanceIndex

_QUESTION = "What are the responsibilities of the local client classification responsible?"


def _responsibility_html() -> str:
    rows = [
        (
            "1LOD Control Design",
            "Definition/design of Key Controls (based on local policy) Review of Key Controls",
            "Local",
            "Local CC Owner",
        ),
        (
            "Policy and Guidelines",
            "Define / maintain local policy and guidelines Watch regulatory changes (local) "
            "Keep global topic owner informed about any changes",
            "Local",
            "Local CC Owner",
        ),
        (
            "Training",
            "Develop / maintain training material Conduct training",
            "Local",
            "Local CC Owner",
        ),
        (
            "Tool",
            "Request budget for changes in local CRM Define respective business requirement "
            "and assure implementation Testing",
            "Local",
            "Local CC Owner",
        ),
        (
            "Process",
            "Maintain process for client classification (forms, communication, approval and "
            "monitoring process)",
            "Local",
            "Local CC Owner",
        ),
        ("1LOD Control Execution", "Perform Key Controls (if required)", "Local", "Local 1LOD"),
        (
            "RTO Tasks",
            "Maintain &amp; refine client classification risk scenarios related to own risk type "
            "in RTOA and Reporting Reflect client classification risk type dependencies "
            "accordingly in global policies",
            "Global",
            "RTO",
        ),
        (
            "Oversight",
            "Provide GPS RC governance for required strategic decision related to client "
            "classification topics Keep global overview about local standards, local "
            "regulatory changes, processes and issues Support Client Classification "
            "initiatives, incidents and requests (within available capacity)",
            "Global",
            "GPS RC",
        ),
    ]
    body = "\n".join(
        f"<tr><td>{role}</td><td>{responsibility}</td><td>{scope}</td>"
        f"<td>{owner}</td><td></td><td></td><td></td></tr>"
        for role, responsibility, scope, owner in rows
    )
    return (
        "<html><body><h1>Responsibilities of Local Client Classification Responsible</h1>"
        "<table><tr><th></th><th>Responsibility / Role</th><th>Scope</th>"
        "<th>Local CC Owner</th><th>Local 1LOD</th><th>RTO</th><th>GPS RC</th></tr>"
        f"{body}</table></body></html>"
    )


def _corpus(tmp_path: Path, *, scope: dict[str, str] | None = None) -> LocalCorpus:
    source = tmp_path / "460471290.html"
    source.write_text(_responsibility_html(), encoding="utf-8")
    entry = ManifestEntry(
        filename=source.name,
        title="Global Client Classification Inventory",
        url=f"local://event-wiki/{source.name}",
        source_path=str(source),
    )
    sections = ingest_event_sections([entry])
    if scope is not None:
        sections = [sections[0].model_copy(update={"scope": scope})]
    provenance = ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2")
    return LocalCorpus(
        sections=tuple(sections),
        provenance=provenance,
        knowledge_root=tmp_path,
    )


def _plan() -> QueryPlan:
    return QueryPlan(
        plan_id="task12-responsibility",
        original_query=_QUESTION,
        normalised_query=_QUESTION,
        intent=QueryIntent.REFERENCE_LOOKUP,
        canonical_terms=["responsibility", "local", "client", "classification"],
        required_context_fields=[],
        missing_context_fields=[],
        subqueries=[_QUESTION],
        retrieval_channels=[
            RetrievalChannel.EXACT,
            RetrievalChannel.TABLE_ROW,
            RetrievalChannel.WORD_TFIDF,
            RetrievalChannel.CHAR_TFIDF,
        ],
        retrieval_skipped=False,
    )


class _Planner:
    def __init__(self, plan: QueryPlan) -> None:
        self._plan = plan

    def plan(self, _request: QueryInput) -> QueryPlan:
        return self._plan

    def context_values(self, request: QueryInput, _plan: QueryPlan) -> dict[str, str]:
        return dict(request.context)


class _NoRouter:
    cards: tuple[Any, ...] = ()

    def route(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the exact responsibility table path must not call the router")


class _NoLLM:
    def request_json(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the exact responsibility table path must not call an LLM")


class _NoRoute:
    def route(self, *_args: Any, **_kwargs: Any) -> Route:
        return Route(
            support_function="TEST",
            routing_reason="test scope conflict",
            routing_confidence=0.0,
        )


def _runtime(corpus: LocalCorpus) -> EventEvidenceReasoningRuntime:
    config = load_milestone2_config(Path("config/milestone2.toml"))
    retriever = EventHybridRetriever(list(corpus.sections), corpus.provenance, config.retrieval)
    semantic = SemanticEventRetriever(_Planner(_plan()), retriever, _NoRouter())
    return EventEvidenceReasoningRuntime(
        corpus,
        semantic,
        _NoLLM(),  # type: ignore[arg-type]
        _NoRoute(),  # type: ignore[arg-type]
    )


def test_generic_responsibility_question_answers_from_a_scoped_page(tmp_path: Path) -> None:
    result = _runtime(_corpus(tmp_path, scope={"jurisdiction": "Switzerland"})).run(
        QueryInput(query=_QUESTION, context={})
    )

    assert result.decision is Decision.ANSWER
    assert "SCOPE_MISMATCH" not in {reason.value for reason in result.reason_codes}
    assert result.scope_violation_count == 0
    assert result.primary_source == "Global Client Classification Inventory"


def test_explicit_conflicting_jurisdiction_still_protects_scope(tmp_path: Path) -> None:
    result = _runtime(_corpus(tmp_path, scope={"jurisdiction": "Switzerland"})).run(
        QueryInput(
            query=_QUESTION,
            context={"jurisdiction": "United Kingdom"},
        )
    )

    assert result.decision is Decision.ABSTAIN
    assert "SCOPE_MISMATCH" in {reason.value for reason in result.reason_codes}
    assert result.scope_violation_count == 8
    assert result.answer is None


def test_responsibility_list_uses_all_original_table_rows(tmp_path: Path) -> None:
    result = _runtime(_corpus(tmp_path)).run(QueryInput(query=_QUESTION, context={}))

    assert result.decision is Decision.ANSWER
    assert len(result.final_evidence_units) == 8
    assert len(result.validated_claims) == 8
    assert all(unit.kind == "table_row" for unit in result.final_evidence_units)
    assert all(
        any(f":table-1:row-{index}" in ref for ref in result.evidence_refs) for index in range(1, 9)
    )
    assert all(role in (result.answer or "") for role in ("Training", "Process", "Oversight"))


def test_unsupported_extra_responsibility_is_rejected_by_validation(tmp_path: Path) -> None:
    runtime = _runtime(_corpus(tmp_path))
    result = runtime.run(QueryInput(query=_QUESTION, context={}))
    assert result.final_analysis is not None
    evidence = result.final_evidence_units[0]
    extra = EvidenceClaim(
        claim_id="unsupported-extra",
        claim_text="Cryptocurrency trading is permitted.",
        evidence_refs=[evidence.evidence_ref],
        supporting_spans=[SupportingSpan(evidence_ref=evidence.evidence_ref, span=evidence.text)],
        critical_control=False,
        applicable_scope=[],
    )
    analysis = result.final_analysis.model_copy(
        update={"material_claims": [*result.final_analysis.material_claims, extra]}
    )

    validation = runtime._validate_claims(
        QueryInput(query=_QUESTION, context={}),
        ContextAssessment(intent="REFERENCE_LOOKUP"),
        analysis,
        list(result.final_evidence_units),
        claim_limit=9,
    )
    approved = tuple(_validated_claim(claim) for claim in validation.valid_claims)
    decision, answer, *_rest = runtime._firewall(
        QueryInput(query=_QUESTION, context={}),
        result.detected_context,
        ContextAssessment(intent="REFERENCE_LOOKUP"),
        result.final_retrieval,
        analysis,
        list(result.final_evidence_units),
        validation,
        approved,
        None,
    )

    assert decision is Decision.ANSWER
    assert "unsupported-extra" in validation.rejected_claim_ids
    assert "Cryptocurrency" not in (answer or "")
