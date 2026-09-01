"""Automatic M4D risk-signal detection and provenance tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from m4d_helpers import baseline, pipeline, request
from pydantic import ValidationError

from riskon.models import Decision
from riskon.orchestra.models import RiskSignal
from riskon.orchestra.risk_signals import OrchestraRiskSignalDetector
from riskon.orchestra.source_safety import SourceSafetyDiagnostic, SourceSafetyReport


@pytest.mark.parametrize(
    ("case_id", "signals", "profile"),
    [
        ("M4D-041", [], "FAST_PATH"),
        ("M4D-042", ["BASELINE_CLARIFY", "AMBIGUOUS_ACRONYM"], "SHORT_CIRCUIT_CLARIFY"),
        ("M4D-043", ["UNRESOLVED_REQUIRED_REFERENCE"], "HUMAN_FIRST"),
        ("M4D-044", ["CRITICAL_CONTROL_RISK"], "DUAL_CHECK"),
        (
            "M4D-045",
            ["SCOPE_SENSITIVE", "SERVICE_MODEL_SENSITIVE", "COUNTERFACTUAL_REQUIRED"],
            "FULL_ORCHESTRA",
        ),
    ],
)
def test_detector_matches_all_five_automatic_activation_cases(
    tmp_path: Path,
    case_id: str,
    signals: list[str],
    profile: str,
) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    baseline_run = runtime_pipeline.run_planned(request(case_id))
    assessment = runtime.detector.assess(
        request(case_id), baseline_run, runtime._source_safety().report
    )
    assert [str(signal) for signal in assessment.risk_signals] == signals
    assert assessment.selected_activation_profile.value == profile
    assert assessment.profile_reason
    assert set(assessment.signal_sources) == set(signals)
    assert all(source for sources in assessment.signal_sources.values() for source in sources)


def test_assessment_is_frozen_and_does_not_share_mutable_signal_sources(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    req = request("M4D-045")
    assessment = runtime.detector.assess(
        req, runtime_pipeline.run_planned(req), runtime._source_safety().report
    )
    with pytest.raises(ValidationError):
        assessment.profile_reason = "changed"  # type: ignore[misc]
    copied = assessment.model_copy(deep=True)
    copied.signal_sources["SCOPE_SENSITIVE"] = ("changed",)
    assert assessment.signal_sources["SCOPE_SENSITIVE"] != ("changed",)


def test_prompt_injection_diagnostic_is_a_dual_check_signal(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    req = request("M4D-041")
    source_safety = SourceSafetyReport(
        unsafe_refs=frozenset(),
        diagnostics=(
            SourceSafetyDiagnostic(
                diagnostic_code="SOURCE_INSTRUCTION_IGNORED",
                evidence_refs=("local://synthetic-m4d/stability_marker_definition.html",),
            ),
        ),
    )
    assessment = runtime.detector.assess(req, baseline("M4D-041"), source_safety)
    assert [str(signal) for signal in assessment.risk_signals] == ["PROMPT_INJECTION_SIGNAL"]
    assert assessment.selected_activation_profile.value == "DUAL_CHECK"


def test_detector_helpers_cover_scope_normalisation_and_claim_guards() -> None:
    assert OrchestraRiskSignalDetector._scope_value_present(
        "Region Beta", "scope region_beta service_basic", "region"
    )
    assert OrchestraRiskSignalDetector._scope_value_present(
        "Service Basic", "service_basic", "service_model"
    )
    assert not OrchestraRiskSignalDetector._scope_value_present("", "anything", "region")
    assert OrchestraRiskSignalDetector._scope_value_present(
        "REGION_ALPHA", "REGION_ALPHA", "jurisdiction"
    )


def test_detector_does_not_treat_normal_scope_filtering_as_contradiction(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    planned = baseline("M4D-045")
    assert OrchestraRiskSignalDetector._has_contradiction(planned) is False
    assert OrchestraRiskSignalDetector._has_explicit_support(planned) is True
    assert OrchestraRiskSignalDetector._critical_claim_exists(planned) is False
    assert OrchestraRiskSignalDetector._has_table_ref(planned) is False
    assert OrchestraRiskSignalDetector._low_margin(planned) is True
    assert (
        runtime.detector._select_profile(Decision.ANSWER, (RiskSignal("SCOPE_SENSITIVE"),))[0].value
        == "FULL_ORCHESTRA"
    )
