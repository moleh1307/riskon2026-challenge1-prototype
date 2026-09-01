"""Shared helpers for fixture-backed M3 tests."""

from pathlib import Path

from riskon.evaluation import M3Case, M3CaseSet, M3FixtureEnvelope
from riskon.pipeline import RiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M3_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m3"


def load_m3_case(case_id: str) -> M3Case:
    """Load one frozen M3 case from the canonical contract."""

    case_set = M3CaseSet.model_validate_json(
        (M3_ROOT / "evaluation_cases.json").read_text(encoding="utf-8")
    )
    return next(case for case in case_set.cases if case.id == case_id)


def load_m3_fixture(case: M3Case) -> M3FixtureEnvelope:
    """Load and validate a case's frozen upstream fixture."""

    prefix = "local://synthetic-m3/upstream-runs/"
    path = M3_ROOT / "upstream_runs" / case.upstream_fixture_ref.removeprefix(prefix)
    return M3FixtureEnvelope.model_validate_json(path.read_text(encoding="utf-8"))


def routed_case(pipeline: RiskonPipeline, case_id: str):
    """Route one case through route_planned and return all test context."""

    case = load_m3_case(case_id)
    fixture = load_m3_fixture(case)
    routed = pipeline.route_planned(
        fixture.planned_verified_run,
        case.routing_context,
        case.routing_profile,
    )
    return case, fixture, routed
