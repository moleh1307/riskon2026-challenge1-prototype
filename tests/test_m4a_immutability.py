"""M4A baseline immutability tests."""

import json
from pathlib import Path

import pytest

from riskon.config import load_milestone4a_config
from riskon.models import PlannedVerifiedRun, RoutingContext
from riskon.orchestra.models import OrchestraContext, RiskSignal
from riskon.orchestra.policy import ActivationPolicy
from riskon.orchestra.runtime import M4AOrchestrator
from riskon.pipeline import RiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"


def load_fixture(case_id: str) -> PlannedVerifiedRun:
    """Load one frozen M4 planned run."""

    raw = json.loads((M4_ROOT / "upstream_runs" / f"{case_id}.planned.json").read_text())
    return PlannedVerifiedRun.model_validate(raw["planned_verified_run"])


def isolated_config(tmp_path: Path):
    """Return an M4A config with an isolated audit destination."""

    config = load_milestone4a_config(PROJECT_ROOT / "config" / "milestone4a.toml")
    orchestra = config.orchestra.model_copy(update={"generated_root": tmp_path / "m4a"})
    return config.model_copy(update={"orchestra": orchestra})


def context_for(case_id: str, profile: str, signal: str) -> OrchestraContext:
    """Build the profile-specific structured context."""

    planned = load_fixture(case_id)
    result = planned.verified_run.result
    routing = None
    if profile == "HUMAN_FIRST":
        routing = RoutingContext(
            need_type=result.detected_context.need_type,
            reason_codes=list(result.reason_codes),
            region=result.detected_context.region,
        )
    return OrchestraContext(
        risk_signals=() if not signal else (RiskSignal(signal),),
        routing_context=routing,
        routing_profile="default",
    )


@pytest.mark.parametrize(
    ("case_id", "profile", "signal"),
    [
        ("M4-029", "FAST_PATH", ""),
        ("M4-033", "SHORT_CIRCUIT_CLARIFY", "AMBIGUOUS_ACRONYM"),
        ("M4-034", "HUMAN_FIRST", "UNRESOLVED_REQUIRED_REFERENCE"),
        ("M4-039", "HUMAN_FIRST", "UNSUPPORTED_MODALITY"),
        ("M4-040", "HUMAN_FIRST", "APPROVAL_REQUIRED"),
    ],
)
def test_all_successful_paths_preserve_the_upstream_semantic_snapshot(
    tmp_path: Path,
    case_id: str,
    profile: str,
    signal: str,
) -> None:
    config = isolated_config(tmp_path)
    pipeline = RiskonPipeline.from_milestone4a_config(config)
    planned = load_fixture(case_id)
    before = planned.model_dump(mode="json")
    run = pipeline.orchestrate_planned(planned, context_for(case_id, profile, signal), profile)
    assert planned.model_dump(mode="json") == before
    assert run.baseline_run.model_dump(mode="json") == before
    assert run.final_verified_run.model_dump(mode="json") == before["verified_run"]
    if run.routed_run is not None:
        assert run.routed_run.planned_verified_run.model_dump(mode="json") == before


def test_unsupported_profile_preserves_input_before_raising(tmp_path: Path) -> None:
    config = isolated_config(tmp_path)
    pipeline = RiskonPipeline.from_milestone4a_config(config)
    planned = load_fixture("M4-030")
    before = planned.model_dump(mode="json")
    context = OrchestraContext(
        risk_signals=(RiskSignal("CRITICAL_CONTROL_RISK"),),
        routing_context=None,
        routing_profile="default",
    )
    with pytest.raises(Exception, match="requires M4B workers"):
        pipeline.orchestrate_planned(planned, context, "DUAL_CHECK")
    assert planned.model_dump(mode="json") == before


def test_runtime_detects_mutation_by_a_route_callback(tmp_path: Path) -> None:
    config = isolated_config(tmp_path)
    pipeline = RiskonPipeline.from_milestone4a_config(config)
    policy = ActivationPolicy.from_file(config.orchestra.activation_policy)
    planned = load_fixture("M4-034")
    result = planned.verified_run.result
    context = OrchestraContext(
        risk_signals=(RiskSignal("UNRESOLVED_REQUIRED_REFERENCE"),),
        routing_context=RoutingContext(
            need_type=result.detected_context.need_type,
            reason_codes=list(result.reason_codes),
        ),
        routing_profile="default",
    )

    def mutating_route(run: PlannedVerifiedRun, routing_context: RoutingContext, profile: str):
        run.query_plan.original_query = "MUTATED_BY_TEST"
        return pipeline.route_planned(run, routing_context, profile)

    orchestrator = M4AOrchestrator(policy, mutating_route)
    with pytest.raises(RuntimeError, match="mutated"):
        orchestrator.orchestrate_planned(planned, context, "HUMAN_FIRST")
