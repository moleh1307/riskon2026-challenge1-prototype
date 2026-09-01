"""Validation and safe-summary tests for the M4C data contracts."""

import pytest
from m4c_helpers import planned

from riskon.models import Decision, ReasonCode
from riskon.orchestra.counterfactual_models import (
    ContextDelta,
    CounterfactualExecutionRequest,
    CounterfactualOperation,
    CounterfactualPlan,
    CounterfactualSummary,
    CounterfactualVariant,
    planned_result_summary,
)


def variant(
    *,
    operation: CounterfactualOperation = CounterfactualOperation.REPLACE,
    to_value: str | None = "REGION_ALPHA",
) -> CounterfactualVariant:
    return CounterfactualVariant(
        variant_id="variant-1",
        dimension="region",
        operation=operation,
        from_value="REGION_BETA",
        to_value=to_value,
        expectation_rule_id="EXACT_SCOPE_REPLACED",
        expected_decision=Decision.ABSTAIN,
        expected_reason_codes=[ReasonCode.SCOPE_MISMATCH],
    )


def test_context_delta_must_change_exactly_one_value() -> None:
    with pytest.raises(ValueError, match="must change"):
        ContextDelta(dimension="region", before="REGION_BETA", after="REGION_BETA")


@pytest.mark.parametrize(
    ("operation", "to_value", "message"),
    [
        (CounterfactualOperation.REPLACE, None, "require to_value"),
        (CounterfactualOperation.REMOVE, "REGION_ALPHA", "must have to_value=None"),
        (CounterfactualOperation.REPLACE, "REGION_BETA", "must change"),
    ],
)
def test_variant_operation_shape_is_closed(
    operation: CounterfactualOperation, to_value: str | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        variant(operation=operation, to_value=to_value)


def test_plan_rejects_duplicate_variants_and_parallel_overflow() -> None:
    first = variant()
    duplicate = first.model_copy(update={"variant_id": "variant-1"})
    with pytest.raises(ValueError, match="IDs must be unique"):
        CounterfactualPlan(
            plan_id="plan",
            baseline_plan_id="baseline",
            variants=[first, duplicate],
            maximum_parallel_variants=3,
        )

    second = first.model_copy(update={"variant_id": "variant-2"})
    with pytest.raises(ValueError, match="parallel variant bound"):
        CounterfactualPlan(
            plan_id="plan",
            baseline_plan_id="baseline",
            variants=[first, second],
            maximum_parallel_variants=1,
        )


@pytest.mark.parametrize(
    ("context", "message"),
    [
        ({"service_model": "SERVICE_BASIC"}, "missing from context"),
        ({"region": "REGION_ALPHA"}, "does not match"),
    ],
)
def test_execution_request_requires_matching_source_context(
    context: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        CounterfactualExecutionRequest(
            baseline_plan_id="baseline",
            original_query="query",
            structured_context=context,
            variant=variant(),
        )


def test_summary_counts_must_reconcile() -> None:
    with pytest.raises(ValueError, match="do not sum"):
        CounterfactualSummary(
            variant_count=2,
            passed_count=2,
            failed_count=1,
            scope_leak_count=1,
            routing_execution_count=0,
        )


def test_planned_result_summary_contains_only_admitted_transition_fields() -> None:
    baseline = planned("M4-035").planned_verified_run
    summary = planned_result_summary(baseline)
    assert set(summary) == {"decision", "reason_codes", "evidence_refs"}
    assert summary["decision"] == baseline.verified_run.result.decision.value
    assert summary["evidence_refs"] == sorted(
        set(baseline.verified_run.verification.evidence_refs)
        | {item.source_ref for item in baseline.verified_run.result.evidence}
    )
