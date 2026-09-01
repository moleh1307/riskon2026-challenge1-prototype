"""Tests for the normal local planned-pipeline counterfactual adapter."""

import asyncio
from typing import Any

import pytest
from m4c_helpers import case, planned

from riskon.evaluation import M4CEvaluator
from riskon.models import PlannedVerifiedRun, QueryInput
from riskon.orchestra.counterfactual_models import CounterfactualExecutionRequest
from riskon.orchestra.counterfactual_runner import (
    LocalPlannedPipelineCounterfactualRunner,
    run_maybe_async,
)
from riskon.orchestra.errors import RecursiveCounterfactualExecutionError


def request_for(case_id: str, index: int) -> CounterfactualExecutionRequest:
    baseline = planned(case_id).planned_verified_run
    variant = M4CEvaluator._requested_variants(case(case_id))[index]
    return CounterfactualExecutionRequest(
        baseline_plan_id=baseline.query_plan.plan_id,
        original_query=baseline.query_plan.original_query,
        structured_context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
        variant=variant,
    )


def test_local_runner_mutates_only_context_and_preserves_query() -> None:
    baseline = planned("M4-035").planned_verified_run
    calls: list[QueryInput] = []

    def run(query: QueryInput) -> PlannedVerifiedRun:
        calls.append(query)
        return baseline

    result = LocalPlannedPipelineCounterfactualRunner(run).run(request_for("M4-035", 0))
    assert result is baseline
    assert len(calls) == 1
    assert calls[0].query == baseline.query_plan.original_query
    assert calls[0].context == {"region": "REGION_ALPHA", "service_model": "SERVICE_BASIC"}
    assert calls[0].trace_id == "cf:m4-fixture-M4-035:M4-035-CF-01"


def test_local_runner_removes_a_context_dimension_and_validates_depth() -> None:
    baseline = planned("M4-035").planned_verified_run

    def run(_query: QueryInput) -> PlannedVerifiedRun:
        return baseline

    request = request_for("M4-035", 2)
    LocalPlannedPipelineCounterfactualRunner(run).run(request)
    with pytest.raises(RecursiveCounterfactualExecutionError, match="maximum depth"):
        LocalPlannedPipelineCounterfactualRunner(run).run(request, counterfactual_depth=2)


def test_local_runner_rejects_bad_replacement_and_changed_query() -> None:
    baseline = planned("M4-035").planned_verified_run
    request = request_for("M4-035", 0)
    invalid_variant = request.variant.model_copy(update={"to_value": None})
    invalid_request = request.model_copy(update={"variant": invalid_variant})

    def return_baseline(_query: QueryInput) -> PlannedVerifiedRun:
        return baseline

    with pytest.raises(ValueError, match="requires a target"):
        LocalPlannedPipelineCounterfactualRunner(return_baseline).run(invalid_request)

    changed = baseline.model_copy(
        update={"query_plan": baseline.query_plan.model_copy(update={"original_query": "changed"})},
        deep=True,
    )

    def return_changed(_query: QueryInput) -> PlannedVerifiedRun:
        return changed

    with pytest.raises(ValueError, match="changed the original query"):
        LocalPlannedPipelineCounterfactualRunner(return_changed).run(request)


def test_local_runner_validates_mapping_results_and_run_maybe_async() -> None:
    baseline = planned("M4-035").planned_verified_run
    request = request_for("M4-035", 0)
    calls: list[QueryInput] = []

    def return_mapping(query: QueryInput) -> Any:
        calls.append(query)
        return baseline.model_dump(mode="json")

    runner = LocalPlannedPipelineCounterfactualRunner(return_mapping)
    result = runner.run(request)
    assert isinstance(result, PlannedVerifiedRun)

    class AsyncRunner:
        backend = "ASYNC_TEST"

        async def run(self, _request, *, counterfactual_depth: int = 1):
            assert counterfactual_depth == 1
            return baseline

    assert asyncio.run(run_maybe_async(AsyncRunner(), request)) is baseline
    assert calls
