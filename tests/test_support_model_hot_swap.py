"""M3 support-model/profile hot-swap tests."""

from m3_helpers import load_m3_case, load_m3_fixture


def test_support_v2_replaces_the_inactive_beta_expert(m3_pipeline) -> None:
    case = load_m3_case("M3-028")
    fixture = load_m3_fixture(case)
    routed = m3_pipeline.route_planned(
        fixture.planned_verified_run, case.routing_context, "support_v2"
    )
    assert routed.expert_route.support_model_version == "m3-v2"
    assert routed.expert_route.selected_expert_id == "SYN3-BRM-BETA-002"


def test_default_profile_keeps_the_v1_beta_expert(m3_pipeline) -> None:
    case = load_m3_case("M3-023")
    fixture = load_m3_fixture(case)
    routed = m3_pipeline.route_planned(
        fixture.planned_verified_run, case.routing_context, "default"
    )
    assert routed.expert_route.support_model_version == "m3-v1"
    assert routed.expert_route.selected_expert_id == "SYN3-BRM-BETA-001"
