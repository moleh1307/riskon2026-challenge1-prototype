"""Tests for M4A HUMAN_FIRST delegation to the existing M3 router."""

import json
from pathlib import Path

import pytest

from riskon.config import load_milestone4a_config
from riskon.models import PlannedVerifiedRun, RoutingContext
from riskon.orchestra.models import OrchestraContext, RiskSignal
from riskon.pipeline import RiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"


def load_planned(case_id: str) -> PlannedVerifiedRun:
    """Load one executable frozen M4 input."""

    raw = json.loads((M4_ROOT / "upstream_runs" / f"{case_id}.planned.json").read_text())
    return PlannedVerifiedRun.model_validate(raw["planned_verified_run"])


def build_pipeline(tmp_path: Path) -> RiskonPipeline:
    """Build an isolated M4A pipeline."""

    config = load_milestone4a_config(PROJECT_ROOT / "config" / "milestone4a.toml")
    orchestra = config.orchestra.model_copy(update={"generated_root": tmp_path / "m4a"})
    return RiskonPipeline.from_milestone4a_config(
        config.model_copy(update={"orchestra": orchestra})
    )


@pytest.mark.parametrize(
    ("case_id", "signal", "expected_function"),
    [
        ("M4-034", "UNRESOLVED_REQUIRED_REFERENCE", "BUSINESS_FRONT_SUPPORT"),
        ("M4-039", "UNSUPPORTED_MODALITY", "BRM_SUITABILITY_LEAD"),
        ("M4-040", "APPROVAL_REQUIRED", "SUITABILITY_EXPERT_COMPLIANCE"),
    ],
)
def test_human_first_uses_existing_m3_route_and_creates_capsule(
    tmp_path: Path,
    case_id: str,
    signal: str,
    expected_function: str,
) -> None:
    pipeline = build_pipeline(tmp_path)
    planned = load_planned(case_id)
    result = planned.verified_run.result
    routing_context = RoutingContext(
        need_type=result.detected_context.need_type,
        reason_codes=list(result.reason_codes),
        region=result.detected_context.region,
    )
    run = pipeline.orchestrate_planned(
        planned,
        OrchestraContext(
            risk_signals=(RiskSignal(signal),),
            routing_context=routing_context,
            routing_profile="default",
        ),
        "HUMAN_FIRST",
    )
    assert run.final_verified_run.result.decision.value == "ABSTAIN"
    assert run.routed_run is not None
    assert run.routed_run.expert_route is not None
    assert run.routed_run.expert_route.support_function == expected_function
    assert run.case_capsule is not None
    assert run.case_capsule.support_function == expected_function
    assert run.case_capsule.baseline_trace_id == result.trace_id
    assert run.case_capsule.reason_codes == result.reason_codes
    assert run.case_capsule.route_mode == run.routed_run.expert_route.route_mode
    assert run.orchestra_metrics.active_agent_count == 0


def test_human_first_rejects_a_route_callback_that_returns_no_route(tmp_path: Path) -> None:
    config = load_milestone4a_config(PROJECT_ROOT / "config" / "milestone4a.toml")
    orchestra = config.orchestra.model_copy(update={"generated_root": tmp_path / "m4a"})
    pipeline = RiskonPipeline.from_milestone4a_config(
        config.model_copy(update={"orchestra": orchestra})
    )
    planned = load_planned("M4-034")
    result = planned.verified_run.result
    context = OrchestraContext(
        risk_signals=(RiskSignal("UNRESOLVED_REQUIRED_REFERENCE"),),
        routing_context=RoutingContext(
            need_type=result.detected_context.need_type,
            reason_codes=list(result.reason_codes),
        ),
        routing_profile="default",
    )
    original = pipeline._m4a_orchestrator
    assert original is not None
    assert context.routing_context is not None

    def bad_route(*_args: object) -> object:
        return pipeline.route_planned(planned, context.routing_context, "unknown-profile")

    original.route_planned = bad_route
    with pytest.raises(ValueError, match="no expert route|Unknown M3 routing profile"):
        pipeline.orchestrate_planned(planned, context, "HUMAN_FIRST")
