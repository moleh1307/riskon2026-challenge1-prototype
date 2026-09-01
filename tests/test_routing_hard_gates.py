"""M3 hard-gate exclusion tests."""

from m3_helpers import routed_case


def test_region_conflict_excludes_alpha_brm(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-023")
    diagnostic = next(
        item
        for item in routed.routing_diagnostics.candidates
        if item.expert_id == "SYN3-BRM-ALPHA-001"
    )
    assert diagnostic.eligible is False
    assert diagnostic.exclusion_reason == "REGION_CONFLICT"


def test_inactive_profile_is_never_eligible(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-028")
    diagnostic = next(
        item
        for item in routed.routing_diagnostics.candidates
        if item.expert_id == "SYN3-BRM-BETA-001"
    )
    assert diagnostic.exclusion_reason == "INACTIVE_PROFILE"
    assert routed.expert_route.selected_expert_id != diagnostic.expert_id


def test_unavailable_profile_is_never_eligible(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-027")
    diagnostic = next(
        item
        for item in routed.routing_diagnostics.candidates
        if item.expert_id == "SYN3-BFS-ALPHA-001"
    )
    assert diagnostic.exclusion_reason == "NOT_ACCEPTING_CASES"
    assert routed.expert_route.selected_expert_id == "SYN3-BFS-ALPHA-002"


def test_technical_route_excludes_non_it_functions(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-022")
    assert routed.expert_route.selected_expert_id == "SYN3-IT-GLOBAL-001"
    assert all(
        item.eligible is False
        for item in routed.routing_diagnostics.candidates
        if item.expert_id != "SYN3-IT-GLOBAL-001"
    )
