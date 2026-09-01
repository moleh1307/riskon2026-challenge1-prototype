"""Shared fixtures for the M4B deterministic worker tests."""

from pathlib import Path

from riskon.config import Milestone4BConfig, load_milestone4b_config
from riskon.evaluation import M4ACase, M4ACaseSet, M4AFixtureEnvelope
from riskon.models import RoutingContext
from riskon.orchestra.models import OrchestraContext, WorkerContext
from riskon.pipeline import RiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"
M4B_CONFIG_PATH = PROJECT_ROOT / "config" / "milestone4b.toml"


def m4b_config(tmp_path: Path) -> Milestone4BConfig:
    """Load M4B and isolate only its generated output directory."""

    config = load_milestone4b_config(M4B_CONFIG_PATH)
    orchestra = config.orchestra.model_copy(update={"generated_root": tmp_path / "m4b"})
    return config.model_copy(update={"orchestra": orchestra})


def case(case_id: str) -> M4ACase:
    """Read one frozen M4 case contract."""

    case_set = M4ACaseSet.model_validate_json(
        (M4_ROOT / "evaluation_cases.json").read_text(encoding="utf-8")
    )
    return next(item for item in case_set.cases if item.id == case_id)


def planned(case_id: str) -> M4AFixtureEnvelope:
    """Read one frozen upstream wrapper."""

    return M4AFixtureEnvelope.model_validate_json(
        (M4_ROOT / "upstream_runs" / f"{case_id}.planned.json").read_text(encoding="utf-8")
    )


def context_for(case_value: M4ACase, planned_value: M4AFixtureEnvelope) -> OrchestraContext:
    """Construct the structured orchestration context used by the evaluator."""

    result = planned_value.planned_verified_run.verified_run.result
    routing_context = None
    if result.route is not None:
        routing_context = RoutingContext(
            need_type=result.detected_context.need_type,
            reason_codes=list(result.reason_codes),
            region=result.detected_context.region,
        )
    return OrchestraContext(
        risk_signals=tuple(case_value.risk_signals),
        routing_context=routing_context,
        routing_profile="default",
    )


def run_case(tmp_path: Path, case_id: str):
    """Build and execute one case in an isolated generated directory."""

    config = m4b_config(tmp_path)
    pipeline = RiskonPipeline.from_milestone4b_config(config)
    case_value = case(case_id)
    fixture = planned(case_id)
    planned_value = fixture.planned_verified_run
    run = pipeline.orchestrate_planned(
        planned_value,
        context_for(case_value, fixture),
        case_value.activation_profile.value,
    )
    return config, pipeline, case_value, planned_value, run


def worker_context_for(
    pipeline: RiskonPipeline,
    case_id: str,
    role: str,
) -> WorkerContext:
    """Build a direct worker context for role-level tests."""

    case_value = case(case_id)
    fixture = planned(case_id)
    planned_value = fixture.planned_verified_run
    orchestrator = pipeline._m4b_orchestrator
    if orchestrator is None:
        raise AssertionError("M4B pipeline did not build an orchestrator")
    tasks = orchestrator.selector.build_tasks(
        planned_value.query_plan.plan_id,
        tuple(case_value.risk_signals),
    )
    task = next(item for item in tasks if item.agent_role == role)
    from riskon.orchestra.source_safety import SourceSafetyContext

    safety = SourceSafetyContext(
        policy=orchestrator.source_safety_policy,
        report=orchestrator.source_safety_policy.inspect(orchestrator.corpus),
    )
    return WorkerContext(
        baseline_run=planned_value,
        orchestra_context=context_for(case_value, fixture),
        task=task,
        local_corpus_config=orchestrator.corpus,
        source_safety_policy=safety,
    )
