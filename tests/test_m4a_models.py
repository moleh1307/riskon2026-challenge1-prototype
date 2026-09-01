"""Contract tests for the M4A orchestration models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from riskon.models import (
    Decision,
    DetectedContext,
    PlannedVerifiedRun,
    RouteMode,
    VerificationStatus,
)
from riskon.orchestra.models import (
    ActivationProfile,
    CaseCapsule,
    InvestigationPlan,
    OrchestraContext,
    OrchestraMetrics,
    OrchestraRun,
    RiskSignal,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"


def planned_fixture(case_id: str) -> PlannedVerifiedRun:
    """Load one frozen M4 planned run."""

    raw = json.loads((M4_ROOT / "upstream_runs" / f"{case_id}.planned.json").read_text())
    return PlannedVerifiedRun.model_validate(raw["planned_verified_run"])


def test_activation_profile_and_context_are_closed_and_serializable() -> None:
    context = OrchestraContext(
        risk_signals=(RiskSignal("APPROVAL_REQUIRED"),),
        routing_context=None,
        routing_profile="default",
    )
    assert list(ActivationProfile) == [
        ActivationProfile.FAST_PATH,
        ActivationProfile.SHORT_CIRCUIT_CLARIFY,
        ActivationProfile.HUMAN_FIRST,
        ActivationProfile.DUAL_CHECK,
        ActivationProfile.FULL_ORCHESTRA,
    ]
    assert context.model_dump(mode="json") == {
        "risk_signals": ["APPROVAL_REQUIRED"],
        "routing_context": None,
        "routing_profile": "default",
    }

    with pytest.raises(ValidationError):
        OrchestraContext(
            risk_signals=("NOT_A_FROZEN_SIGNAL",),
            routing_context=None,
            routing_profile="default",
        )
    with pytest.raises(ValidationError):
        OrchestraContext(
            risk_signals=(),
            routing_context=None,
            routing_profile="",
        )
    with pytest.raises(ValidationError):
        OrchestraContext(
            risk_signals=(),
            routing_context=None,
            routing_profile="default",
            unexpected="rejected",
        )


def test_empty_worker_contracts_have_deterministic_json() -> None:
    plan = InvestigationPlan(
        activation_profile=ActivationProfile.FAST_PATH,
        required_agent_roles=[],
        task_ids=[],
        worker_execution_required=False,
    )
    metrics = OrchestraMetrics(
        active_agent_count=0,
        task_count=0,
        finding_count=0,
        candidate_claim_count=0,
        material_objection_count=0,
        counterfactual_count=0,
        worker_execution_count=0,
    )
    assert plan.model_dump(mode="json") == {
        "activation_profile": "FAST_PATH",
        "required_agent_roles": [],
        "task_ids": [],
        "worker_execution_required": False,
    }
    assert metrics.model_dump(mode="json") == {
        "active_agent_count": 0,
        "task_count": 0,
        "finding_count": 0,
        "candidate_claim_count": 0,
        "material_objection_count": 0,
        "counterfactual_count": 0,
        "worker_execution_count": 0,
    }
    with pytest.raises(ValidationError):
        OrchestraMetrics(
            active_agent_count=-1,
            task_count=0,
            finding_count=0,
            candidate_claim_count=0,
            material_objection_count=0,
            counterfactual_count=0,
            worker_execution_count=0,
        )


def test_case_capsule_and_orchestra_run_reject_extra_or_nonlocal_data() -> None:
    planned = planned_fixture("M4-034")
    result = planned.verified_run.result
    capsule = CaseCapsule(
        capsule_id="m4a-capsule-test",
        baseline_trace_id=result.trace_id,
        baseline_decision=Decision.ABSTAIN,
        reason_codes=list(result.reason_codes),
        detected_context=DetectedContext.model_validate(result.detected_context.model_dump()),
        missing_context=[],
        evidence_refs=["local://synthetic-m4/procedure_missing_form.html#section-required-form"],
        verification_status=VerificationStatus.INSUFFICIENT,
        support_function="BUSINESS_FRONT_SUPPORT",
        route_mode=RouteMode.FUNCTIONAL_QUEUE,
        selected_expert_id=None,
        queue_id="QUEUE-BFS-GLOBAL",
        routing_reason="structured test route",
        routing_confidence=0.5,
        confidence_kind="DETERMINISTIC_ROUTING_HEURISTIC_V1",
    )
    assert capsule.model_dump(mode="json")["evidence_refs"]
    with pytest.raises(ValidationError):
        CaseCapsule.model_validate(
            {**capsule.model_dump(mode="json"), "evidence_refs": ["https://example.invalid/raw"]}
        )

    run = OrchestraRun(
        baseline_run=planned,
        activation_profile=ActivationProfile.HUMAN_FIRST,
        risk_signals=(RiskSignal("UNRESOLVED_REQUIRED_REFERENCE"),),
        investigation_plan=InvestigationPlan(
            activation_profile=ActivationProfile.HUMAN_FIRST,
            worker_execution_required=False,
        ),
        final_verified_run=planned.verified_run,
        case_capsule=capsule,
        orchestra_metrics=OrchestraMetrics(
            active_agent_count=0,
            task_count=0,
            finding_count=0,
            candidate_claim_count=0,
            material_objection_count=0,
            counterfactual_count=0,
            worker_execution_count=0,
        ),
    )
    payload = run.model_dump(mode="json")
    assert payload["agent_tasks"] == []
    assert payload["candidate_claims"] == []
    assert payload["case_capsule"]["baseline_trace_id"] == result.trace_id
    with pytest.raises(ValidationError):
        OrchestraRun.model_validate({**payload, "not_allowed": True})
