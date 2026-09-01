"""Contract tests for the bounded Task 5 evidence-reasoning firewall."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from riskon.event_runtime.corpus_loader import ingest_event_sections
from riskon.event_runtime.evidence_reasoning import (
    EventEvidenceReasoningRuntime,
    _validated_claim,
)
from riskon.event_runtime.evidence_reasoning_models import (
    CLAIM_BUILDER_MODEL,
    CLAIM_BUILDER_REASONING,
    CONTEXT_INTERPRETER_MODEL,
    CONTEXT_INTERPRETER_REASONING,
    SKEPTIC_MODEL,
    SKEPTIC_REASONING,
    ContextAssessment,
    ContextInterpreterOutput,
    EvidenceAnalysisOutput,
    EvidenceClaim,
    EvidenceSufficiencyStatus,
    EvidenceUnit,
    SkepticOutput,
    SupportingSpan,
)
from riskon.event_runtime.llm_client import (
    PAGE_CARD_MODEL,
    PAGE_CARD_REASONING,
    ROUTER_RETRY_MODEL,
    ROUTER_RETRY_REASONING,
    TITLE_ROUTER_MODEL,
    TITLE_ROUTER_REASONING,
    EventOpenAIClient,
    LLMCallRecord,
    Task5LLMConfig,
)
from riskon.hybrid_retrieval import RetrievalCandidate
from riskon.models import (
    Decision,
    DetectedContext,
    ManifestEntry,
    QueryInput,
)
from riskon.orchestra.source_safety import LocalCorpus
from riskon.provenance import ProvenanceIndex


def _corpus(tmp_path: Path, count: int = 1) -> LocalCorpus:
    entries: list[ManifestEntry] = []
    for index in range(count):
        filename = f"page-{index}.html"
        source = tmp_path / filename
        source.write_text(
            f"<html><body><h1>Page {index}</h1><p>Policy requires a signed form for target "
            f"{index}. "
            "Additional source text keeps the evidence bounded.</p></body></html>",
            encoding="utf-8",
        )
        entries.append(
            ManifestEntry(
                filename=filename,
                title=f"Page {index}",
                url=f"local://event-wiki/{filename}",
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


def _runtime(corpus: LocalCorpus) -> EventEvidenceReasoningRuntime:
    return EventEvidenceReasoningRuntime(corpus, object(), object(), object())  # type: ignore[arg-type]


def _unit(corpus: LocalCorpus) -> EvidenceUnit:
    source = next(unit for unit in corpus.provenance.units.values() if unit.kind == "sentence")
    return EvidenceUnit(
        evidence_ref=source.ref,
        kind=source.kind,
        source_ref=source.source_ref,
        title="Test page",
        filename=source.filename,
        heading_path=list(source.heading_path),
        text=source.text,
        headers=list(source.headers),
        row=list(source.row),
        scope=dict(source.scope),
    )


def _call(phase: str) -> LLMCallRecord:
    return LLMCallRecord(
        phase=phase,  # type: ignore[arg-type]
        model="test-model",
        reasoning_effort="none",
        input_tokens=1,
        output_tokens=1,
        cached_input_tokens=0,
        latency_ms=1.0,
    )


def test_task5_fixed_policy_and_strict_response_schemas() -> None:
    assert (PAGE_CARD_MODEL, PAGE_CARD_REASONING) == ("gpt-5.6-luna", "none")
    assert (TITLE_ROUTER_MODEL, TITLE_ROUTER_REASONING) == ("gpt-5.6-terra", "low")
    assert (ROUTER_RETRY_MODEL, ROUTER_RETRY_REASONING) == ("gpt-5.6-terra", "medium")
    assert (CONTEXT_INTERPRETER_MODEL, CONTEXT_INTERPRETER_REASONING) == (
        "gpt-5.6-luna",
        "low",
    )
    assert (CLAIM_BUILDER_MODEL, CLAIM_BUILDER_REASONING) == ("gpt-5.6-terra", "medium")
    assert (SKEPTIC_MODEL, SKEPTIC_REASONING) == ("gpt-5.6-terra", "medium")
    assert "sol" not in str(EventOpenAIClient._specs).casefold()

    for response_model in (ContextInterpreterOutput, EvidenceAnalysisOutput, SkepticOutput):
        schema = response_model.model_json_schema()
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])

    config = Task5LLMConfig()
    assert config.max_evidence_units == 8
    assert config.max_evidence_chars == 12_000
    assert config.max_nearby_units == 2
    assert config.max_claims == 8


def test_responses_client_uses_fixed_structured_call_without_storage() -> None:
    class _Responses:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def create(self, **kwargs: Any) -> Any:
            self.calls.append(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "intent": "REFERENCE_LOOKUP",
                        "explicitly_supplied_context": [],
                        "answer_changing_context_fields": [],
                        "missing_context_fields": [],
                        "ambiguity_acronym_flags": [],
                    }
                ),
                usage=SimpleNamespace(input_tokens=2, output_tokens=3),
            )

    responses = _Responses()
    client = EventOpenAIClient(Task5LLMConfig(), client=SimpleNamespace(responses=responses))
    output, record = client.request_json(
        "context_interpreter",
        ContextInterpreterOutput,
        developer_prompt="developer",
        user_prompt="user",
    )

    request = responses.calls[0]
    assert output.intent == "REFERENCE_LOOKUP"
    assert record.model == CONTEXT_INTERPRETER_MODEL
    assert request["model"] == CONTEXT_INTERPRETER_MODEL
    assert request["reasoning"] == {"effort": "low"}
    assert request["store"] is False
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True
    assert request["text"]["format"]["name"] == "riskon_context_interpreter"


def test_claim_validation_requires_local_refs_and_literal_spans(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    runtime = _runtime(corpus)
    evidence = _unit(corpus)
    context = ContextAssessment(intent="REFERENCE_LOOKUP")
    valid = EvidenceClaim(
        claim_id="valid",
        claim_text="The policy requires a signed form for target 0.",
        evidence_refs=[evidence.evidence_ref],
        supporting_spans=[
            SupportingSpan(evidence_ref=evidence.evidence_ref, span=evidence.text),
        ],
        critical_control=True,
        applicable_scope=[],
    )
    invalid_span = EvidenceClaim(
        claim_id="invalid-span",
        claim_text="The policy requires a signed contract for target 0.",
        evidence_refs=[evidence.evidence_ref],
        supporting_spans=[
            SupportingSpan(evidence_ref=evidence.evidence_ref, span="not in original evidence"),
        ],
        critical_control=False,
        applicable_scope=[],
    )
    invalid_ref = EvidenceClaim(
        claim_id="invalid-ref",
        claim_text="The policy requires a signed form.",
        evidence_refs=["https://example.invalid/evidence"],
        supporting_spans=[
            SupportingSpan(
                evidence_ref="https://example.invalid/evidence",
                span="The policy requires a signed form.",
            ),
        ],
        critical_control=False,
        applicable_scope=[],
    )
    analysis = EvidenceAnalysisOutput(
        evidence_sufficiency=EvidenceSufficiencyStatus.SUFFICIENT,
        material_claims=[valid, invalid_span, invalid_ref],
        unresolved_issues=[],
    )

    validation = runtime._validate_claims(
        QueryInput(query="policy target"),
        context,
        analysis,
        [evidence],
    )

    assert [claim.claim_id for claim in validation.valid_claims] == ["valid"]
    assert validation.rejected_claim_ids == ["invalid-span", "invalid-ref"]
    assert validation.broken_reference_count == 1
    assert any("not literal" in error for error in validation.errors)
    assert any("unresolved" in error for error in validation.errors)


def test_evidence_budget_is_bounded_and_page_cards_are_not_prompt_evidence(
    tmp_path: Path,
) -> None:
    corpus = _corpus(tmp_path, count=12)
    runtime = _runtime(corpus)
    candidates: list[RetrievalCandidate] = []
    for section in corpus.sections:
        section_ref = corpus.provenance.section_ref(section)
        candidates.append(
            RetrievalCandidate(
                candidate_ref=section_ref,
                section_id=section.section_id,
                source_ref=section.source_ref,
                title=section.title,
                heading_path=tuple(section.heading_path),
                excerpt=section.text,
                table_rows=(),
                unit_refs=(section_ref,),
                claim_ids=(),
                scope=tuple(section.scope.items()),
                is_table_row=False,
                is_attachment=False,
            )
        )
    retrieval = SimpleNamespace(
        selected_candidates=tuple(candidates),
        ranked_candidates=tuple(candidates),
        deterministic_result=SimpleNamespace(selected_candidates=()),
        plan=SimpleNamespace(
            normalised_query="policy target",
            canonical_terms=["policy", "target"],
        ),
    )
    units = runtime._evidence_units(QueryInput(query="policy target"), retrieval)
    assert len(units) <= 8
    assert sum(len(unit.text) for unit in units) <= 12_000
    assert all(unit.evidence_ref.startswith("local://event-wiki/") for unit in units)

    class _AnalysisClient:
        def __init__(self) -> None:
            self.user_prompts: list[str] = []

        def request_json(
            self,
            phase: str,
            response_model: type[Any],
            *,
            developer_prompt: str,
            user_prompt: str,
        ) -> tuple[Any, LLMCallRecord]:
            del phase, response_model, developer_prompt
            self.user_prompts.append(user_prompt)
            return (
                EvidenceAnalysisOutput(
                    evidence_sufficiency=EvidenceSufficiencyStatus.NO_DIRECT_SUPPORT,
                    material_claims=[],
                    unresolved_issues=[],
                ),
                _call("claim_builder"),
            )

    client = _AnalysisClient()
    runtime.client = client  # type: ignore[assignment]
    runtime._analyze(
        QueryInput(query="policy target"),
        SimpleNamespace(
            intent=SimpleNamespace(value="REFERENCE_LOOKUP"),
            normalised_query="policy target",
            canonical_terms=["policy", "target"],
        ),
        ContextAssessment(intent="REFERENCE_LOOKUP"),
        units,
    )
    payload = json.loads(client.user_prompts[0])
    assert "page_cards" not in payload
    assert "router_output" not in payload
    assert len(payload["evidence_units"]) <= 8


def test_firewall_releases_only_validated_claim_text(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    runtime = _runtime(corpus)
    evidence = _unit(corpus)
    valid = EvidenceClaim(
        claim_id="valid",
        claim_text="The policy requires a signed form for target 0.",
        evidence_refs=[evidence.evidence_ref],
        supporting_spans=[SupportingSpan(evidence_ref=evidence.evidence_ref, span=evidence.text)],
        critical_control=True,
        applicable_scope=[],
    )
    rejected = EvidenceClaim(
        claim_id="rejected",
        claim_text="The policy authorizes cryptocurrency trading.",
        evidence_refs=[evidence.evidence_ref],
        supporting_spans=[SupportingSpan(evidence_ref=evidence.evidence_ref, span=evidence.text)],
        critical_control=False,
        applicable_scope=[],
    )
    analysis = EvidenceAnalysisOutput(
        evidence_sufficiency=EvidenceSufficiencyStatus.SUFFICIENT,
        material_claims=[valid, rejected],
        unresolved_issues=[],
    )
    validation = runtime._validate_claims(
        QueryInput(query="policy target"),
        ContextAssessment(intent="REFERENCE_LOOKUP"),
        analysis,
        [evidence],
    )
    approved = tuple(_validated_claim(claim) for claim in validation.valid_claims)
    decision, answer, *_rest = runtime._firewall(
        QueryInput(query="policy target"),
        DetectedContext(),
        ContextAssessment(intent="REFERENCE_LOOKUP"),
        SimpleNamespace(plan=SimpleNamespace(normalised_query="policy target")),
        analysis,
        [evidence],
        validation,
        approved,
        SkepticOutput(objections=[]),
    )
    assert decision is Decision.ANSWER
    assert answer == "The policy requires a signed form for target 0."
    assert "cryptocurrency" not in (answer or "")


__all__ = []
