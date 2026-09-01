"""M4D structured context and routing-envelope tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from m4d_helpers import baseline

from riskon.models import QueryInput
from riskon.orchestra.context_builder import build_orchestra_context
from riskon.orchestra.models import RiskAssessment, RiskSignal


def assessment(profile: str = "FAST_PATH") -> RiskAssessment:
    from riskon.orchestra.models import ActivationProfile

    return RiskAssessment(
        risk_signals=(),
        signal_sources={},
        selected_activation_profile=ActivationProfile(profile),
        profile_reason="test assessment",
    )


def test_answer_context_copies_only_structured_fields(tmp_path: Path) -> None:
    raw_query = "What is a private query that must not enter orchestration?"
    context = build_orchestra_context(
        QueryInput(
            query=raw_query,
            context={" region ": " REGION_BETA ", "routing_profile": "default", "": ""},
        ),
        baseline("M4D-041"),
        assessment(),
        default_routing_profile="fallback",
    )
    assert context.structured_context == {"region": "REGION_BETA"}
    assert context.routing_profile == "default"
    assert raw_query not in str(context.model_dump(mode="json"))
    assert context.routing_context is None
    assert context.requested_agent_roles == ()
    assert tmp_path.is_dir()  # keep the fixture path explicit in this isolated test


def test_abstain_context_builds_structured_routing_envelope(tmp_path: Path) -> None:
    value = QueryInput(
        query="Where can I submit the Synthetic Atlas exception request?",
        context={
            "routing_need_type": "POLICY_INTERPRETATION",
            "routing_topics": "atlas, exception | form",
            "jurisdiction": "CH",
            "region": "REGION_ALPHA",
            "system": "SYNTHETIC_PORTAL",
            "requester_team": "OPERATIONS",
            "routing_profile": "default",
        },
        trace_id="context-test",
    )
    context = build_orchestra_context(
        value,
        baseline("M4D-043"),
        RiskAssessment(
            risk_signals=(RiskSignal("UNRESOLVED_REQUIRED_REFERENCE"),),
            signal_sources={"UNRESOLVED_REQUIRED_REFERENCE": ("test",)},
            selected_activation_profile="HUMAN_FIRST",
            profile_reason="test abstention",
        ),
    )
    assert context.routing_context is not None
    assert context.routing_context.need_type.value == "POLICY_INTERPRETATION"
    assert context.routing_context.topics == ["atlas", "exception", "form"]
    assert context.routing_context.reason_codes[0].value == "UNRESOLVED_REQUIRED_REFERENCE"
    assert context.routing_context.jurisdiction == "CH"
    assert context.routing_context.region == "REGION_ALPHA"
    assert context.routing_context.system == "SYNTHETIC_PORTAL"
    assert context.routing_context.requester_team == "OPERATIONS"
    assert context.structured_context["routing_topics"] == "atlas, exception | form"
    assert context.routing_profile == "default"
    assert tmp_path.is_dir()


def test_abstain_context_uses_baseline_region_and_need_when_not_supplied() -> None:
    value = QueryInput(query="Where can I submit the Synthetic Atlas exception request?")
    context = build_orchestra_context(value, baseline("M4D-043"), assessment("HUMAN_FIRST"))
    assert context.routing_context is not None
    assert context.routing_context.region is None
    assert context.routing_context.topics == []


def test_context_rejects_invalid_structured_need_type() -> None:
    with pytest.raises(ValueError):
        build_orchestra_context(
            QueryInput(
                query="Where can I submit the Synthetic Atlas exception request?",
                context={"need_type": "not-a-need"},
            ),
            baseline("M4D-043"),
            assessment("HUMAN_FIRST"),
        )
