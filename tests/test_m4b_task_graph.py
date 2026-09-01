"""M4B deterministic task graph tests."""

from m4b_helpers import M4_ROOT

from riskon.orchestra.models import ExecutionWave
from riskon.orchestra.policy import WorkerSelectionPolicy
from riskon.orchestra.tasks import AgentCatalog, build_agent_tasks
from riskon.orchestra.worker_selection import WorkerSelector


def _selector() -> WorkerSelector:
    policy = WorkerSelectionPolicy.from_file(
        M4_ROOT.parent / "m4b" / "worker_selection_policy.json"
    )
    catalog = AgentCatalog.from_file(M4_ROOT / "agent_catalog.json")
    return WorkerSelector(policy, catalog)


def test_full_orchestra_graph_has_discovery_then_one_challenge() -> None:
    tasks = _selector().build_tasks(
        "plan-alpha",
        ["SCOPE_SENSITIVE", "JURISDICTION_SENSITIVE"],
    )
    assert [task.agent_role for task in tasks] == [
        "EVIDENCE_SCOUT",
        "SCOPE_SENTINEL",
        "SKEPTIC",
    ]
    assert [task.execution_wave for task in tasks] == [
        ExecutionWave.DISCOVERY,
        ExecutionWave.DISCOVERY,
        ExecutionWave.CHALLENGE,
    ]
    assert [task.task_id for task in tasks] == [
        "task:plan-alpha:evidence_scout",
        "task:plan-alpha:scope_sentinel",
        "task:plan-alpha:skeptic",
    ]


def test_task_graph_is_independent_of_signal_input_order() -> None:
    first = _selector().build_tasks("plan-stable", ["TABLE_DEPENDENT", "CRITICAL_CONTROL_RISK"])
    second = _selector().build_tasks("plan-stable", ["CRITICAL_CONTROL_RISK", "TABLE_DEPENDENT"])
    assert [task.model_dump(mode="json") for task in first] == [
        task.model_dump(mode="json") for task in second
    ]


def test_task_builder_rejects_unregistered_role() -> None:
    catalog = AgentCatalog.from_file(M4_ROOT / "agent_catalog.json")
    try:
        build_agent_tasks("plan-invalid", ["COUNTERFACTUAL_SENTINEL"], catalog)
    except ValueError as exc:
        assert "objective" in str(exc)
    else:
        raise AssertionError("unregistered M4B worker role was accepted")
