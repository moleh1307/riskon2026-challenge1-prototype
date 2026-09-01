"""Deterministic one-dimension counterfactual planning."""

from __future__ import annotations

from collections.abc import Iterable

from riskon.models import PlannedVerifiedRun
from riskon.orchestra.counterfactual_models import (
    CounterfactualOperation,
    CounterfactualPlan,
    CounterfactualVariant,
)
from riskon.orchestra.counterfactual_policy import CounterfactualExecutionPolicy


class CounterfactualPlanner:
    """Build bounded variants from context, evidence scope, and policy only."""

    def __init__(self, policy: CounterfactualExecutionPolicy) -> None:
        self.policy = policy

    def plan(
        self,
        baseline: PlannedVerifiedRun,
        structured_context: dict[str, str] | None = None,
        *,
        requested_variants: Iterable[CounterfactualVariant] | None = None,
    ) -> CounterfactualPlan:
        """Return a deterministic plan without reading evaluation-case files."""

        context = self.context_for(baseline, structured_context)
        source_scope_text = " ".join(
            item.excerpt for item in baseline.verified_run.result.evidence if item.excerpt
        )
        required = list(baseline.query_plan.required_context_fields)
        if requested_variants is None:
            variants = self._derive_variants(
                baseline,
                context,
                source_scope_text,
                required,
            )
        else:
            variants = [
                self.policy.build_variant(
                    variant_id=item.variant_id,
                    dimension=item.dimension,
                    operation=item.operation,
                    from_value=item.from_value,
                    to_value=item.to_value,
                    source_scope_text=source_scope_text,
                    required_context_fields=required,
                )
                for item in requested_variants
            ]
        if not variants:
            raise ValueError("M4C could not derive a bounded counterfactual variant")
        if len(variants) > self.policy.maximum_variants_per_case:
            raise ValueError("M4C case exceeds maximum_variants_per_case")
        return CounterfactualPlan(
            plan_id=f"counterfactual:{baseline.query_plan.plan_id}",
            baseline_plan_id=baseline.query_plan.plan_id,
            variants=variants,
            maximum_parallel_variants=self.policy.maximum_parallel_variants,
        )

    def context_for(
        self,
        baseline: PlannedVerifiedRun,
        supplied: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Resolve the registered context that a runner must copy."""

        return self._context(baseline, supplied)

    def _derive_variants(
        self,
        baseline: PlannedVerifiedRun,
        context: dict[str, str],
        source_scope_text: str,
        required_fields: list[str],
    ) -> list[CounterfactualVariant]:
        variants: list[CounterfactualVariant] = []
        for ordinal, (dimension, operation) in enumerate(
            self.policy.candidate_variant_specs(), start=1
        ):
            if dimension not in required_fields:
                continue
            current = context.get(dimension)
            if current is None:
                continue
            target = (
                self.policy.registry.replacement_for(dimension, current)
                if operation is CounterfactualOperation.REPLACE
                else None
            )
            if operation is CounterfactualOperation.REPLACE and target is None:
                continue
            variants.append(
                self.policy.build_variant(
                    variant_id=f"cf-{ordinal:03d}",
                    dimension=dimension,
                    operation=operation,
                    from_value=current,
                    to_value=target,
                    source_scope_text=source_scope_text,
                    required_context_fields=required_fields,
                )
            )
            if len(variants) >= self.policy.maximum_variants_per_case:
                break
        del baseline
        return variants

    def _context(
        self,
        baseline: PlannedVerifiedRun,
        supplied: dict[str, str] | None,
    ) -> dict[str, str]:
        """Resolve registered values without inventing free-form alternatives."""

        context = dict(supplied or {})
        required = list(baseline.query_plan.required_context_fields)
        query_text = " ".join(
            [
                baseline.query_plan.original_query,
                baseline.query_plan.normalised_query,
                *baseline.query_plan.canonical_terms,
            ]
        )
        inferred = self.policy.registry.infer_context(required, query_text)
        detected_region = baseline.verified_run.result.detected_context.region
        if "region" in required and detected_region:
            inferred["region"] = self.policy.registry.canonical_value("region", detected_region)
        for dimension in required:
            if dimension in context:
                context[dimension] = self.policy.registry.canonical_value(
                    dimension, context[dimension]
                )
            elif dimension in inferred:
                context[dimension] = inferred[dimension]
        return context
