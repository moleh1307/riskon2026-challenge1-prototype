"""Frozen M4D activation precedence and profile-boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from m4d_helpers import M4D_ROOT, PROJECT_ROOT, pipeline

from riskon.config import load_milestone4d_config
from riskon.models import Decision
from riskon.orchestra.models import ActivationProfile, RiskSignal
from riskon.orchestra.risk_signals import OrchestraRiskSignalDetector
from riskon.orchestra.runtime_policy import RuntimePolicy


def detector() -> OrchestraRiskSignalDetector:
    return OrchestraRiskSignalDetector(
        RuntimePolicy.from_file(M4D_ROOT / "runtime_policy.json"),
        implemented_dimensions=("region", "service_model"),
    )


@pytest.mark.parametrize(
    ("decision", "signals", "expected"),
    [
        (Decision.CLARIFY, (), ActivationProfile.SHORT_CIRCUIT_CLARIFY),
        (Decision.ANSWER, ("BASELINE_CLARIFY",), ActivationProfile.SHORT_CIRCUIT_CLARIFY),
        (Decision.ABSTAIN, ("UNRESOLVED_REQUIRED_REFERENCE",), ActivationProfile.HUMAN_FIRST),
        (Decision.ANSWER, ("SCOPE_SENSITIVE",), ActivationProfile.FULL_ORCHESTRA),
        (Decision.ANSWER, ("CRITICAL_CONTROL_RISK",), ActivationProfile.DUAL_CHECK),
        (Decision.ANSWER, (), ActivationProfile.FAST_PATH),
        (Decision.ABSTAIN, (), ActivationProfile.HUMAN_FIRST),
        (Decision.ANSWER, ("APPROVAL_REQUIRED",), ActivationProfile.DUAL_CHECK),
    ],
)
def test_profile_precedence_is_closed_and_deterministic(
    decision: Decision,
    signals: tuple[str, ...],
    expected: ActivationProfile,
) -> None:
    actual, reason = detector()._select_profile(
        decision, tuple(RiskSignal(signal) for signal in signals)
    )
    assert actual is expected
    assert reason


@pytest.mark.parametrize(
    ("decision", "signals", "expected"),
    [
        (
            Decision.ANSWER,
            ("SCOPE_SENSITIVE", "CRITICAL_CONTROL_RISK"),
            ActivationProfile.FULL_ORCHESTRA,
        ),
        (
            Decision.ABSTAIN,
            ("UNRESOLVED_REQUIRED_REFERENCE", "SCOPE_SENSITIVE"),
            ActivationProfile.HUMAN_FIRST,
        ),
        (
            Decision.ANSWER,
            ("BASELINE_CLARIFY", "SCOPE_SENSITIVE"),
            ActivationProfile.SHORT_CIRCUIT_CLARIFY,
        ),
        (
            Decision.ANSWER,
            ("MULTI_PART_QUERY", "LOW_RETRIEVAL_MARGIN"),
            ActivationProfile.DUAL_CHECK,
        ),
    ],
)
def test_higher_precedence_wins_regardless_of_signal_input_order(
    decision: Decision, signals: tuple[str, ...], expected: ActivationProfile
) -> None:
    reversed_signals = tuple(RiskSignal(signal) for signal in reversed(signals))
    profile, _reason = detector()._select_profile(decision, reversed_signals)
    assert profile is expected


def test_runtime_policy_matches_frozen_activation_precedence() -> None:
    config = load_milestone4d_config(PROJECT_ROOT / "config" / "milestone4d.toml")
    assert config.orchestra.m4d.auto_activation_enabled is True
    assert config.orchestra.m4d.default_routing_profile == "default"
    assert config.base.orchestra.m4c.implemented_dimensions == [
        "region",
        "service_model",
    ]


def test_legacy_pipelines_do_not_expose_live_m4d_method() -> None:
    from riskon.config import load_milestone3_config
    from riskon.pipeline import RiskonPipeline

    legacy = RiskonPipeline.from_milestone3_config(
        load_milestone3_config(PROJECT_ROOT / "config" / "milestone3.toml")
    )
    assert not hasattr(legacy, "run_orchestrated")


def test_m4d_pipeline_exposes_only_the_additive_live_method(tmp_path: Path) -> None:
    m4d = pipeline(tmp_path)
    assert hasattr(m4d, "run_orchestrated")
    assert m4d._m4d_runtime is not None
