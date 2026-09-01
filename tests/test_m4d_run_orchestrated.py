"""Public M4D runtime flow and profile-path tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from m4d_helpers import pipeline, request

from riskon.models import Decision


@pytest.mark.parametrize(
    ("case_id", "profile", "decision", "roles"),
    [
        ("M4D-041", "FAST_PATH", Decision.ANSWER, []),
        ("M4D-042", "SHORT_CIRCUIT_CLARIFY", Decision.CLARIFY, []),
        ("M4D-043", "HUMAN_FIRST", Decision.ABSTAIN, []),
        ("M4D-044", "DUAL_CHECK", Decision.ANSWER, ["EVIDENCE_SCOUT", "SKEPTIC"]),
        (
            "M4D-045",
            "FULL_ORCHESTRA",
            Decision.ANSWER,
            ["EVIDENCE_SCOUT", "SCOPE_SENTINEL", "COUNTERFACTUAL_SENTINEL"],
        ),
    ],
)
def test_run_orchestrated_matches_the_five_profile_paths(
    tmp_path: Path,
    case_id: str,
    profile: str,
    decision: Decision,
    roles: list[str],
) -> None:
    run = pipeline(tmp_path).run_orchestrated(request(case_id))
    assert run.activation_profile.value == profile
    assert run.final_verified_run.result.decision is decision
    assert run.investigation_plan.required_agent_roles == roles
    assert [task.agent_role for task in run.agent_tasks] == roles
    assert run.runtime_diagnostics is not None
    assert run.runtime_diagnostics.run_planned_call_count == 1
    assert run.risk_assessment is not None
    assert run.risk_assessment.selected_activation_profile.value == profile


def test_fast_path_preserves_answer_and_uses_no_workers(tmp_path: Path) -> None:
    run = pipeline(tmp_path).run_orchestrated(request("M4D-041"))
    assert run.final_verified_run.model_dump(mode="json") == (
        run.baseline_run.verified_run.model_dump(mode="json")
    )
    assert run.orchestra_metrics.model_dump(mode="json") == {
        "active_agent_count": 0,
        "task_count": 0,
        "finding_count": 0,
        "candidate_claim_count": 0,
        "material_objection_count": 0,
        "counterfactual_count": 0,
        "worker_execution_count": 0,
    }
    assert run.routed_run is None
    assert run.case_capsule is None


def test_clarify_path_preserves_exact_question_and_short_circuits(tmp_path: Path) -> None:
    run = pipeline(tmp_path).run_orchestrated(request("M4D-042"))
    result = run.final_verified_run.result
    assert result.decision is Decision.CLARIFY
    assert result.clarifying_question == (
        "Do you mean Advisory Review Code or Account Routing Console?"
    )
    assert run.agent_tasks == []
    assert run.orchestra_metrics.worker_execution_count == 0
    assert run.routed_run is None


def test_human_first_path_routes_without_workers(tmp_path: Path) -> None:
    run = pipeline(tmp_path).run_orchestrated(request("M4D-043"))
    assert run.final_verified_run.result.decision is Decision.ABSTAIN
    assert run.routed_run is not None
    assert run.routed_run.expert_route is not None
    assert run.routed_run.expert_route.support_function == "BUSINESS_FRONT_SUPPORT"
    assert run.case_capsule is not None
    assert run.case_capsule.baseline_decision is Decision.ABSTAIN
    assert run.case_capsule.evidence_refs
    assert run.orchestra_metrics.task_count == 0


def test_dual_check_fanout_fanin_produces_both_atlas_claims(tmp_path: Path) -> None:
    run = pipeline(tmp_path).run_orchestrated(request("M4D-044"))
    result = run.final_verified_run.result
    assert result.decision is Decision.ANSWER
    assert result.route is None
    assert {claim.claim_id for claim in run.candidate_claims} >= {
        "atlas_do_not_proceed",
        "atlas_client_acceptance_no_override",
    }
    assert run.material_objections == []
    assert run.orchestra_metrics.task_count == 2
    assert run.orchestra_metrics.worker_execution_count == 2


def test_full_orchestra_runs_local_counterfactuals_without_route(tmp_path: Path) -> None:
    run = pipeline(tmp_path).run_orchestrated(request("M4D-045"))
    assert run.final_verified_run.result.decision is Decision.ANSWER
    assert run.final_verified_run.result.route is None
    assert run.orchestra_metrics.counterfactual_count == 3
    assert run.orchestra_metrics.worker_execution_count == 3
    assert [item.actual_decision for item in run.counterfactual_results] == [
        Decision.ABSTAIN,
        Decision.ABSTAIN,
        Decision.CLARIFY,
    ]
    assert all("route" not in item.model_dump(mode="json") for item in run.counterfactual_results)
