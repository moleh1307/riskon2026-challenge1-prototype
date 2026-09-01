"""M3 routing-confidence contract tests."""

from m3_helpers import routed_case


def test_person_confidence_uses_frozen_heuristic_kind(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-021")
    assert routed.expert_route.route_mode.value == "PERSON"
    assert routed.expert_route.confidence_kind == "DETERMINISTIC_ROUTING_HEURISTIC_V1"
    assert 0.0 <= routed.expert_route.routing_confidence <= 1.0


def test_queue_confidence_is_exactly_point_five(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-026")
    assert routed.expert_route.routing_confidence == 0.500
    assert routed.expert_route.expected_fallback_reason == "LOW_SCORE_OR_MARGIN"


def test_confidence_is_not_presented_as_probability(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-024")
    assert "probability" not in routed.expert_route.confidence_kind.lower()
    assert "calibrated" not in routed.expert_route.confidence_kind.lower()
