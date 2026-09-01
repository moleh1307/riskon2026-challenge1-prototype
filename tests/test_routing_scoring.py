"""M3 deterministic score and tie-break tests."""

from m3_helpers import routed_case


def test_default_routine_route_selects_primary_bfs(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-021")
    assert routed.expert_route.selected_expert_id == "SYN3-BFS-ALPHA-001"
    assert routed.expert_route.candidate_expert_ids[:2] == [
        "SYN3-BFS-ALPHA-001",
        "SYN3-BFS-ALPHA-002",
    ]


def test_network_proximity_breaks_legal_tie(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-024")
    assert routed.expert_route.selected_expert_id == "SYN3-LEGAL-GLOBAL-001"
    primary = next(
        item
        for item in routed.routing_diagnostics.candidates
        if item.expert_id == "SYN3-LEGAL-GLOBAL-001"
    )
    secondary = next(
        item
        for item in routed.routing_diagnostics.candidates
        if item.expert_id == "SYN3-LEGAL-GLOBAL-002"
    )
    assert (
        primary.component_scores["network_proximity"]
        > secondary.component_scores["network_proximity"]
    )


def test_missing_network_context_keeps_legal_scores_tied(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-026")
    assert routed.expert_route.route_mode.value == "FUNCTIONAL_QUEUE"
    legal = [
        item
        for item in routed.routing_diagnostics.candidates
        if item.eligible and item.expert_id.startswith("SYN3-LEGAL-")
    ]
    assert legal[0].total_score == legal[1].total_score
