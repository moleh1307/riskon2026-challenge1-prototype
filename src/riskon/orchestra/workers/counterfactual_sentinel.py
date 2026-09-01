"""Bounded worker for decision transitions under structured context changes."""

from riskon.orchestra.counterfactual_adjudication import CounterfactualAdjudicator
from riskon.orchestra.counterfactual_runner import CounterfactualRunner
from riskon.orchestra.models import FindingStance, WorkerContext, WorkerResult
from riskon.orchestra.workers.base import make_finding


class CounterfactualSentinel:
    """Execute and adjudicate one bounded counterfactual plan."""

    async def run(self, context: WorkerContext) -> WorkerResult:
        plan = context.counterfactual_plan
        runner = context.counterfactual_runner
        if plan is None:
            raise ValueError("Counterfactual sentinel requires a CounterfactualPlan")
        if not isinstance(runner, CounterfactualRunner):
            raise TypeError("Counterfactual sentinel requires a counterfactual runner")
        adjudication = await CounterfactualAdjudicator().execute(
            context.baseline_run,
            plan,
            context.orchestra_context.structured_context,
            runner,
        )
        refs = sorted(
            {
                reference
                for result in adjudication.results
                for reference in result.actual_evidence_refs
            }
        )
        leaking = adjudication.summary.scope_leak_count > 0
        finding = make_finding(
            context,
            1,
            claim_id=(
                "counterfactual_scope_transition" if leaking else "counterfactual_transitions"
            ),
            stance=FindingStance.CHALLENGE if leaking else FindingStance.NEUTRAL,
            evidence_refs=refs,
            source_scope="COUNTERFACTUAL_RUN",
            criticality="CRITICAL",
            limitations=["Diagnostic only; counterfactual results are not authoritative evidence"],
        )
        return WorkerResult(
            task_id=context.task.task_id,
            agent_id=context.task.agent_id,
            agent_role=context.task.agent_role,
            findings=[finding],
            material_objections=list(adjudication.objections),
            counterfactual_results=list(adjudication.results),
        )
