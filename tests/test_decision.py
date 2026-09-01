"""Decision engine tests."""

import pytest

from riskon.decision import DecisionEngine
from riskon.models import EvidenceCheck, ReasonCode


def test_decision_priority_is_clarify_then_abstain_then_answer() -> None:
    engine = DecisionEngine()
    assert engine.decide(EvidenceCheck(missing_context=["channel"])).value == "CLARIFY"
    assert engine.decide(EvidenceCheck(reason_codes=[ReasonCode.OPEN_EVIDENCE])).value == "ABSTAIN"
    assert engine.decide(EvidenceCheck()).value == "ANSWER"


def test_exact_channel_clarification_and_unknown_field_fallback() -> None:
    engine = DecisionEngine()
    assert engine.clarifying_question(EvidenceCheck(missing_context=["channel"])) == (
        "Did the alert arise during an interactive advice session or during "
        "overnight portfolio monitoring?"
    )
    assert engine.clarifying_question(EvidenceCheck(missing_context=["role"])) == (
        "Please provide the missing context: role."
    )
    with pytest.raises(ValueError):
        engine.clarifying_question(EvidenceCheck())
