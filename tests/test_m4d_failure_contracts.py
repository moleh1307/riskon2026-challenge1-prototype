"""M4D fail-closed and safe-fallback contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from m4d_helpers import pipeline, request

from riskon.models import Decision
from riskon.orchestra.counterfactual_models import CounterfactualExecutionRequest
from riskon.orchestra.errors import (
    OrchestraExecutionBudgetExceededError,
    OrchestraFailClosedError,
)
from riskon.orchestra.models import (
    ActivationProfile,
    OrchestraContext,
    RiskAssessment,
    RiskSignal,
    RuntimeDiagnostics,
)
from riskon.orchestra.runtime_audit import validate_m4d_audit_file
from riskon.orchestra.runtime_diagnostics import safe_failure_payload


class SyntheticWorkerFailure:
    """Worker double that fails without returning any findings."""

    async def run(self, _context: object) -> object:
        raise RuntimeError("synthetic worker failure")


class SyntheticCounterfactualFailure:
    """Local runner double that fails before returning a planned result."""

    def run(
        self,
        _request: CounterfactualExecutionRequest,
        *,
        counterfactual_depth: int = 1,
    ) -> object:
        del counterfactual_depth
        raise RuntimeError("synthetic counterfactual failure")


def _audit_rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_answer_worker_failure_is_fail_closed_and_audited(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    runtime.executor.workers["EVIDENCE_SCOUT"] = SyntheticWorkerFailure()  # type: ignore[assignment]
    req = request("M4D-044", trace_id="failure-answer")
    with pytest.raises(OrchestraFailClosedError) as captured:
        runtime_pipeline.run_orchestrated(req)
    error = captured.value
    assert str(error) == OrchestraFailClosedError.safe_message
    assert error.stage == "WORKER_EXECUTION"
    assert error.activation_profile == "DUAL_CHECK"
    assert error.baseline_decision == "ANSWER"
    assert any("evidence_scout" in task_id.lower() for task_id in error.failed_task_ids)
    assert "RuntimeError" in error.cause_types
    audit_logger = runtime_pipeline._m4d_audit_logger
    assert audit_logger is not None
    audit_path = audit_logger.path
    ok, message = validate_m4d_audit_file(audit_path)
    assert (ok, message) == (True, "M4D audit schema valid")
    row = _audit_rows(audit_path)[0]
    assert row["answer_returned"] is False
    assert row["route_returned"] is False
    assert row["baseline_decision"] == "ANSWER"
    assert "safe_message" not in row


def test_abstain_worker_failure_preserves_human_safe_fallback(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    runtime.executor.workers["EVIDENCE_SCOUT"] = SyntheticWorkerFailure()  # type: ignore[assignment]
    req = request("M4D-043", trace_id="failure-abstain")
    planned = runtime_pipeline.run_planned(req)
    assessment = RiskAssessment(
        risk_signals=(RiskSignal("CRITICAL_CONTROL_RISK"),),
        signal_sources={"CRITICAL_CONTROL_RISK": ("failure-test",)},
        selected_activation_profile=ActivationProfile.DUAL_CHECK,
        profile_reason="failure test",
    )
    run = runtime.orchestrate_planned(
        planned,
        OrchestraContext(
            risk_signals=assessment.risk_signals,
            routing_profile="default",
        ),
        ActivationProfile.DUAL_CHECK.value,
        risk_assessment=assessment,
        request=req,
        run_planned_call_count=1,
    )
    assert run.final_verified_run.result.decision is Decision.ABSTAIN
    assert run.final_verified_run.result.answer is None
    assert run.findings == []
    assert run.candidate_claims == []
    assert run.routed_run is not None
    assert run.routed_run.expert_route is not None
    assert run.case_capsule is not None
    objection = next(
        item for item in run.material_objections if item.reason_code == "ORCHESTRATION_INCOMPLETE"
    )
    assert objection.materiality == "MATERIAL"
    assert objection.status == "OPEN"
    assert objection.resolvable_by == "HUMAN_REVIEW"
    assert run.runtime_diagnostics is not None
    assert run.runtime_diagnostics.fallback_action == "PRESERVE_ABSTAIN_AND_ROUTE"
    audit_logger = runtime_pipeline._m4d_audit_logger
    assert audit_logger is not None
    audit_path = audit_logger.path
    row = _audit_rows(audit_path)[0]
    assert row["answer_returned"] is False
    assert row["route_returned"] is True


def test_counterfactual_failure_never_returns_baseline_answer(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    runtime.local_runner = SyntheticCounterfactualFailure()  # type: ignore[assignment]
    with pytest.raises(OrchestraFailClosedError) as captured:
        runtime_pipeline.run_orchestrated(request("M4D-045", trace_id="failure-cf"))
    error = captured.value
    assert error.stage == "COUNTERFACTUAL"
    assert error.baseline_decision == "ANSWER"
    assert any("counterfactual_sentinel" in task_id for task_id in error.failed_task_ids)
    assert error.cause_types
    audit_logger = runtime_pipeline._m4d_audit_logger
    assert audit_logger is not None
    audit_path = audit_logger.path
    rows = _audit_rows(audit_path)
    assert len(rows) == 1
    assert "final_decision" not in rows[0]
    assert rows[0]["answer_returned"] is False


def test_structural_worker_budget_fails_without_fallback(tmp_path: Path) -> None:
    runtime = pipeline(tmp_path)._m4d_runtime
    assert runtime is not None
    with pytest.raises(OrchestraExecutionBudgetExceededError, match="maximum worker tasks"):
        runtime._check_task_budget(8)


def test_failure_diagnostics_are_safe_and_source_free(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    runtime.executor.workers["EVIDENCE_SCOUT"] = SyntheticWorkerFailure()  # type: ignore[assignment]
    with pytest.raises(OrchestraFailClosedError):
        runtime_pipeline.run_orchestrated(request("M4D-044", trace_id="failure-safe"))
    audit_logger = runtime_pipeline._m4d_audit_logger
    assert audit_logger is not None
    audit_path = audit_logger.path
    row = _audit_rows(audit_path)[0]
    serialized = json.dumps(row)
    assert not any(token in serialized for token in ("http://", "https://", "/Users/", "@"))
    diagnostics = runtime.last_worker_diagnostics
    assert isinstance(diagnostics, list)
    safe = RuntimeDiagnostics(
        run_planned_call_count=1,
        failure_stage="WORKER_EXECUTION",
        failed_task_ids=("task:example",),
        cause_types=("RuntimeError",),
        fallback_action="FAIL_CLOSED",
    )
    assert safe_failure_payload(safe) == {
        "failed_stage": "WORKER_EXECUTION",
        "failed_task_ids": ["task:example"],
        "cause_types": ["RuntimeError"],
        "fallback_action": "FAIL_CLOSED",
    }
