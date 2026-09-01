"""Tests for the public decision contract."""

import pytest
from pydantic import ValidationError

from riskon.models import (
    Decision,
    DetectedContext,
    Evidence,
    PipelineResult,
    ReasonCode,
    Route,
)


def _evidence() -> Evidence:
    return Evidence(
        section_id="synthetic::section-01",
        source_ref="local://synthetic/page.html",
        title="Synthetic page",
        heading_path=["Rule"],
        score=0.5,
        excerpt="A supported synthetic rule.",
        table_rows=[],
    )


def _route() -> Route:
    return Route(
        support_function="IT_SERVICE_DESK",
        expert_id="SYN-IT-001",
        routing_reason="Synthetic route",
        routing_confidence=1.0,
    )


def _base() -> dict:
    return {
        "trace_id": "trace-model",
        "answer_confidence": 0.0,
        "routing_confidence": 0.0,
        "confidence_kind": "DETERMINISTIC_GATE_PLACEHOLDER",
        "detected_context": DetectedContext(),
    }


def test_decision_values_are_exact() -> None:
    assert [decision.value for decision in Decision] == ["ANSWER", "CLARIFY", "ABSTAIN"]


def test_answer_contract_requires_evidence_and_forbids_route() -> None:
    base = _base()
    base["answer_confidence"] = 1.0
    result = PipelineResult(
        **base,
        decision=Decision.ANSWER,
        answer="Supported answer",
        evidence=[_evidence()],
    )
    assert result.route is None
    with pytest.raises(ValidationError):
        PipelineResult(**_base(), decision=Decision.ANSWER, answer="No evidence")


def test_clarify_contract_is_question_only() -> None:
    result = PipelineResult(
        **_base(),
        decision=Decision.CLARIFY,
        clarifying_question="Which channel?",
    )
    assert result.answer is None
    with pytest.raises(ValidationError):
        PipelineResult(
            **_base(),
            decision=Decision.CLARIFY,
            clarifying_question="Which channel?",
            answer="Speculation",
        )


def test_abstain_contract_requires_reason_and_route() -> None:
    result = PipelineResult(
        **_base(),
        decision=Decision.ABSTAIN,
        reason_codes=[ReasonCode.TECHNICAL_FAILURE],
        route=_route(),
    )
    assert result.answer is None
    with pytest.raises(ValidationError):
        PipelineResult(
            **_base(),
            decision=Decision.ABSTAIN,
            reason_codes=[ReasonCode.TECHNICAL_FAILURE],
        )
