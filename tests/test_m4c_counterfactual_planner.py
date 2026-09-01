"""Deterministic M4C planning tests."""

from pathlib import Path

import pytest
from m4c_helpers import case, planned

from riskon.evaluation import M4CEvaluator
from riskon.orchestra.counterfactual_models import CounterfactualOperation
from riskon.orchestra.counterfactual_planner import CounterfactualPlanner
from riskon.orchestra.counterfactual_policy import CounterfactualExecutionPolicy


def planner() -> CounterfactualPlanner:
    return CounterfactualPlanner(
        CounterfactualExecutionPolicy.from_files(
            Path(__file__).resolve().parents[1]
            / "data/synthetic/m4c/counterfactual_execution_policy.json",
            Path(__file__).resolve().parents[1] / "data/synthetic/m4c/context_value_registry.json",
        )
    )


def test_planner_derives_bounded_variants_in_policy_precedence() -> None:
    baseline = planned("M4-035").planned_verified_run
    value = planner().context_for(baseline)
    assert value == {"region": "REGION_BETA", "service_model": "SERVICE_BASIC"}
    plan = planner().plan(baseline, value)
    assert [item.variant_id for item in plan.variants] == ["cf-001", "cf-002", "cf-003"]
    assert [item.dimension for item in plan.variants] == ["region", "service_model", "region"]
    assert [item.operation for item in plan.variants] == [
        CounterfactualOperation.REPLACE,
        CounterfactualOperation.REPLACE,
        CounterfactualOperation.REMOVE,
    ]
    assert plan.baseline_plan_id == baseline.query_plan.plan_id
    assert plan.maximum_parallel_variants == 3


def test_planner_rebuilds_requested_variants_without_trusting_expected_outputs() -> None:
    baseline = planned("M4-036").planned_verified_run
    requested = M4CEvaluator._requested_variants(case("M4-036"))
    rebuilt = planner().plan(
        baseline, planner().context_for(baseline), requested_variants=requested
    )
    assert rebuilt.variants[0].variant_id == "M4-036-CF-01"
    assert rebuilt.variants[0].expected_decision.value == "ABSTAIN"
    assert rebuilt.variants[0].expected_reason_codes[0].value == "SCOPE_MISMATCH"


def test_planner_canonicalizes_supplied_context_and_does_not_mutate_it() -> None:
    baseline = planned("M4-035").planned_verified_run
    supplied = {"region": "region beta", "service_model": "service basic", "ignored": "value"}
    resolved = planner().context_for(baseline, supplied)
    assert resolved["region"] == "REGION_BETA"
    assert resolved["service_model"] == "SERVICE_BASIC"
    assert supplied["region"] == "region beta"
    assert "ignored" in resolved


def test_planner_fails_when_no_answer_changing_context_can_be_derived() -> None:
    baseline = planned("M4-035").planned_verified_run
    no_context = baseline.model_copy(
        update={
            "query_plan": baseline.query_plan.model_copy(update={"required_context_fields": []})
        },
        deep=True,
    )
    with pytest.raises(ValueError, match="could not derive"):
        planner().plan(no_context, {})


def test_planner_rejects_more_variants_than_policy_bound() -> None:
    baseline = planned("M4-035").planned_verified_run
    requested = M4CEvaluator._requested_variants(case("M4-035"))
    requested.append(requested[0].model_copy(update={"variant_id": "extra"}))
    with pytest.raises(ValueError, match="maximum_variants"):
        planner().plan(baseline, planner().context_for(baseline), requested_variants=requested)
