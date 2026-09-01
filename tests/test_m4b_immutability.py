"""M4B immutability and deterministic replay tests."""

from pathlib import Path

import pytest
from m4b_helpers import run_case
from pydantic import ValidationError

from riskon.evaluation import M4BScenarioResult
from riskon.orchestra.models import AgentTask


def _semantic(run):
    return {
        "roles": run.investigation_plan.required_agent_roles,
        "tasks": [item.model_dump(mode="json") for item in run.agent_tasks],
        "findings": [item.model_dump(mode="json") for item in run.findings],
        "claims": [item.model_dump(mode="json") for item in run.candidate_claims],
        "objections": [item.model_dump(mode="json") for item in run.material_objections],
        "decision": run.final_verified_run.result.decision.value,
        "evidence": run.final_verified_run.verification.evidence_refs,
        "route": run.case_capsule.model_dump(mode="json") if run.case_capsule else None,
    }


def test_repeated_case_execution_is_semantically_identical(tmp_path: Path) -> None:
    first = run_case(tmp_path / "first", "M4-037")[-1]
    second = run_case(tmp_path / "second", "M4-037")[-1]
    assert _semantic(first) == _semantic(second)


def test_baseline_fixture_is_unchanged_after_answer_and_abstain(tmp_path: Path) -> None:
    config, _pipeline, _case, planned, answer = run_case(tmp_path / "answer", "M4-030")
    before = planned.model_dump(mode="json")
    assert planned.model_dump(mode="json") == before
    _config, _pipeline, _case, abstain_planned, abstain = run_case(tmp_path / "abstain", "M4-037")
    assert abstain_planned.model_dump(mode="json") == abstain.baseline_run.model_dump(mode="json")
    assert config.orchestra.generated_root != _config.orchestra.generated_root
    assert answer.baseline_run.model_dump(mode="json") == before


def test_frozen_task_rejects_field_assignment() -> None:
    task = AgentTask(
        task_id="task:plan:evidence_scout",
        plan_id="plan",
        agent_id="agent",
        agent_role="EVIDENCE_SCOUT",
        execution_wave="DISCOVERY",
        objective="objective",
    )
    with pytest.raises(ValidationError):
        task.agent_role = "SKEPTIC"


def test_scenario_result_does_not_accept_raw_query_field() -> None:
    with pytest.raises(ValidationError):
        M4BScenarioResult(
            id="M4-030",
            matched=True,
            failures=[],
            expected_profile="DUAL_CHECK",
            actual_profile="DUAL_CHECK",
            expected_agent_roles=[],
            actual_agent_roles=[],
            expected_task_count=0,
            actual_task_count=0,
            expected_decision="ANSWER",
            actual_decision="ANSWER",
            expected_claim_ids=[],
            actual_claim_ids=[],
            required_finding_count=0,
            matched_required_finding_count=0,
            required_finding_recall=1.0,
            required_material_objection_count=0,
            matched_required_material_objection_count=0,
            required_material_objection_recall=1.0,
            required_evidence_refs=[],
            actual_evidence_refs=[],
            forbidden_evidence_count=0,
            open_material_objection_count=0,
            diagnostic_codes=[],
            expected_route=None,
            actual_route=None,
            case_capsule_id=None,
            worker_execution_count=0,
            baseline_unchanged=True,
            baseline_mutation_count=0,
            agent_to_agent_citation_count=0,
            recursive_delegation_count=0,
            network_violation_count=0,
            result={},
            query="raw query",
        )
