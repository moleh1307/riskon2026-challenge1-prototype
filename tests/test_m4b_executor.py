"""M4B executor contract and failure tests."""

import asyncio

import pytest
from m4b_helpers import case, context_for, m4b_config, planned

from riskon.orchestra.errors import OrchestraWorkerExecutionError
from riskon.orchestra.executor import BoundedWorkerExecutor
from riskon.orchestra.models import WorkerResult
from riskon.pipeline import RiskonPipeline


class _EmptyWorker:
    async def run(self, context):
        return WorkerResult(
            task_id=context.task.task_id,
            agent_id=context.task.agent_id,
            agent_role=context.task.agent_role,
        )


class _FailingWorker:
    async def run(self, _context):
        raise RuntimeError("source text must not escape")


def _executor_context(tmp_path, case_id: str = "M4-030"):
    config = m4b_config(tmp_path)
    pipeline = RiskonPipeline.from_milestone4b_config(config)
    fixture = planned(case_id)
    value = fixture.planned_verified_run
    case_value = case(case_id)
    orchestrator = pipeline._m4b_orchestrator
    assert orchestrator is not None
    tasks = orchestrator.selector.build_tasks(value.query_plan.plan_id, case_value.risk_signals)
    from riskon.orchestra.source_safety import SourceSafetyContext

    safety = SourceSafetyContext(
        policy=orchestrator.source_safety_policy,
        report=orchestrator.source_safety_policy.inspect(orchestrator.corpus),
    )
    return pipeline, value, context_for(case_value, fixture), orchestrator.corpus, safety, tasks


def test_empty_wave_is_a_noop(tmp_path) -> None:
    assert asyncio.run(BoundedWorkerExecutor({}, 3).execute_wave([], None, None, None, None)) == []


def test_executor_returns_results_in_task_order(tmp_path) -> None:
    _pipeline, value, context, corpus, safety, tasks = _executor_context(tmp_path)
    task = tasks[0]
    result = asyncio.run(
        BoundedWorkerExecutor({task.agent_role: _EmptyWorker()}, 3).execute_wave(
            [task], value, context, corpus, safety
        )
    )
    assert [item.task_id for item in result] == [task.task_id]


def test_missing_worker_is_typed_and_does_not_fallback(tmp_path) -> None:
    _pipeline, value, context, corpus, safety, tasks = _executor_context(tmp_path)
    with pytest.raises(OrchestraWorkerExecutionError) as error:
        asyncio.run(
            BoundedWorkerExecutor({}, 3).execute_wave(tasks[:1], value, context, corpus, safety)
        )
    assert error.value.task_id == tasks[0].task_id
    assert error.value.agent_role == tasks[0].agent_role
    assert error.value.cause_type == "WorkerNotRegistered"


def test_worker_exception_is_safe_and_has_no_raw_source(tmp_path) -> None:
    _pipeline, value, context, corpus, safety, tasks = _executor_context(tmp_path)
    task = tasks[0]
    with pytest.raises(OrchestraWorkerExecutionError) as error:
        asyncio.run(
            BoundedWorkerExecutor({task.agent_role: _FailingWorker()}, 3).execute_wave(
                [task], value, context, corpus, safety
            )
        )
    assert error.value.cause_type == "RuntimeError"
    assert "source text" not in str(error.value)
