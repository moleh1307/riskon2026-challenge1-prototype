"""Bounded asyncio fan-out/fan-in executor for M4B workers."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from riskon.models import AnswerClaim, PlannedVerifiedRun
from riskon.orchestra.counterfactual_models import CounterfactualPlan
from riskon.orchestra.errors import OrchestraWorkerExecutionError
from riskon.orchestra.models import (
    AgentFinding,
    AgentTask,
    OrchestraContext,
    WorkerContext,
    WorkerResult,
)
from riskon.orchestra.source_safety import LocalCorpus, SourceSafetyContext
from riskon.orchestra.workers.base import Worker


class BoundedWorkerExecutor:
    """Run one wave concurrently with a hard discovery concurrency bound."""

    def __init__(self, workers: Mapping[str, Worker], max_parallel_discovery_workers: int) -> None:
        if max_parallel_discovery_workers < 1:
            raise ValueError("maximum_parallel_discovery_workers must be positive")
        self.workers = dict(workers)
        self.max_parallel_discovery_workers = max_parallel_discovery_workers

    async def execute_wave(
        self,
        tasks: list[AgentTask],
        baseline_run: PlannedVerifiedRun,
        orchestra_context: OrchestraContext,
        corpus: LocalCorpus,
        source_safety: SourceSafetyContext,
        *,
        prior_findings: list[AgentFinding] | None = None,
        candidate_claims: list[AnswerClaim] | None = None,
        counterfactual_plan: CounterfactualPlan | None = None,
        counterfactual_runner: object | None = None,
    ) -> list[WorkerResult]:
        """Fan out one wave and return results in deterministic task order."""

        if not tasks:
            return []
        semaphore = asyncio.Semaphore(self.max_parallel_discovery_workers)
        results: dict[str, WorkerResult] = {}

        async def run_one(task: AgentTask) -> None:
            worker = self.workers.get(task.agent_role)
            if worker is None:
                raise OrchestraWorkerExecutionError(
                    task.task_id,
                    task.agent_role,
                    "WorkerNotRegistered",
                )
            worker_context = WorkerContext(
                baseline_run=baseline_run,
                orchestra_context=orchestra_context,
                task=task,
                local_corpus_config=corpus,
                source_safety_policy=source_safety,
                prior_findings=list(prior_findings or []),
                candidate_claims=list(candidate_claims or []),
                counterfactual_plan=counterfactual_plan,
                counterfactual_runner=counterfactual_runner,
            )
            try:
                async with semaphore:
                    result = await worker.run(worker_context)
            except OrchestraWorkerExecutionError:
                raise
            except Exception as exc:
                raise OrchestraWorkerExecutionError(
                    task.task_id,
                    task.agent_role,
                    type(exc).__name__,
                ) from exc
            if (
                result.task_id != task.task_id
                or result.agent_id != task.agent_id
                or result.agent_role != task.agent_role
            ):
                raise OrchestraWorkerExecutionError(
                    task.task_id,
                    task.agent_role,
                    "WorkerResultContract",
                )
            results[task.task_id] = result

        try:
            async with asyncio.TaskGroup() as group:
                for task in tasks:
                    group.create_task(run_one(task))
        except* OrchestraWorkerExecutionError as errors:
            raise errors.exceptions[0] from None

        return [results[task.task_id] for task in sorted(tasks, key=lambda item: item.task_id)]
