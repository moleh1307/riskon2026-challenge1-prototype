"""M4C worker-graph, security, and final-gate guard tests."""

import asyncio
from pathlib import Path

import pytest
from m4c_helpers import M4C_ROOT, case, context_for, m4c_config, pipeline, planned

from riskon.evaluation import M4CEvaluator
from riskon.orchestra.counterfactual_models import CounterfactualSummary
from riskon.orchestra.counterfactual_planner import CounterfactualPlanner
from riskon.orchestra.counterfactual_policy import CounterfactualExecutionPolicy
from riskon.orchestra.counterfactual_runner import FrozenCounterfactualRunner
from riskon.orchestra.models import (
    AgentTask,
    ExecutionWave,
    OrchestraContext,
    RiskSignal,
    WorkerContext,
)
from riskon.orchestra.workers.counterfactual_sentinel import CounterfactualSentinel
from riskon.pipeline import RiskonPipeline


def _plan(case_id: str):
    baseline = planned(case_id).planned_verified_run
    planner = CounterfactualPlanner(
        CounterfactualExecutionPolicy.from_files(
            M4C_ROOT / "counterfactual_execution_policy.json",
            M4C_ROOT / "context_value_registry.json",
        )
    )
    return baseline, planner.plan(
        baseline,
        planner.context_for(baseline),
        requested_variants=M4CEvaluator._requested_variants(case(case_id)),
    )


def _sentinel_context(case_id: str) -> WorkerContext:
    baseline, plan = _plan(case_id)
    task = AgentTask(
        task_id=f"task:{baseline.query_plan.plan_id}:counterfactual_sentinel",
        plan_id=baseline.query_plan.plan_id,
        agent_id="AGENT-M4-COUNTERFACTUAL-001",
        agent_role="COUNTERFACTUAL_SENTINEL",
        execution_wave=ExecutionWave.VALIDATION,
        objective="Validate bounded context transitions.",
    )
    context = OrchestraContext(
        risk_signals=(RiskSignal("SCOPE_SENSITIVE"), RiskSignal("COUNTERFACTUAL_REQUIRED")),
        routing_profile="default",
        structured_context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
    )
    return WorkerContext(
        baseline_run=baseline,
        orchestra_context=context,
        task=task,
        local_corpus_config=object(),
        source_safety_policy=object(),
        counterfactual_plan=plan,
    )


def test_counterfactual_sentinel_fails_without_plan_or_runner() -> None:
    context = _sentinel_context("M4-035")
    with pytest.raises(ValueError, match="requires a CounterfactualPlan"):
        asyncio.run(
            CounterfactualSentinel().run(context.model_copy(update={"counterfactual_plan": None}))
        )
    with pytest.raises(TypeError, match="requires a counterfactual runner"):
        asyncio.run(CounterfactualSentinel().run(context))


def test_m4c_roles_are_derived_and_graph_is_fail_closed(tmp_path: Path) -> None:
    orchestrator = pipeline(tmp_path)._m4c_orchestrator
    assert orchestrator is not None
    signals = (RiskSignal("SCOPE_SENSITIVE"), RiskSignal("COUNTERFACTUAL_REQUIRED"))
    derived = orchestrator._roles(
        OrchestraContext(risk_signals=signals, routing_profile="default"), signals
    )
    assert "COUNTERFACTUAL_SENTINEL" in derived

    base = OrchestraContext(risk_signals=signals, routing_profile="default")
    with pytest.raises(ValueError, match="must be unique"):
        orchestrator._roles(
            base.model_copy(
                update={
                    "requested_agent_roles": ("COUNTERFACTUAL_SENTINEL", "COUNTERFACTUAL_SENTINEL")
                }
            ),
            signals,
        )
    with pytest.raises(ValueError, match="not implemented"):
        orchestrator._roles(
            base.model_copy(update={"requested_agent_roles": ("UNKNOWN",)}), signals
        )
    with pytest.raises(ValueError, match="requires COUNTERFACTUAL_SENTINEL"):
        orchestrator._roles(
            base.model_copy(update={"requested_agent_roles": ("EVIDENCE_SCOUT",)}), signals
        )


@pytest.mark.parametrize(
    ("attribute", "message"),
    [
        ("network_enabled", "network_enabled"),
        ("counterfactual_routing_enabled", "counterfactual_routing_enabled"),
        ("recursive_orchestration_enabled", "recursive_orchestration_enabled"),
        ("agent_to_agent_citation_enabled", "agent_to_agent_citation_enabled"),
    ],
)
def test_m4c_runtime_security_switches_fail_closed(
    tmp_path: Path, attribute: str, message: str
) -> None:
    orchestrator = pipeline(tmp_path / attribute)._m4c_orchestrator
    assert orchestrator is not None
    setattr(orchestrator, attribute, True)
    with pytest.raises(ValueError, match=message):
        orchestrator._validate_security()


def test_m4c_final_gate_returns_initial_result_when_no_variants_run(tmp_path: Path) -> None:
    orchestrator = pipeline(tmp_path)._m4c_orchestrator
    assert orchestrator is not None
    baseline = planned("M4-035").planned_verified_run
    initial = baseline.verified_run
    summary = CounterfactualSummary(
        variant_count=0,
        passed_count=0,
        failed_count=0,
        scope_leak_count=0,
        routing_execution_count=0,
    )
    final = orchestrator._final_verified_run(baseline, initial, [], summary)
    assert final == initial
    assert final is not initial


def test_m4c_rejects_a_plan_from_another_baseline(tmp_path: Path) -> None:
    config = m4c_config(tmp_path)
    pipe = RiskonPipeline.from_milestone4c_config(config)
    orchestrator = pipe._m4c_orchestrator
    assert orchestrator is not None
    envelope = planned("M4-035")
    baseline = envelope.planned_verified_run
    context = context_for(case("M4-035"), envelope).model_copy(
        update={"structured_context": orchestrator.planner.context_for(baseline)}
    )
    plan = orchestrator.planner.plan(
        baseline,
        context.structured_context,
        requested_variants=M4CEvaluator._requested_variants(case("M4-035")),
    ).model_copy(update={"baseline_plan_id": "wrong-baseline"})
    runner = FrozenCounterfactualRunner(
        config.orchestra.m4c.fixture_catalog,
        config.orchestra.m4c.fixture_root,
    )
    with pytest.raises(ValueError, match="baseline lineage"):
        pipe.orchestrate_planned(
            baseline,
            context,
            "FULL_ORCHESTRA",
            counterfactual_plan=plan,
            counterfactual_runner=runner,
        )
