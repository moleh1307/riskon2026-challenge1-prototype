"""M4D deterministic output and policy-order tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from m4d_helpers import pipeline, request, semantic_run


@pytest.mark.parametrize("case_id", ["M4D-041", "M4D-042", "M4D-043", "M4D-044", "M4D-045"])
def test_same_input_produces_same_semantic_orchestra_run(tmp_path: Path, case_id: str) -> None:
    req = request(case_id, trace_id=f"deterministic-{case_id}")
    first = pipeline(tmp_path / "first").run_orchestrated(req)
    second = pipeline(tmp_path / "second").run_orchestrated(req)
    assert semantic_run(first) == semantic_run(second)


def test_deterministic_task_ids_are_derived_from_plan_and_role(tmp_path: Path) -> None:
    run = pipeline(tmp_path).run_orchestrated(request("M4D-045"))
    assert [task.task_id for task in run.agent_tasks] == [
        f"task:{task.plan_id}:{task.agent_role.lower()}" for task in run.agent_tasks
    ]
    assert len({task.task_id for task in run.agent_tasks}) == len(run.agent_tasks)


def test_counterfactual_variant_ids_are_runtime_generated_not_case_ids(tmp_path: Path) -> None:
    run = pipeline(tmp_path).run_orchestrated(request("M4D-045"))
    assert [item.variant_id for item in run.counterfactual_results] == [
        "cf-001",
        "cf-002",
        "cf-003",
    ]
    assert all("M4D-045" not in item.variant_id for item in run.counterfactual_results)
