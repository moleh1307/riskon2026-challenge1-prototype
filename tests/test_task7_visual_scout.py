"""Contract tests for the bounded Task 7 visual path."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from riskon.event_eval.final_stabilization_probe import (
    Task7CaseResult,
    Task7Document,
    Task7Metrics,
    write_final_reports,
)
from riskon.event_runtime.corpus_loader import ingest_event_sections
from riskon.event_runtime.evidence_reasoning import EventEvidenceReasoningRuntime
from riskon.event_runtime.evidence_reasoning_models import (
    ContextAssessment,
    EvidenceAnalysisOutput,
    EvidenceClaim,
    EvidenceSufficiencyStatus,
    EvidenceUnit,
    SupportingSpan,
)
from riskon.event_runtime.llm_client import (
    VISUAL_SCOUT_MODEL,
    VISUAL_SCOUT_REASONING,
    EventOpenAIClient,
    LLMCallRecord,
    Task7LLMConfig,
)
from riskon.event_runtime.visual_scout import (
    VisualAnalysis,
    VisualScoutOutput,
    VisualSupport,
    VisualVerificationOutput,
    run_visual_scout,
    select_visual_assets,
    should_run_visual_scout,
)
from riskon.models import ManifestEntry, QueryInput
from riskon.orchestra.source_safety import LocalCorpus
from riskon.provenance import ProvenanceIndex

_PNG = b"\x89PNG\r\n\x1a\n" + b"task7-test-image"


def _corpus(tmp_path: Path) -> LocalCorpus:
    (tmp_path / "diagram.png").write_bytes(_PNG)
    source = tmp_path / "visual.html"
    source.write_text(
        "<html><body><h1>Product risk methodology</h1>"
        "<p>The methodology uses four control checks.</p>"
        '<img src="diagram.png" alt="Product risk methodology diagram" />'
        "</body></html>",
        encoding="utf-8",
    )
    entries = [
        ManifestEntry(
            filename="visual.html",
            title="Product risk methodology",
            url="local://event-wiki/visual.html",
            source_path=str(source),
        )
    ]
    sections = ingest_event_sections(entries)
    return LocalCorpus(
        sections=tuple(sections),
        provenance=ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2"),
        knowledge_root=tmp_path,
    )


def _retrieval(corpus: LocalCorpus) -> SimpleNamespace:
    section = corpus.sections[0]
    return SimpleNamespace(
        hybrid_page_refs=(section.source_ref,),
        ranked_candidates=(SimpleNamespace(source_ref=section.source_ref),),
        selected_candidates=(SimpleNamespace(source_ref=section.source_ref),),
    )


def _call(phase: str) -> LLMCallRecord:
    return LLMCallRecord(
        phase=phase,  # type: ignore[arg-type]
        model="test-model",
        reasoning_effort="medium",
        input_tokens=2,
        output_tokens=2,
        cached_input_tokens=0,
        latency_ms=1.0,
    )


class _VisualClient:
    def __init__(self, agrees: bool = True) -> None:
        self.agrees = agrees
        self.phases: list[str] = []
        self.prompts: list[str] = []

    def request_multimodal_json(
        self,
        phase: str,
        response_model: type[Any],
        *,
        developer_prompt: str,
        user_prompt: str,
        image_data_urls: list[str] | tuple[str, ...],
    ) -> tuple[Any, LLMCallRecord]:
        del developer_prompt
        self.phases.append(phase)
        self.prompts.append(user_prompt)
        assert 1 <= len(image_data_urls) <= 2
        payload = json.loads(user_prompt)
        if phase == "visual_scout":
            return (
                VisualScoutOutput(
                    observations=[
                        {
                            "asset_evidence_ref": payload["assets"][0]["asset_evidence_ref"],
                            "visual_observations": ["The diagram shows four control checks."],
                            "answer_relevant_facts": ["The diagram shows four control checks."],
                            "uncertainty": "The labels are legible.",
                            "confidence": 0.95,
                            "visual_sufficient": True,
                        }
                    ]
                ),
                _call(phase),
            )
        assert response_model is VisualVerificationOutput
        return (
            VisualVerificationOutput(
                asset_evidence_ref=payload["asset_evidence_ref"],
                agrees=self.agrees,
                verified_facts=["The diagram shows four control checks."],
                uncertainty="The labels are legible." if self.agrees else "The diagram is unclear.",
                confidence=0.95 if self.agrees else 0.4,
                visual_sufficient=self.agrees,
            ),
            _call(phase),
        )


def test_visual_asset_selection_is_local_bounded_and_context_bound(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    assets = select_visual_assets(corpus, _retrieval(corpus))

    assert len(assets) == 1
    assert assets[0].asset_evidence_ref.endswith("#asset-1")
    assert assets[0].path == (tmp_path / "diagram.png").resolve()
    assert assets[0].data_url.startswith("data:image/png;base64,")
    assert assets[0].nearby_evidence_refs
    assert "four control checks" in assets[0].nearby_context


def test_visual_asset_selection_skips_inline_data_uri(tmp_path: Path) -> None:
    source = tmp_path / "inline.html"
    source.write_text(
        "<html><body><h1>Inline visual</h1>"
        '<img src="data:image/svg+xml;charset=utf-8,'
        + ("x" * 5000)
        + '" alt="inline diagram" /></body></html>',
        encoding="utf-8",
    )
    entry = ManifestEntry(
        filename="inline.html",
        title="Inline visual",
        url="local://event-wiki/inline.html",
        source_path=str(source),
    )
    sections = ingest_event_sections([entry])
    corpus = LocalCorpus(
        sections=tuple(sections),
        provenance=ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2"),
        knowledge_root=tmp_path,
    )

    assert select_visual_assets(corpus, _retrieval(corpus)) == ()


def test_visual_scout_requires_independent_agreement() -> None:
    asset = SimpleNamespace(
        asset_evidence_ref="local://event-wiki/visual.html#asset-1",
        source_ref="local://event-wiki/visual.html",
        title="Product risk methodology",
        heading_path=("Product risk methodology",),
        alt="Product risk methodology diagram",
        data_url="data:image/png;base64,dGVzdA==",
        nearby_evidence_refs=("local://event-wiki/visual.html#section-product-risk-methodology",),
        nearby_context="Heading: Product risk methodology\nText: Four control checks.",
    )
    client = _VisualClient()
    result = run_visual_scout(client, "How many control checks?", [asset])

    assert result.primary_call_used
    assert result.verification_call_used
    assert result.usable
    assert client.phases == ["visual_scout", "visual_verification"]

    disagreement = run_visual_scout(_VisualClient(agrees=False), "How many?", [asset])
    assert not disagreement.usable
    assert disagreement.failure_reason == "VISUAL_VERIFICATION_AMBIGUOUS"


def test_visual_scout_triggers_when_text_analysis_has_no_direct_support() -> None:
    analysis = EvidenceAnalysisOutput(
        evidence_sufficiency=EvidenceSufficiencyStatus.NO_DIRECT_SUPPORT,
        material_claims=[],
        unresolved_issues=["The answer is only visible in the supplied image."],
    )
    unit = EvidenceUnit(
        evidence_ref="local://event-wiki/visual.html#section-product-risk-methodology",
        kind="sentence",
        source_ref="local://event-wiki/visual.html",
        title="Product risk methodology",
        filename="visual.html",
        text="The surrounding text does not state the requested value.",
    )

    assert should_run_visual_scout(analysis, [unit])


def test_visual_claim_validation_accepts_only_verified_exact_visual_fact(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    runtime = EventEvidenceReasoningRuntime(corpus, object(), object(), object())  # type: ignore[arg-type]
    section_unit = next(unit for unit in corpus.provenance.units.values() if unit.kind == "section")
    asset_unit = next(unit for unit in corpus.provenance.units.values() if unit.kind == "asset")
    section = EvidenceUnit(
        evidence_ref=section_unit.ref,
        kind=section_unit.kind,
        source_ref=section_unit.source_ref,
        title="Product risk methodology",
        filename=section_unit.filename,
        heading_path=list(section_unit.heading_path),
        text=section_unit.text,
        scope=dict(section_unit.scope),
    )
    asset = EvidenceUnit(
        evidence_ref=asset_unit.ref,
        kind=asset_unit.kind,
        source_ref=asset_unit.source_ref,
        title="Product risk methodology",
        filename=asset_unit.filename,
        heading_path=list(asset_unit.heading_path),
        text=asset_unit.text,
        contains_visual=True,
    )
    fact = "The diagram shows four control checks."
    claim = EvidenceClaim(
        claim_id="visual-claim",
        claim_text=fact,
        evidence_refs=[section.evidence_ref, asset.evidence_ref],
        supporting_spans=[
            SupportingSpan(evidence_ref=section.evidence_ref, span=section.text),
            SupportingSpan(evidence_ref=asset.evidence_ref, span=fact),
        ],
        critical_control=False,
        applicable_scope=[],
    )
    analysis = EvidenceAnalysisOutput(
        evidence_sufficiency=EvidenceSufficiencyStatus.SUFFICIENT,
        material_claims=[claim],
        unresolved_issues=[],
    )
    support = VisualSupport(
        asset_evidence_ref=asset.evidence_ref,
        source_ref=asset.source_ref,
        nearby_evidence_refs=(section.evidence_ref,),
        visual_observations=(fact,),
        answer_relevant_facts=(fact,),
        uncertainty="None.",
        confidence=0.95,
        visual_sufficient=True,
        verified=True,
        verification_agrees=True,
    )
    validation = runtime._validate_claims(
        QueryInput(query="How many control checks?"),
        ContextAssessment(intent="REFERENCE_LOOKUP"),
        analysis,
        [section, asset],
        visual_analysis=VisualAnalysis(supports=(support,), primary_call_used=True),
    )

    assert len(validation.valid_claims) == 1
    assert validation.errors == []


def test_event_client_uses_fixed_visual_policy_and_structured_input() -> None:
    class _Response:
        output_text = json.dumps(
            {
                "observations": [
                    {
                        "asset_evidence_ref": "local://event-wiki/page.html#asset-1",
                        "visual_observations": ["A diagram."],
                        "answer_relevant_facts": [],
                        "uncertainty": "None.",
                        "confidence": 1.0,
                        "visual_sufficient": False,
                    }
                ]
            }
        )
        usage = SimpleNamespace(input_tokens=3, output_tokens=4, input_tokens_details=None)

    class _Responses:
        def __init__(self) -> None:
            self.kwargs: dict[str, Any] = {}

        def create(self, **kwargs: Any) -> _Response:
            self.kwargs = kwargs
            return _Response()

    responses = _Responses()
    client = EventOpenAIClient(config=Task7LLMConfig(), client=SimpleNamespace(responses=responses))
    output, call = client.request_multimodal_json(
        "visual_scout",
        VisualScoutOutput,
        developer_prompt="developer",
        user_prompt="{}",
        image_data_urls=["data:image/png;base64,dGVzdA=="],
    )

    assert output.observations[0].asset_evidence_ref.endswith("asset-1")
    assert call.model == VISUAL_SCOUT_MODEL
    assert call.reasoning_effort == VISUAL_SCOUT_REASONING
    assert responses.kwargs["store"] is False
    assert responses.kwargs["input"][1]["content"][1]["type"] == "input_image"
    assert client.usage.visual_scout_calls == 1


def test_final_stabilization_report_preserves_case_and_safety_metadata(tmp_path: Path) -> None:
    metrics = Task7Metrics(
        cases_executed=1,
        decision_match_count=1,
        answer_count=1,
        clarify_count=0,
        abstain_count=0,
        correct_clarification_count=0,
        final_citation_valid_count=1,
        final_citation_validity=1.0,
        unsupported_released_claims=0,
        scope_violation_count=0,
        released_answer_scope_violations=0,
        critical_control_omission_count=0,
        released_answer_critical_control_omissions=0,
        visual_case_count=0,
        visual_case_decision_match_count=0,
        verified_visual_support_count=0,
        routing_count=0,
        retry_count=0,
        visual_call_count=0,
        visual_verification_call_count=0,
        runtime_error_count=0,
        median_latency_ms=12.5,
        llm_calls=3,
        input_tokens=100,
        output_tokens=25,
        cached_input_tokens=10,
        total_llm_latency_ms=30.0,
        hard_gates_passed=True,
    )
    case = Task7CaseResult(
        case_id="TEST-01",
        expected_behavior="ANSWER",
        actual_decision="ANSWER",
        decision_match=True,
        expected_source_title_contains=["Policy"],
        source_titles=["Policy"],
        primary_source="Policy",
        answer_or_clarification="The released claim.",
        modality="text",
        material_objection_count=0,
        remaining_objection_or_failure=None,
        final_failure_reason=None,
        final_citation_valid=True,
        unsupported_released_claims=0,
        scope_violation_count=0,
        released_answer_scope_violations=0,
        critical_control_omission_count=0,
        released_answer_critical_control_omissions=0,
        routing_count=0,
        latency_ms=12.5,
    )
    document = Task7Document(
        schema_version="1.0",
        suite="RISKON_CHALLENGE_1",
        task="TASK_7_FINAL_STABILIZATION",
        metrics=metrics,
        cases=[case],
        fixed_policy={"visual_scout": "gpt-5.6-sol/medium"},
        page_cards_reused=339,
        atlas_pages_reused=339,
        metadata_is_not_evidence=True,
        deterministic_answer_firewall_authoritative=True,
        network_enabled=False,
        event_data_copied=False,
    )

    paths = write_final_reports(document, tmp_path / "final")

    assert all(path.is_file() for path in paths.values())
    payload = json.loads(paths["evaluation"].read_text(encoding="utf-8"))
    assert payload["metadata_is_not_evidence"] is True
    assert payload["deterministic_answer_firewall_authoritative"] is True
    assert payload["cases"][0]["case_id"] == "TEST-01"
    assert "Decision match: 1/17" in paths["summary"].read_text(encoding="utf-8")
