"""M4D policy, budget, and typed-error contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from m4d_helpers import M4D_ROOT
from pydantic import ValidationError

from riskon.models import Decision
from riskon.orchestra.errors import (
    OrchestraConfigurationError,
    OrchestraExecutionBudgetExceededError,
    OrchestraFailClosedError,
)
from riskon.orchestra.failure_policy import FailurePolicy
from riskon.orchestra.models import RiskSignal
from riskon.orchestra.runtime_policy import RuntimePolicy


def _write_json(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _runtime_raw() -> dict[str, object]:
    return json.loads((M4D_ROOT / "runtime_policy.json").read_text(encoding="utf-8"))


def _failure_raw() -> dict[str, object]:
    return json.loads((M4D_ROOT / "failure_policy.json").read_text(encoding="utf-8"))


def test_runtime_policy_is_immutable_and_detached() -> None:
    policy = RuntimePolicy.from_file(M4D_ROOT / "runtime_policy.json")
    assert policy.auto_activation_enabled is True
    assert len(policy.risk_signal_rules) == 20
    assert policy.execution_budget.maximum_total_worker_tasks == 7
    assert policy.validate_signals([RiskSignal("PROMPT_INJECTION_SIGNAL")]) == (
        RiskSignal("PROMPT_INJECTION_SIGNAL"),
    )
    exported = policy.as_dict()
    exported["risk_signal_order"].clear()  # type: ignore[union-attr]
    assert len(policy.risk_signal_order) == 20
    first = policy.risk_signal_rules[0]
    with pytest.raises(ValidationError):
        first.source = "changed"  # type: ignore[misc]


def test_runtime_policy_returns_rules_in_canonical_order() -> None:
    policy = RuntimePolicy.from_file(M4D_ROOT / "runtime_policy.json")
    assert [str(rule.signal) for rule in policy.risk_signal_rules] == [
        str(signal) for signal in policy.risk_signal_order
    ]
    assert policy.rule("BASELINE_CLARIFY").source
    with pytest.raises(OrchestraConfigurationError, match="Unknown M4D risk signal"):
        policy.rule("NOT_DECLARED")
    with pytest.raises(OrchestraConfigurationError, match="Unknown M4D risk signal"):
        policy.validate_signals([RiskSignal("NOT_DECLARED")])


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda raw: raw.pop("execution_budget"), "fields do not match"),
        (lambda raw: raw.__setitem__("schema_version", "2.0"), "Unsupported"),
        (lambda raw: raw.__setitem__("auto_activation_enabled", False), "automatic activation"),
        (
            lambda raw: raw["risk_signal_order"].__setitem__(0, raw["risk_signal_order"][1]),
            "unique and aligned",
        ),
        (
            lambda raw: raw["risk_signal_rules"].pop(),
            "unique and aligned",
        ),
        (
            lambda raw: raw["execution_budget"].__setitem__("maximum_total_worker_tasks", 8),
            "budget does not match",
        ),
    ],
)
def test_runtime_policy_rejects_contract_drift(
    tmp_path: Path,
    mutation: object,
    message: str,
) -> None:
    raw = _runtime_raw()
    mutation(raw)  # type: ignore[operator]
    with pytest.raises(OrchestraConfigurationError, match=message):
        RuntimePolicy.from_file(_write_json(tmp_path / "runtime.json", raw))


@pytest.mark.parametrize(
    "value",
    [None, [], "not-an-object", {"unexpected": True}],
)
def test_runtime_policy_rejects_invalid_json_shapes(tmp_path: Path, value: object) -> None:
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(OrchestraConfigurationError):
        RuntimePolicy.from_file(path)


def test_runtime_policy_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OrchestraConfigurationError, match="not found"):
        RuntimePolicy.from_file(tmp_path / "missing.json")


def test_failure_policy_is_immutable_and_covers_all_baseline_decisions() -> None:
    policy = FailurePolicy.from_file(M4D_ROOT / "failure_policy.json")
    assert policy.retry_count == 0
    assert policy.partial_answer_enabled is False
    assert policy.rule_for(Decision.ANSWER).action == "FAIL_CLOSED"
    assert policy.rule_for(Decision.ABSTAIN).fallback_action == (
        "ROUTE_AND_OPEN_ORCHESTRATION_INCOMPLETE"
    )
    assert policy.rule_for(Decision.CLARIFY).action == "NO_WORKERS"
    assert policy.configuration_rule().action == "RAISE_CONFIGURATION_ERROR"
    rules = policy.rules
    assert len(rules) == 4
    with pytest.raises(ValidationError):
        rules[0].rule_id = "mutated"  # type: ignore[misc]
    assert policy.rules[0].rule_id == "ANSWER_WORKER_FAILURE"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda raw: raw.pop("rules"), "fields do not match"),
        (lambda raw: raw.__setitem__("schema_version", "2.0"), "Unsupported"),
        (lambda raw: raw.__setitem__("retry_count", 1), "retries and partial answers"),
        (
            lambda raw: raw.__setitem__("partial_answer_enabled", True),
            "retries and partial answers",
        ),
        (lambda raw: raw["rules"].reverse(), "rule order"),
        (lambda raw: raw["rules"][0].__setitem__("action", "RETURN_PARTIAL"), "does not match"),
    ],
)
def test_failure_policy_rejects_contract_drift(
    tmp_path: Path,
    mutation: object,
    message: str,
) -> None:
    raw = _failure_raw()
    mutation(raw)  # type: ignore[operator]
    with pytest.raises(OrchestraConfigurationError, match=message):
        FailurePolicy.from_file(_write_json(tmp_path / "failure.json", raw))


def test_failure_policy_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OrchestraConfigurationError, match="not found"):
        FailurePolicy.from_file(tmp_path / "missing.json")


def test_fail_closed_error_exposes_only_safe_structured_fields() -> None:
    error = OrchestraFailClosedError(
        stage="WORKER_EXECUTION",
        activation_profile="DUAL_CHECK",
        baseline_decision="ANSWER",
        failed_task_ids=["task:one"],
        cause_types=["SyntheticWorkerFailure"],
    )
    assert str(error) == OrchestraFailClosedError.safe_message
    assert error.safe_message == OrchestraFailClosedError.safe_message
    assert error.stage == "WORKER_EXECUTION"
    assert error.failed_task_ids == ["task:one"]
    assert error.cause_types == ["SyntheticWorkerFailure"]
    assert OrchestraExecutionBudgetExceededError.__name__
