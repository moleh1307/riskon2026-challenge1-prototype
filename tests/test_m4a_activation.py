"""Tests for M4A profile and baseline activation validation."""

import json
from pathlib import Path

import pytest

from riskon.models import Decision, PlannedVerifiedRun, RoutingContext
from riskon.orchestra.activation import M4A_SUPPORTED_PROFILES, validate_m4a_activation
from riskon.orchestra.models import ActivationProfile, OrchestraContext, RiskSignal
from riskon.orchestra.policy import ActivationPolicy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"


def load_planned(case_id: str) -> PlannedVerifiedRun:
    """Load one frozen planned run."""

    raw = json.loads((M4_ROOT / "upstream_runs" / f"{case_id}.planned.json").read_text())
    return PlannedVerifiedRun.model_validate(raw["planned_verified_run"])


def context_for(
    case_id: str,
    signals: tuple[RiskSignal, ...],
    routing_context: RoutingContext | None,
) -> OrchestraContext:
    """Build a context for an activation test."""

    return OrchestraContext(
        risk_signals=signals,
        routing_context=routing_context,
        routing_profile="default",
    )


def test_supported_profiles_are_exactly_the_zero_worker_profiles() -> None:
    assert M4A_SUPPORTED_PROFILES == (
        ActivationProfile.FAST_PATH,
        ActivationProfile.SHORT_CIRCUIT_CLARIFY,
        ActivationProfile.HUMAN_FIRST,
    )


def test_valid_fast_short_and_human_activation() -> None:
    policy = ActivationPolicy.from_file(M4_ROOT / "activation_policy.json")
    fast = load_planned("M4-029")
    assert (
        validate_m4a_activation(
            policy,
            ActivationProfile.FAST_PATH,
            fast.verified_run.result.decision,
            context_for("M4-029", (), None),
        )
        is ActivationProfile.FAST_PATH
    )

    short = load_planned("M4-033")
    assert (
        validate_m4a_activation(
            policy,
            ActivationProfile.SHORT_CIRCUIT_CLARIFY,
            short.verified_run.result.decision,
            context_for("M4-033", (RiskSignal("AMBIGUOUS_ACRONYM"),), None),
        )
        is ActivationProfile.SHORT_CIRCUIT_CLARIFY
    )

    human = load_planned("M4-034")
    result = human.verified_run.result
    routing_context = RoutingContext(
        need_type=result.detected_context.need_type,
        reason_codes=list(result.reason_codes),
        region=result.detected_context.region,
    )
    assert (
        validate_m4a_activation(
            policy,
            "HUMAN_FIRST",
            result.decision,
            context_for("M4-034", (RiskSignal("UNRESOLVED_REQUIRED_REFERENCE"),), routing_context),
        )
        is ActivationProfile.HUMAN_FIRST
    )


def test_activation_rejects_decision_context_and_trigger_mismatches() -> None:
    policy = ActivationPolicy.from_file(M4_ROOT / "activation_policy.json")
    with pytest.raises(ValueError, match="baseline ANSWER"):
        validate_m4a_activation(
            policy,
            "FAST_PATH",
            Decision.CLARIFY,
            context_for("bad-fast", (), None),
        )
    with pytest.raises(ValueError, match="baseline CLARIFY"):
        validate_m4a_activation(
            policy,
            "SHORT_CIRCUIT_CLARIFY",
            Decision.ANSWER,
            context_for("bad-short", (RiskSignal("AMBIGUOUS_ACRONYM"),), None),
        )
    with pytest.raises(ValueError, match="routing_context=None"):
        validate_m4a_activation(
            policy,
            "FAST_PATH",
            Decision.ANSWER,
            context_for("bad-context", (), RoutingContext(need_type="UNKNOWN", reason_codes=[])),
        )
    with pytest.raises(ValueError, match="routing_context"):
        validate_m4a_activation(
            policy,
            "HUMAN_FIRST",
            Decision.ABSTAIN,
            context_for("bad-human", (RiskSignal("APPROVAL_REQUIRED"),), None),
        )
    with pytest.raises(ValueError, match="declared trigger"):
        validate_m4a_activation(
            policy,
            "HUMAN_FIRST",
            Decision.ABSTAIN,
            context_for(
                "bad-trigger",
                (RiskSignal("BASELINE_CLARIFY"),),
                RoutingContext(need_type="UNKNOWN", reason_codes=[]),
            ),
        )


def test_activation_covers_all_fail_closed_profile_guards() -> None:
    policy = ActivationPolicy.from_file(M4_ROOT / "activation_policy.json")
    routing = RoutingContext(need_type="UNKNOWN", reason_codes=[])
    with pytest.raises(ValueError, match="empty risk_signals"):
        validate_m4a_activation(
            policy,
            "FAST_PATH",
            Decision.ANSWER,
            context_for("fast-signal", (RiskSignal("APPROVAL_REQUIRED"),), None),
        )
    with pytest.raises(ValueError, match="routing_context=None"):
        validate_m4a_activation(
            policy,
            "SHORT_CIRCUIT_CLARIFY",
            Decision.CLARIFY,
            context_for("short-routing", (RiskSignal("AMBIGUOUS_ACRONYM"),), routing),
        )
    with pytest.raises(ValueError, match="declared trigger"):
        validate_m4a_activation(
            policy,
            "SHORT_CIRCUIT_CLARIFY",
            Decision.CLARIFY,
            context_for("short-trigger", (RiskSignal("APPROVAL_REQUIRED"),), None),
        )
    with pytest.raises(ValueError, match="baseline ABSTAIN"):
        validate_m4a_activation(
            policy,
            "HUMAN_FIRST",
            Decision.CLARIFY,
            context_for("human-decision", (RiskSignal("APPROVAL_REQUIRED"),), routing),
        )
    with pytest.raises(ValueError, match="routing_context"):
        validate_m4a_activation(
            policy,
            "HUMAN_FIRST",
            Decision.ABSTAIN,
            context_for("human-context", (RiskSignal("APPROVAL_REQUIRED"),), None),
        )
    with pytest.raises(ValueError, match="declared trigger"):
        validate_m4a_activation(
            policy,
            "HUMAN_FIRST",
            Decision.ABSTAIN,
            context_for("human-trigger", (RiskSignal("AMBIGUOUS_ACRONYM"),), routing),
        )
