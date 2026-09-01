"""Shared fixtures for the M4C counterfactual tests."""

from pathlib import Path

from riskon.config import Milestone4CConfig, load_milestone4c_config
from riskon.evaluation import M4AFixtureEnvelope, M4CCase, M4CCaseSet
from riskon.models import RoutingContext
from riskon.orchestra.models import OrchestraContext, RiskSignal
from riskon.pipeline import RiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4C_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4c"
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"
M4C_CONFIG_PATH = PROJECT_ROOT / "config" / "milestone4c.toml"


def m4c_config(tmp_path: Path) -> Milestone4CConfig:
    """Load M4C and isolate its generated output directory."""

    config = load_milestone4c_config(M4C_CONFIG_PATH)
    profile = config.orchestra.m4c.model_copy(update={"generated_root": tmp_path / "m4c"})
    orchestra = config.orchestra.model_copy(update={"m4c": profile})
    return config.model_copy(update={"orchestra": orchestra})


def case(case_id: str) -> M4CCase:
    """Read one frozen M4C case."""

    case_set = M4CCaseSet.model_validate_json(
        (M4C_ROOT / "evaluation_cases.json").read_text(encoding="utf-8")
    )
    return next(item for item in case_set.cases if item.id == case_id)


def planned(case_id: str) -> M4AFixtureEnvelope:
    """Read one frozen M4 upstream baseline."""

    return M4AFixtureEnvelope.model_validate_json(
        (M4_ROOT / "upstream_runs" / f"{case_id}.planned.json").read_text(encoding="utf-8")
    )


def pipeline(tmp_path: Path) -> RiskonPipeline:
    """Build an isolated M4C pipeline."""

    return RiskonPipeline.from_milestone4c_config(m4c_config(tmp_path))


def context_for(case_value: M4CCase, planned_value: M4AFixtureEnvelope) -> OrchestraContext:
    """Build the structured M4C activation envelope."""

    result = planned_value.planned_verified_run.verified_run.result
    routing_context = None
    if result.route is not None:
        routing_context = RoutingContext(
            need_type=result.detected_context.need_type,
            reason_codes=list(result.reason_codes),
            region=result.detected_context.region,
        )
    return OrchestraContext(
        risk_signals=(RiskSignal("SCOPE_SENSITIVE"), RiskSignal("COUNTERFACTUAL_REQUIRED")),
        routing_context=routing_context,
        routing_profile="default",
        requested_agent_roles=tuple(case_value.expected_agent_roles),
    )
