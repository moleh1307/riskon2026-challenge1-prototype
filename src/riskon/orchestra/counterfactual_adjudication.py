"""Transition comparison and scope-leak objection handling for M4C."""

from __future__ import annotations

from dataclasses import dataclass

from riskon.models import PlannedVerifiedRun, ReasonCode
from riskon.orchestra.counterfactual_models import (
    ContextDelta,
    CounterfactualExecutionRequest,
    CounterfactualExecutionResult,
    CounterfactualPlan,
    CounterfactualSummary,
    CounterfactualVariant,
)
from riskon.orchestra.counterfactual_runner import CounterfactualRunner, run_maybe_async
from riskon.orchestra.models import MaterialObjection


@dataclass(frozen=True)
class CounterfactualAdjudication:
    """Results, objections, and counters retained after deterministic fan-in."""

    results: tuple[CounterfactualExecutionResult, ...]
    objections: tuple[MaterialObjection, ...]
    summary: CounterfactualSummary


class CounterfactualAdjudicator:
    """Compare expected transitions without deciding the final baseline answer."""

    async def execute(
        self,
        baseline: PlannedVerifiedRun,
        plan: CounterfactualPlan,
        structured_context: dict[str, str],
        runner: CounterfactualRunner,
        *,
        maximum_depth: int = 1,
        agent_id: str = "AGENT-M4-COUNTERFACTUAL-001",
    ) -> CounterfactualAdjudication:
        """Run variants concurrently, then sort all outcomes by variant ID."""

        import asyncio

        async def execute_one(
            variant: CounterfactualVariant,
        ) -> tuple[CounterfactualVariant, PlannedVerifiedRun]:
            request = CounterfactualExecutionRequest(
                baseline_plan_id=plan.baseline_plan_id,
                original_query=baseline.query_plan.original_query,
                structured_context=dict(structured_context),
                variant=variant,
            )
            planned = await run_maybe_async(
                runner,
                request,
                counterfactual_depth=maximum_depth,
            )
            if planned.query_plan.original_query != baseline.query_plan.original_query:
                raise ValueError("Counterfactual query text is not immutable")
            return variant, planned

        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(execute_one(variant)) for variant in plan.variants]
        executed: list[tuple[CounterfactualVariant, PlannedVerifiedRun]] = [
            task.result() for task in tasks
        ]
        return self.adjudicate(
            plan,
            executed,
            runner_backend=getattr(runner, "backend", "UNKNOWN"),
            agent_id=agent_id,
        )

    def adjudicate(
        self,
        plan: CounterfactualPlan,
        executed: list[tuple[CounterfactualVariant, PlannedVerifiedRun]],
        *,
        runner_backend: str,
        agent_id: str = "AGENT-M4-COUNTERFACTUAL-001",
    ) -> CounterfactualAdjudication:
        """Compare actual decisions and retain only safe structured outcomes."""

        ordered = sorted(executed, key=lambda item: item[0].variant_id)
        results: list[CounterfactualExecutionResult] = []
        objections: list[MaterialObjection] = []
        for variant, planned in ordered:
            result = planned.verified_run.result
            actual_reasons = list(result.reason_codes)
            expected_reasons = list(variant.expected_reason_codes)
            evidence_refs = sorted(
                set(planned.verified_run.verification.evidence_refs)
                | {item.source_ref for item in result.evidence}
            )
            passed = result.decision is variant.expected_decision and (
                actual_reasons == expected_reasons
            )
            results.append(
                CounterfactualExecutionResult(
                    variant_id=variant.variant_id,
                    context_delta=ContextDelta(
                        dimension=variant.dimension,
                        before=variant.from_value,
                        after=variant.to_value,
                    ),
                    expected_decision=variant.expected_decision,
                    actual_decision=result.decision,
                    expected_reason_codes=expected_reasons,
                    actual_reason_codes=actual_reasons,
                    actual_evidence_refs=evidence_refs,
                    passed=passed,
                    runner_backend=runner_backend,
                )
            )
            if not passed:
                objections.append(
                    MaterialObjection(
                        objection_id=f"objection:counterfactual:{variant.variant_id}",
                        agent_id=agent_id,
                        target_claim_id="ORCHESTRA_FINAL_ANSWER",
                        reason_code="COUNTERFACTUAL_SCOPE_LEAK",
                        materiality="MATERIAL",
                        evidence_refs=evidence_refs,
                        status="OPEN",
                        resolvable_by="HUMAN_REVIEW",
                    )
                )
        passed_count = sum(item.passed for item in results)
        summary = CounterfactualSummary(
            variant_count=len(results),
            passed_count=passed_count,
            failed_count=len(results) - passed_count,
            scope_leak_count=sum(not item.passed for item in results),
            routing_execution_count=0,
        )
        return CounterfactualAdjudication(
            results=tuple(sorted(results, key=lambda item: item.variant_id)),
            objections=tuple(sorted(objections, key=lambda item: item.objection_id)),
            summary=summary,
        )


def scope_mismatch_reason() -> list[ReasonCode]:
    """Return the typed final reason used when a scope transition leaks."""

    return [ReasonCode.SCOPE_MISMATCH]
