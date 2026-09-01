"""Deterministic barrier-based M4B fan-out tests."""

import asyncio

from m4b_helpers import case, context_for, m4b_config, planned

from riskon.orchestra.executor import BoundedWorkerExecutor
from riskon.orchestra.models import WorkerResult
from riskon.pipeline import RiskonPipeline


class _BarrierWorker:
    def __init__(self, started: set[str], all_started: asyncio.Event) -> None:
        self.started = started
        self.all_started = all_started

    async def run(self, context):
        self.started.add(context.task.agent_role)
        if len(self.started) == 2:
            self.all_started.set()
        await self.all_started.wait()
        return WorkerResult(
            task_id=context.task.task_id,
            agent_id=context.task.agent_id,
            agent_role=context.task.agent_role,
        )


def test_two_discovery_workers_reach_a_shared_barrier(tmp_path) -> None:
    async def exercise() -> set[str]:
        config = m4b_config(tmp_path)
        pipeline = RiskonPipeline.from_milestone4b_config(config)
        fixture = planned("M4-031")
        case_value = case("M4-031")
        value = fixture.planned_verified_run
        orchestrator = pipeline._m4b_orchestrator
        assert orchestrator is not None
        tasks = orchestrator.selector.build_tasks(value.query_plan.plan_id, case_value.risk_signals)
        discovery = [task for task in tasks if task.execution_wave.value == "DISCOVERY"]
        from riskon.orchestra.source_safety import SourceSafetyContext

        safety = SourceSafetyContext(
            policy=orchestrator.source_safety_policy,
            report=orchestrator.source_safety_policy.inspect(orchestrator.corpus),
        )
        started: set[str] = set()
        all_started = asyncio.Event()
        workers = {task.agent_role: _BarrierWorker(started, all_started) for task in discovery}
        execution = asyncio.create_task(
            BoundedWorkerExecutor(workers, 3).execute_wave(
                discovery,
                value,
                context_for(case_value, fixture),
                orchestrator.corpus,
                safety,
            )
        )
        await all_started.wait()
        assert started == {"EVIDENCE_SCOUT", "SCOPE_SENTINEL"}
        await execution
        return started

    assert asyncio.run(exercise()) == {"EVIDENCE_SCOUT", "SCOPE_SENTINEL"}
