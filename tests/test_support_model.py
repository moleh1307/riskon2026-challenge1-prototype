"""M3 support-model loading and structured mapping tests."""

from riskon.models import NeedType, ReasonCode, RoutingRequest
from riskon.support_model import SupportModel


def _request(need_type: NeedType, reason: ReasonCode) -> RoutingRequest:
    return RoutingRequest(
        need_type=need_type,
        reason_codes=[reason],
        routing_profile="default",
    )


def test_default_support_model_is_versioned(m3_config) -> None:
    path = m3_config.routing.profiles["default"].support_model
    model = SupportModel.from_file(path)
    assert model.support_model_version == "m3-v1"
    assert len(model.rules) == 10


def test_reason_mapping_has_priority_over_unknown_need(m3_config) -> None:
    path = m3_config.routing.profiles["default"].support_model
    model = SupportModel.from_file(path)
    assert model.resolve(_request(NeedType.UNKNOWN, ReasonCode.NO_EXPLICIT_SUPPORT)) == (
        "SUITABILITY_EXPERT_LEGAL"
    )


def test_need_mapping_selects_technical_support(m3_config) -> None:
    path = m3_config.routing.profiles["default"].support_model
    model = SupportModel.from_file(path)
    assert model.resolve(_request(NeedType.TECHNICAL_FAILURE, ReasonCode.TECHNICAL_FAILURE)) == (
        "IT_SERVICE_DESK"
    )


def test_unknown_structured_need_has_no_implicit_python_route(m3_config) -> None:
    path = m3_config.routing.profiles["default"].support_model
    model = SupportModel.from_file(path)
    assert model.resolve(_request(NeedType.UNKNOWN, ReasonCode.NO_RELEVANT_EVIDENCE)) is None
