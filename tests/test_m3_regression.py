"""M3 additive integration and legacy-conflict tests."""

from m3_helpers import load_m3_case, load_m3_fixture

from riskon.models import Route, RoutingContext


def test_answer_is_not_routed(m3_pipeline, m2_pipeline) -> None:
    planned = m2_pipeline.run_planned(
        __import__("riskon.models", fromlist=["QueryInput"]).QueryInput(
            query=(
                "Which session alerts are active for Advisory Location Alpha and a Premium mandate?"
            ),
            context={"location": "ALPHA", "mandate": "PREMIUM"},
        )
    )
    assert planned.verified_run.result.decision.value == "ANSWER"
    context = RoutingContext(
        need_type=planned.verified_run.result.detected_context.need_type,
        reason_codes=[],
    )
    routed = m3_pipeline.route_planned(planned, context, "default")
    assert routed.expert_route is None
    assert routed.routing_diagnostics.status.value == "NOT_ROUTED_DECISION"


def test_legacy_route_conflict_fails_closed(m3_pipeline) -> None:
    case = load_m3_case("M3-021")
    fixture = load_m3_fixture(case)
    original = fixture.planned_verified_run
    result = original.verified_run.result
    assert result.route is not None
    conflicting_route = Route(
        support_function="IT_SERVICE_DESK",
        expert_id=None,
        routing_reason=result.route.routing_reason,
        routing_confidence=result.route.routing_confidence,
    )
    conflicting_result = result.model_copy(update={"route": conflicting_route})
    conflicting_verified = original.verified_run.model_copy(update={"result": conflicting_result})
    conflicting_planned = original.model_copy(update={"verified_run": conflicting_verified})
    routed = m3_pipeline.route_planned(conflicting_planned, case.routing_context, "default")
    assert routed.expert_route is None
    assert routed.routing_diagnostics.status.value == "BLOCKED"
    assert routed.routing_diagnostics.reason_codes == ["LEGACY_ROUTE_CONFLICT"]


def test_route_planned_does_not_mutate_fixture(m3_pipeline) -> None:
    case = load_m3_case("M3-024")
    fixture = load_m3_fixture(case)
    before = fixture.planned_verified_run.model_dump(mode="json")
    m3_pipeline.route_planned(fixture.planned_verified_run, case.routing_context, "default")
    assert fixture.planned_verified_run.model_dump(mode="json") == before
