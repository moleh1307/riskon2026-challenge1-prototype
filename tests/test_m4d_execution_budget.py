"""M4D defensive profile, budget, and internal-boundary tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from m4d_helpers import baseline, pipeline, request

from riskon.models import (
    Decision,
    NeedType,
    RoutedRun,
    RoutingContext,
    RoutingDiagnostics,
    RoutingStatus,
    VerificationStatus,
)
from riskon.orchestra.counterfactual_models import CounterfactualSummary
from riskon.orchestra.errors import (
    OrchestraConfigurationError,
    OrchestraFailClosedError,
)
from riskon.orchestra.models import (
    ActivationProfile,
    MaterialObjection,
    OrchestraContext,
    RiskAssessment,
    RiskSignal,
)


def _assessment(profile: ActivationProfile, signals: tuple[str, ...] = ()) -> RiskAssessment:
    return RiskAssessment(
        risk_signals=tuple(RiskSignal(signal) for signal in signals),
        signal_sources={signal: ("test",) for signal in signals},
        selected_activation_profile=profile,
        profile_reason="defensive test",
    )


@pytest.mark.parametrize(
    "attribute",
    [
        "network_enabled",
        "external_api_enabled",
        "recursive_orchestration_enabled",
        "counterfactual_routing_enabled",
        "agent_to_agent_citation_enabled",
    ],
)
def test_security_switches_fail_closed(tmp_path: Path, attribute: str) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    setattr(runtime, attribute, True)
    with pytest.raises(OrchestraConfigurationError, match="M4D requires"):
        runtime_pipeline.run_orchestrated(request("M4D-041"))


def test_disabled_automatic_activation_is_configuration_error(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    runtime.runtime_policy.auto_activation_enabled = False
    with pytest.raises(OrchestraConfigurationError, match="automatic activation"):
        runtime_pipeline.run_orchestrated(request("M4D-041"))


@pytest.mark.parametrize(
    ("case_id", "profile", "signals", "message"),
    [
        ("M4D-041", "NOT_A_PROFILE", (), "Unknown M4D activation profile"),
        ("M4D-041", "SHORT_CIRCUIT_CLARIFY", (), "requires a baseline CLARIFY"),
        ("M4D-044", "FAST_PATH", ("CRITICAL_CONTROL_RISK",), "FAST_PATH requires"),
        ("M4D-041", "HUMAN_FIRST", (), "requires a baseline ABSTAIN"),
        (
            "M4D-042",
            "DUAL_CHECK",
            ("BASELINE_CLARIFY", "AMBIGUOUS_ACRONYM"),
            "must not execute workers",
        ),
    ],
)
def test_direct_profile_contracts_reject_invalid_combinations(
    tmp_path: Path,
    case_id: str,
    profile: str,
    signals: tuple[str, ...],
    message: str,
) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    with pytest.raises(OrchestraConfigurationError, match=message):
        runtime.orchestrate_planned(
            runtime_pipeline.run_planned(request(case_id)),
            OrchestraContext(
                risk_signals=tuple(RiskSignal(signal) for signal in signals),
                routing_profile="default",
            ),
            profile,
            risk_assessment=_assessment(
                ActivationProfile(profile)
                if profile != "NOT_A_PROFILE"
                else ActivationProfile.FAST_PATH,
                signals,
            ),
            run_planned_call_count=1,
        )


def test_assessment_and_context_mismatch_is_configuration_error(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    planned = runtime_pipeline.run_planned(request("M4D-041"))
    with pytest.raises(OrchestraConfigurationError, match="assessment/profile mismatch"):
        runtime.orchestrate_planned(
            planned,
            OrchestraContext(risk_signals=(), routing_profile="default"),
            "FAST_PATH",
            risk_assessment=_assessment(ActivationProfile.DUAL_CHECK),
        )
    with pytest.raises(OrchestraConfigurationError, match="assessment/signal mismatch"):
        runtime.orchestrate_planned(
            planned,
            OrchestraContext(
                risk_signals=(RiskSignal("CRITICAL_CONTROL_RISK"),),
                routing_profile="default",
            ),
            "DUAL_CHECK",
            risk_assessment=_assessment(ActivationProfile.DUAL_CHECK),
        )


def test_counterfactual_plan_lineage_and_variant_budget_fail_closed(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    req = request("M4D-045")
    planned = runtime_pipeline.run_planned(req)
    context = OrchestraContext(
        risk_signals=tuple(
            RiskSignal(signal)
            for signal in ("SCOPE_SENSITIVE", "SERVICE_MODEL_SENSITIVE", "COUNTERFACTUAL_REQUIRED")
        ),
        structured_context=req.context,
        routing_profile="default",
    )
    actual_plan = runtime.counterfactual_planner.plan(planned, req.context)
    over_budget = actual_plan.model_copy(
        update={
            "variants": [
                *actual_plan.variants,
                actual_plan.variants[0].model_copy(update={"variant_id": "cf-extra"}),
            ]
        }
    )
    with pytest.raises(OrchestraFailClosedError) as captured:
        runtime.orchestrate_planned(
            planned,
            context,
            "FULL_ORCHESTRA",
            counterfactual_plan=over_budget,
        )
    assert captured.value.stage == "EXECUTION_BUDGET"
    lineage = actual_plan.model_copy(update={"baseline_plan_id": "wrong-plan"})
    with pytest.raises(OrchestraConfigurationError, match="lineage"):
        runtime.orchestrate_planned(planned, context, "FULL_ORCHESTRA", counterfactual_plan=lineage)


def test_scope_objection_blocks_unsafe_final_answer(tmp_path: Path) -> None:
    runtime = pipeline(tmp_path)._m4d_runtime
    assert runtime is not None
    planned = baseline("M4D-045")
    objection = MaterialObjection(
        objection_id="objection:test:scope",
        agent_id="COUNTERFACTUAL_SENTINEL",
        target_claim_id="meridian_applies_beta_basic",
        reason_code="COUNTERFACTUAL_SCOPE_LEAK",
        materiality="MATERIAL",
        evidence_refs=["local://synthetic-m4d/meridian_region_alpha.html"],
        status="OPEN",
        resolvable_by="HUMAN_REVIEW",
    )
    final = runtime._final_verified_run(
        planned,
        planned.verified_run,
        [objection],
        CounterfactualSummary(
            variant_count=1,
            passed_count=0,
            failed_count=1,
            scope_leak_count=1,
            routing_execution_count=0,
        ),
    )
    assert final.result.decision is Decision.ABSTAIN
    assert final.result.answer is None
    assert final.result.route is not None
    assert final.verification.status is VerificationStatus.INSUFFICIENT
    assert final.verification.reason_codes == ["SCOPE_MISMATCH"]


def test_internal_role_selection_covers_table_scope_skeptic_and_requested_roles(
    tmp_path: Path,
) -> None:
    runtime = pipeline(tmp_path)._m4d_runtime
    assert runtime is not None
    empty_context = OrchestraContext(risk_signals=(), routing_profile="default")
    assert runtime._roles(
        ActivationProfile.DUAL_CHECK,
        (RiskSignal("TABLE_DEPENDENT"),),
        empty_context,
    ) == ["PROCESS_TABLE_SCOUT", "SKEPTIC"]
    assert runtime._roles(
        ActivationProfile.FULL_ORCHESTRA,
        (RiskSignal("TABLE_DEPENDENT"),),
        empty_context,
    ) == ["PROCESS_TABLE_SCOUT"]
    assert runtime._roles(
        ActivationProfile.FULL_ORCHESTRA,
        (RiskSignal("LOW_RETRIEVAL_MARGIN"),),
        empty_context,
    ) == ["EVIDENCE_SCOUT", "SKEPTIC"]
    requested = OrchestraContext(
        risk_signals=(),
        routing_profile="default",
        requested_agent_roles=("EVIDENCE_SCOUT", "SKEPTIC"),
    )
    assert runtime._roles(ActivationProfile.FULL_ORCHESTRA, (), requested) == [
        "EVIDENCE_SCOUT",
        "SKEPTIC",
    ]
    duplicate = requested.model_copy(update={"requested_agent_roles": ("SKEPTIC", "SKEPTIC")})
    with pytest.raises(OrchestraConfigurationError, match="roles must be unique"):
        runtime._roles(ActivationProfile.FULL_ORCHESTRA, (), duplicate)


def test_route_helper_reconciles_reasons_and_rejects_route_without_expert(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    planned = runtime_pipeline.run_planned(request("M4D-043"))
    context = OrchestraContext(
        risk_signals=(RiskSignal("UNRESOLVED_REQUIRED_REFERENCE"),),
        routing_profile="default",
        routing_context=RoutingContext(
            need_type=NeedType.POLICY_INTERPRETATION,
            reason_codes=[],
        ),
    )
    routed, capsule = runtime._route_if_needed(planned, context, namespace="test")
    assert routed is not None and capsule is not None

    def no_expert(value: object, _context: RoutingContext, _profile: str) -> RoutedRun:
        assert value is planned
        return RoutedRun(
            planned_verified_run=planned,
            expert_route=None,
            routing_diagnostics=RoutingDiagnostics(status=RoutingStatus.BLOCKED),
        )

    runtime.route_planned = no_expert  # type: ignore[assignment]
    with pytest.raises(OrchestraConfigurationError, match="no expert route"):
        runtime._route_if_needed(planned, context, namespace="test")


def test_empty_wave_and_no_audit_sink_are_safe(tmp_path: Path) -> None:
    runtime = pipeline(tmp_path)._m4d_runtime
    assert runtime is not None
    safety = runtime._source_safety()
    assert (
        runtime._execute_wave(
            [],
            baseline("M4D-041"),
            OrchestraContext(risk_signals=(), routing_profile="default"),
            safety,
            stage="DISCOVERY",
        )
        == []
    )
    runtime.audit_sink = None
    runtime._append_success(
        pipeline(tmp_path / "second").run_orchestrated(request("M4D-041")),
        None,
        _assessment(ActivationProfile.FAST_PATH),
    )
    runtime._append_failure(
        baseline("M4D-041"),
        ActivationProfile.DUAL_CHECK,
        "WORKER_EXECUTION",
        [],
        [],
        fallback_action="FAIL_CLOSED",
    )
