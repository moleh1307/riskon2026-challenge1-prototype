"""Frozen data contracts for bounded M4C counterfactual execution."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from riskon.models import Decision, PlannedVerifiedRun, ReasonCode


class CounterfactualOperation(StrEnum):
    """Closed set of context mutations allowed by M4C."""

    REPLACE = "REPLACE"
    REMOVE = "REMOVE"


class ContextDelta(BaseModel):
    """One changed structured-context field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: str = Field(min_length=1)
    before: str | None = None
    after: str | None = None

    @model_validator(mode="after")
    def validate_changed_value(self) -> "ContextDelta":
        if self.before == self.after:
            raise ValueError("ContextDelta must change exactly one value")
        return self


class CounterfactualVariant(BaseModel):
    """One policy-derived, one-dimension counterfactual operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    operation: CounterfactualOperation
    from_value: str = Field(min_length=1)
    to_value: str | None = None
    expectation_rule_id: str = Field(min_length=1)
    expected_decision: Decision
    expected_reason_codes: list[ReasonCode] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_operation_shape(self) -> "CounterfactualVariant":
        if self.operation is CounterfactualOperation.REPLACE and self.to_value is None:
            raise ValueError("REPLACE counterfactuals require to_value")
        if self.operation is CounterfactualOperation.REMOVE and self.to_value is not None:
            raise ValueError("REMOVE counterfactuals must have to_value=None")
        if self.to_value == self.from_value:
            raise ValueError("Counterfactual replacement must change the value")
        return self


class CounterfactualPlan(BaseModel):
    """Bounded deterministic plan executed by the counterfactual sentinel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_id: str = Field(min_length=1)
    baseline_plan_id: str = Field(min_length=1)
    variants: list[CounterfactualVariant] = Field(min_length=1)
    maximum_parallel_variants: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_unique_variants(self) -> "CounterfactualPlan":
        identifiers = [item.variant_id for item in self.variants]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Counterfactual variant IDs must be unique")
        if len(self.variants) > self.maximum_parallel_variants:
            raise ValueError("Counterfactual plan exceeds its parallel variant bound")
        return self


class CounterfactualExecutionRequest(BaseModel):
    """Input envelope passed to one counterfactual runner."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_plan_id: str = Field(min_length=1)
    original_query: str = Field(min_length=1)
    structured_context: dict[str, str] = Field(default_factory=dict)
    variant: CounterfactualVariant

    @model_validator(mode="after")
    def validate_baseline_context(self) -> "CounterfactualExecutionRequest":
        if self.variant.dimension not in self.structured_context:
            raise ValueError("Counterfactual source dimension is missing from context")
        if self.structured_context[self.variant.dimension] != self.variant.from_value:
            raise ValueError("Counterfactual from_value does not match structured context")
        return self


class CounterfactualExecutionResult(BaseModel):
    """Safe result summary for one counterfactual run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str = Field(min_length=1)
    context_delta: ContextDelta
    expected_decision: Decision
    actual_decision: Decision
    expected_reason_codes: list[ReasonCode] = Field(default_factory=list)
    actual_reason_codes: list[ReasonCode] = Field(default_factory=list)
    actual_evidence_refs: list[str] = Field(default_factory=list)
    passed: bool
    runner_backend: str = Field(min_length=1)


class CounterfactualSummary(BaseModel):
    """Aggregate transition and safety counters."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    scope_leak_count: int = Field(ge=0)
    routing_execution_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "CounterfactualSummary":
        if self.passed_count + self.failed_count != self.variant_count:
            raise ValueError("Counterfactual pass/fail counts do not sum to variant count")
        return self


def planned_result_summary(planned: PlannedVerifiedRun) -> dict[str, Any]:
    """Extract only the decision fields admitted to a transition comparison."""

    result = planned.verified_run.result
    return {
        "decision": result.decision.value,
        "reason_codes": [reason.value for reason in result.reason_codes],
        "evidence_refs": sorted(
            set(planned.verified_run.verification.evidence_refs)
            | {item.source_ref for item in result.evidence}
        ),
    }
