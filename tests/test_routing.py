"""Structured expert routing tests."""

from pathlib import Path

from riskon.models import DetectedContext, NeedType, ReasonCode
from riskon.routing import ExpertRouter

DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def _router() -> ExpertRouter:
    return ExpertRouter.from_files(DATA_ROOT / "experts.json", DATA_ROOT / "routing_policy.json")


def test_scope_routes_to_jurisdiction_matching_brm() -> None:
    route = _router().route(
        DetectedContext(region="REGION_BETA", need_type=NeedType.COMPLEX_CASE),
        [ReasonCode.SCOPE_MISMATCH],
    )
    assert route.support_function == "BRM_SUITABILITY_LEAD"
    assert route.expert_id == "SYN-BRM-BETA-001"
    assert route.routing_confidence == 1.0


def test_technical_policy_and_approval_routes() -> None:
    router = _router()
    technical = router.route(
        DetectedContext(need_type=NeedType.TECHNICAL_FAILURE), [ReasonCode.TECHNICAL_FAILURE]
    )
    assert technical.expert_id == "SYN-IT-001"
    legal = router.route(DetectedContext(need_type=NeedType.POLICY_INTERPRETATION), [])
    assert legal.expert_id == "SYN-LEGAL-001"
    compliance = router.route(DetectedContext(need_type=NeedType.APPROVAL_REQUIRED), [])
    assert compliance.expert_id == "SYN-COMPLIANCE-001"


def test_routine_and_unknown_use_expected_queue_fallbacks() -> None:
    router = _router()
    routine = router.route(DetectedContext(need_type=NeedType.ROUTINE_PROCESS), [])
    assert routine.expert_id == "SYN-BFS-001"
    unknown = router.route(DetectedContext(), [])
    assert unknown.expert_id is None
    assert unknown.routing_confidence == 0.5


def test_brm_without_jurisdiction_uses_functional_queue() -> None:
    route = _router().route(DetectedContext(need_type=NeedType.COMPLEX_CASE), [])
    assert route.support_function == "BRM_SUITABILITY_LEAD"
    assert route.expert_id is None
    assert route.routing_confidence == 0.5
