"""Counterfactual fan-out/fan-in and transition-adjudication tests."""

import asyncio

import pytest
from m4c_helpers import M4C_ROOT, case, planned

from riskon.evaluation import M4CEvaluator
from riskon.models import ReasonCode
from riskon.orchestra.counterfactual_adjudication import (
    CounterfactualAdjudicator,
    scope_mismatch_reason,
)
from riskon.orchestra.counterfactual_models import CounterfactualExecutionRequest
from riskon.orchestra.counterfactual_planner import CounterfactualPlanner
from riskon.orchestra.counterfactual_policy import CounterfactualExecutionPolicy
from riskon.orchestra.counterfactual_runner import FrozenCounterfactualRunner


def _planner() -> CounterfactualPlanner:
    return CounterfactualPlanner(
        CounterfactualExecutionPolicy.from_files(
            M4C_ROOT / "counterfactual_execution_policy.json",
            M4C_ROOT / "context_value_registry.json",
        )
    )


def _plan(case_id: str):
    baseline = planned(case_id).planned_verified_run
    planner = _planner()
    return baseline, planner.plan(
        baseline,
        planner.context_for(baseline),
        requested_variants=M4CEvaluator._requested_variants(case(case_id)),
    )


def _runner() -> FrozenCounterfactualRunner:
    return FrozenCounterfactualRunner(
        M4C_ROOT / "counterfactual_fixture_catalog.json",
        M4C_ROOT / "counterfactual_runs",
    )


def test_adjudicator_marks_safe_transitions_without_objections() -> None:
    baseline, plan = _plan("M4-035")
    fixture_runner = _runner()
    executed = [
        (
            variant,
            fixture_runner.run(
                CounterfactualExecutionRequest(
                    baseline_plan_id=plan.baseline_plan_id,
                    original_query=baseline.query_plan.original_query,
                    structured_context={
                        "region": "REGION_BETA",
                        "service_model": "SERVICE_BASIC",
                    },
                    variant=variant,
                )
            ),
        )
        for variant in plan.variants
    ]
    adjudication = CounterfactualAdjudicator().adjudicate(
        plan,
        list(reversed(executed)),
        runner_backend=fixture_runner.backend,
    )
    assert [item.variant_id for item in adjudication.results] == [
        "M4-035-CF-01",
        "M4-035-CF-02",
        "M4-035-CF-03",
    ]
    assert adjudication.summary.passed_count == 3
    assert adjudication.summary.failed_count == 0
    assert adjudication.objections == ()


def test_adjudicator_opens_material_objection_for_scope_leak() -> None:
    baseline, plan = _plan("M4-036")
    fixture_runner = _runner()
    variant = plan.variants[0]
    executed = [
        (
            variant,
            fixture_runner.run(
                CounterfactualExecutionRequest(
                    baseline_plan_id=plan.baseline_plan_id,
                    original_query=baseline.query_plan.original_query,
                    structured_context={
                        "region": "REGION_BETA",
                        "service_model": "SERVICE_BASIC",
                    },
                    variant=variant,
                )
            ),
        )
    ]
    adjudication = CounterfactualAdjudicator().adjudicate(
        plan, executed, runner_backend=fixture_runner.backend, agent_id="test-agent"
    )
    assert adjudication.summary.scope_leak_count == 1
    assert adjudication.results[0].passed is False
    assert adjudication.objections[0].agent_id == "test-agent"
    assert adjudication.objections[0].reason_code == "COUNTERFACTUAL_SCOPE_LEAK"
    assert scope_mismatch_reason() == [ReasonCode.SCOPE_MISMATCH]


class AsyncBarrierRunner:
    """Async wrapper that proves all bounded variants enter the fan-out."""

    backend = "ASYNC_FIXTURE_TEST"

    def __init__(self, fixture_runner: FrozenCounterfactualRunner) -> None:
        self.fixture_runner = fixture_runner
        self.started: list[str] = []
        self.all_started = asyncio.Event()

    async def run(self, request, *, counterfactual_depth: int = 1):
        assert counterfactual_depth == 1
        self.started.append(request.variant.variant_id)
        if len(self.started) == 3:
            self.all_started.set()
        await self.all_started.wait()
        return self.fixture_runner.run(request, counterfactual_depth=counterfactual_depth)


def test_adjudicator_fans_out_concurrently_and_fans_in_sorted_results() -> None:
    baseline, plan = _plan("M4-035")
    runner = AsyncBarrierRunner(_runner())
    result = asyncio.run(
        CounterfactualAdjudicator().execute(
            baseline,
            plan.model_copy(update={"variants": list(reversed(plan.variants))}),
            {"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
            runner,
        )
    )
    assert set(runner.started) == {item.variant_id for item in plan.variants}
    assert [item.variant_id for item in result.results] == sorted(runner.started)
    assert result.summary.passed_count == 3


def test_adjudicator_rejects_counterfactual_query_mutation() -> None:
    baseline, plan = _plan("M4-035")

    class ChangedQueryRunner:
        backend = "CHANGED_QUERY_TEST"

        def run(self, _request, *, counterfactual_depth: int = 1):
            del counterfactual_depth
            return baseline.model_copy(
                update={
                    "query_plan": baseline.query_plan.model_copy(
                        update={"original_query": "changed"}
                    )
                },
                deep=True,
            )

    with pytest.raises(ExceptionGroup) as exc_info:
        asyncio.run(
            CounterfactualAdjudicator().execute(
                baseline,
                plan.model_copy(update={"variants": [plan.variants[0]]}),
                {"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
                ChangedQueryRunner(),
            )
        )
    assert "immutable" in repr(exc_info.value)
