"""Contract tests for the bounded Task 6 Policy Atlas path."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from riskon.config import load_milestone2_config
from riskon.event_runtime.config import EventRuntimeConfig
from riskon.event_runtime.corpus_loader import ingest_event_sections
from riskon.event_runtime.evidence_reasoning import EventEvidenceReasoningRuntime
from riskon.event_runtime.evidence_reasoning_models import (
    ContextAssessment,
    SkepticOutput,
    SupportingSpan,
    ValidatedClaim,
)
from riskon.event_runtime.llm_client import (
    ELIGIBILITY_MODEL,
    ELIGIBILITY_REASONING,
    POLICY_ATLAS_MODEL,
    POLICY_ATLAS_REASONING,
    LLMCallRecord,
    Task6LLMConfig,
)
from riskon.event_runtime.policy_atlas import (
    PolicyAtlasRouter,
    apply_atlas_retrieval,
    build_policy_atlas,
    load_answerability_graph,
    load_policy_atlas,
)
from riskon.event_runtime.policy_atlas_models import (
    ContrastiveEligibilityOutput,
    EligibilityDecision,
    EligibilityStatus,
    GraphEdgeType,
    PolicyFingerprintPayload,
    ScopeConstraint,
)
from riskon.event_runtime.retrieval import EventHybridRetriever
from riskon.event_runtime.semantic_models import (
    EvidenceSufficiency,
    SufficiencyStatus,
)
from riskon.event_runtime.semantic_retrieval import SemanticRetrievalOutcome
from riskon.event_runtime.title_router import RouterResult
from riskon.models import ManifestEntry, QueryInput
from riskon.orchestra.source_safety import LocalCorpus
from riskon.provenance import ProvenanceIndex


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


def _write_corpus(tmp_path: Path) -> LocalCorpus:
    pages = [
        (
            "policy.html",
            "Advisory Policy",
            "Policy guidance explains the approved form and the workflow. "
            '<a href="procedure.html">Procedure Template</a> '
            '<a href="client-book.html">Client Book</a>',
        ),
        (
            "client-book.html",
            "Client Book",
            "Client book guidance explains the approved form and the workflow.",
        ),
        (
            "procedure.html",
            "Procedure Template",
            "The procedure explains the approved form and the workflow steps.",
        ),
    ]
    entries: list[ManifestEntry] = []
    for filename, title, body in pages:
        (tmp_path / filename).write_text(
            f"<html><body><h1>{title}</h1><p>{body}</p></body></html>",
            encoding="utf-8",
        )
        entries.append(
            ManifestEntry(
                filename=filename,
                title=title,
                url=f"local://event-wiki/{filename}",
                source_path=str(tmp_path / filename),
            )
        )
    sections = ingest_event_sections(entries)
    provenance = ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2")
    return LocalCorpus(
        sections=tuple(sections),
        provenance=provenance,
        knowledge_root=tmp_path,
    )


def _reingest(tmp_path: Path) -> LocalCorpus:
    entries = [
        ManifestEntry(
            filename=filename,
            title=title,
            url=f"local://event-wiki/{filename}",
            source_path=str(tmp_path / filename),
        )
        for filename, title in (
            ("policy.html", "Advisory Policy"),
            ("client-book.html", "Client Book"),
            ("procedure.html", "Procedure Template"),
        )
    ]
    sections = ingest_event_sections(entries)
    provenance = ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2")
    return LocalCorpus(
        sections=tuple(sections),
        provenance=provenance,
        knowledge_root=tmp_path,
    )


def _call(phase: str) -> LLMCallRecord:
    return LLMCallRecord(
        phase=phase,  # type: ignore[arg-type]
        model="test-model",
        reasoning_effort="medium",  # type: ignore[arg-type]
        input_tokens=10,
        output_tokens=5,
        cached_input_tokens=0,
        latency_ms=1.0,
    )


class _FakeAtlasClient:
    def __init__(self, *, ineligible_client_book: bool = False) -> None:
        self.ineligible_client_book = ineligible_client_book
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
        payload = json.loads(user_prompt)
        if response_model is PolicyFingerprintPayload:
            source_ref = str(payload["page_ref"])
            if source_ref.endswith("policy.html"):
                return (
                    PolicyFingerprintPayload(
                        purpose=(
                            "Policy guidance identifies the applicable workflow and approved form."
                        ),
                        answerable_questions=[
                            "Which policy workflow applies?",
                            "Which approved form supports the policy?",
                            "What evidence is required for the policy?",
                        ],
                        anti_questions=[
                            "Which operational steps complete the form?",
                            "What does the client book record?",
                        ],
                        required_context_fields=["workflow_stage"],
                        explicit_scope_constraints=[
                            ScopeConstraint(field="workflow_stage", value="advisory")
                        ],
                        critical_controls=["The approved form must be used."],
                        acronyms=["K&E"],
                        confusable_with=["Client Book"],
                    ),
                    _call(phase),
                )
            if source_ref.endswith("client-book.html"):
                return (
                    PolicyFingerprintPayload(
                        purpose=(
                            "Client-book guidance identifies the record and approved form workflow."
                        ),
                        answerable_questions=[
                            "Which policy workflow applies?",
                            "Which approved form supports the policy?",
                            "What does the client book record?",
                        ],
                        anti_questions=[
                            "Which advisory policy applies?",
                            "Which operational steps complete the form?",
                        ],
                        required_context_fields=["workflow_stage"],
                        explicit_scope_constraints=[
                            ScopeConstraint(field="workflow_stage", value="client_book")
                        ],
                        critical_controls=["The client-book record must be complete."],
                        acronyms=["K&E"],
                        confusable_with=["Advisory Policy"],
                    ),
                    _call(phase),
                )
            return (
                PolicyFingerprintPayload(
                    purpose="Operational procedure explains how to complete the approved form.",
                    answerable_questions=[
                        "Which approved form supports the policy?",
                        "Which operational steps complete the form?",
                        "What workflow steps are required?",
                    ],
                    anti_questions=[
                        "Which advisory policy applies?",
                        "What does the client book record?",
                    ],
                    required_context_fields=["workflow_stage"],
                    explicit_scope_constraints=[],
                    critical_controls=["The approved form must be completed."],
                    acronyms=[],
                    confusable_with=["Advisory Policy"],
                ),
                _call(phase),
            )

        if response_model is ContrastiveEligibilityOutput:
            decisions: list[EligibilityDecision] = []
            for candidate in payload["candidate_pages"]:
                page_ref = str(candidate["page_ref"])
                if page_ref.endswith("client-book.html") and self.ineligible_client_book:
                    status = EligibilityStatus.INELIGIBLE_SCOPE
                    missing: list[str] = []
                else:
                    status = EligibilityStatus.ELIGIBLE
                    missing = []
                decisions.append(
                    EligibilityDecision(
                        page_ref=page_ref,
                        status=status,
                        why_can_answer="The fingerprint covers the question terms.",
                        why_not_authoritative="Original evidence still has to prove the answer.",
                        missing_context_fields=missing,
                        confidence=0.8,
                        anti_question_warning=False,
                    )
                )
            # Deliberately include an unknown ref: the router must not admit it.
            decisions.append(
                EligibilityDecision(
                    page_ref="local://event-wiki/unknown.html",
                    status=EligibilityStatus.ELIGIBLE,
                    why_can_answer="Unknown test page.",
                    why_not_authoritative="It is not in the supplied Atlas.",
                    missing_context_fields=[],
                    confidence=1.0,
                    anti_question_warning=False,
                )
            )
            return ContrastiveEligibilityOutput(decisions=decisions), _call(phase)
        raise AssertionError(f"unexpected response model: {response_model}")


def _retrieval_components(
    corpus: LocalCorpus,
) -> tuple[Any, EventHybridRetriever]:
    config = load_milestone2_config(Path("config/milestone2.toml"))
    from riskon.event_runtime.query_planner import EventQueryPlanner

    planner = EventQueryPlanner.from_aliases(
        [],
        page_titles=[section.title for section in corpus.sections],
        config=config.query_planning,
    )
    return planner, EventHybridRetriever(list(corpus.sections), corpus.provenance, config.retrieval)


def test_task6_fixed_policy_and_bounded_config() -> None:
    assert (POLICY_ATLAS_MODEL, POLICY_ATLAS_REASONING) == ("gpt-5.6-luna", "low")
    assert (ELIGIBILITY_MODEL, ELIGIBILITY_REASONING) == ("gpt-5.6-terra", "medium")
    assert "sol" not in f"{POLICY_ATLAS_MODEL} {ELIGIBILITY_MODEL}".casefold()
    config = Task6LLMConfig()
    assert config.policy_atlas_excerpt_chars == 3500
    assert config.atlas_candidate_limit == 10
    assert config.atlas_neighbor_limit == 6
    for response_model in (PolicyFingerprintPayload, ContrastiveEligibilityOutput):
        schema = response_model.model_json_schema()
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


def test_policy_atlas_reuses_hashes_and_derives_generic_graph(tmp_path: Path) -> None:
    corpus = _write_corpus(tmp_path)
    event_config = _event_config(tmp_path)
    first_client = _FakeAtlasClient()
    first = build_policy_atlas(corpus, event_config, first_client)
    assert first.generated_count == 3
    assert first.reused_count == 0
    assert len(first.document.fingerprints) == 3
    assert len(first.graph.nodes) == 3
    edge_types = {edge.edge_type for edge in first.graph.edges}
    assert GraphEdgeType.SUPPORTING_PROCEDURE in edge_types
    assert GraphEdgeType.CONFUSABLE_WITH in edge_types
    assert GraphEdgeType.SCOPE_ALTERNATIVE in edge_types

    second_client = _FakeAtlasClient()
    second = build_policy_atlas(corpus, event_config, second_client)
    assert second.generated_count == 0
    assert second.reused_count == 3
    assert second_client.calls == []

    old_hash = first.document.fingerprints[0].source_hash
    (tmp_path / "policy.html").write_text(
        "<html><body><h1>Advisory Policy</h1><p>Changed policy source.</p></body></html>",
        encoding="utf-8",
    )
    changed_client = _FakeAtlasClient()
    changed = build_policy_atlas(_reingest(tmp_path), event_config, changed_client)
    assert changed.generated_count == 1
    assert changed.reused_count == 2
    assert changed.document.fingerprints[0].source_hash != old_hash
    loaded_atlas = load_policy_atlas(_reingest(tmp_path), event_config)
    loaded_graph = load_answerability_graph(loaded_atlas, event_config)
    assert len(loaded_graph.nodes) == len(loaded_atlas.fingerprints) == 3


def test_contrastive_router_filters_unknown_and_ineligible_pages_and_finds_boundary(
    tmp_path: Path,
) -> None:
    corpus = _write_corpus(tmp_path)
    event_config = _event_config(tmp_path)
    atlas_build = build_policy_atlas(corpus, event_config, _FakeAtlasClient())
    client = _FakeAtlasClient()
    router = PolicyAtlasRouter(atlas_build.document, atlas_build.graph, client)
    planner, _retriever = _retrieval_components(corpus)
    request = QueryInput(query="Which policy workflow applies?")
    plan = planner.plan(request)
    refs = [
        "local://event-wiki/policy.html",
        "local://event-wiki/client-book.html",
        "local://event-wiki/procedure.html",
    ]
    result = router.evaluate(request, plan, {}, refs)
    assert "local://event-wiki/unknown.html" not in result.ranked_page_refs
    assert "workflow_stage" in result.clarification_fields
    assert result.expected_control_hints
    prompt = json.loads(client.prompts[0])
    assert len(prompt["candidate_pages"]) <= 10
    assert "evidence" not in prompt["candidate_pages"][0]


def test_atlas_retrieval_navigates_to_procedure_and_filters_scope(tmp_path: Path) -> None:
    corpus = _write_corpus(tmp_path)
    event_config = _event_config(tmp_path)
    atlas_build = build_policy_atlas(corpus, event_config, _FakeAtlasClient())
    router = PolicyAtlasRouter(
        atlas_build.document,
        atlas_build.graph,
        _FakeAtlasClient(ineligible_client_book=True),
    )
    planner, retriever = _retrieval_components(corpus)
    request = QueryInput(query="Which approved form supports the policy?")
    plan = planner.plan(request)
    deterministic = retriever.retrieve(plan, planner.context_values(request, plan))
    policy = next(item for item in retriever.candidates if item.source_ref.endswith("policy.html"))
    client_book = next(
        item for item in retriever.candidates if item.source_ref.endswith("client-book.html")
    )
    base = SemanticRetrievalOutcome(
        plan=plan,
        deterministic_result=deterministic,
        ranked_candidates=(client_book, policy),
        selected_candidates=(client_book, policy),
        deterministic_page_refs=(client_book.source_ref, policy.source_ref),
        hybrid_page_refs=(client_book.source_ref, policy.source_ref),
        initial_router=RouterResult(
            selections=(),
            attempted_page_refs=(),
            shortlist_page_refs=(),
            call=_call("title_router"),
            retry=False,
        ),
        retry_router=None,
        sufficiency=EvidenceSufficiency(
            status=SufficiencyStatus.SUFFICIENT,
            detail="test",
        ),
        retry_count=0,
        latency_ms=1.0,
    )
    semantic = SimpleNamespace(planner=planner, deterministic_retriever=retriever)
    application = apply_atlas_retrieval(
        semantic,  # type: ignore[arg-type]
        base,
        request,
        {},
        router,
    )
    assert "local://event-wiki/client-book.html" in application.atlas.excluded_page_refs
    assert "local://event-wiki/client-book.html" not in application.retrieval.hybrid_page_refs
    assert "local://event-wiki/procedure.html" in application.atlas.supporting_procedure_refs
    assert any(
        item.source_ref.endswith("procedure.html")
        for item in application.retrieval.ranked_candidates
    )


def test_task5_skeptic_prompt_receives_atlas_control_hints(tmp_path: Path) -> None:
    corpus = _write_corpus(tmp_path)

    class _SkepticClient:
        def __init__(self) -> None:
            self.prompt = ""

        def request_json(
            self,
            phase: str,
            response_model: type[Any],
            *,
            developer_prompt: str,
            user_prompt: str,
        ) -> tuple[Any, LLMCallRecord]:
            del phase, response_model, developer_prompt
            self.prompt = user_prompt
            return SkepticOutput(objections=[]), _call("skeptic")

    client = _SkepticClient()
    runtime = EventEvidenceReasoningRuntime(corpus, object(), client, object())  # type: ignore[arg-type]
    unit = next(unit for unit in corpus.provenance.units.values() if unit.kind == "sentence")
    claim = ValidatedClaim(
        claim_id="claim",
        text="The approved form is used.",
        evidence_refs=[unit.ref],
        supporting_spans=[SupportingSpan(evidence_ref=unit.ref, span=unit.text)],
        critical_control=False,
        applicable_scope={},
    )
    runtime._run_skeptic(
        QueryInput(query="Which form is used?"),
        ContextAssessment(intent="REFERENCE_LOOKUP"),
        [claim],
        [],
        [],
        expected_control_hints=["The approved form must be used."],
    )
    prompt = json.loads(client.prompt)
    assert prompt["expected_control_hints"] == ["The approved form must be used."]
