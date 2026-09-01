"""M3 structured routing-explanation tests."""

from m3_helpers import routed_case


def test_person_explanation_contains_decisive_factors(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-024")
    explanation = routed.expert_route.explanation
    assert "mandate_match" in explanation.decisive_factors
    assert "network_proximity" in explanation.decisive_factors
    assert explanation.selected_candidate_factors
    assert explanation.alternative_candidates


def test_queue_explanation_contains_fallback_reason(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-026")
    explanation = routed.expert_route.explanation
    assert explanation.fallback_reason == "LOW_SCORE_OR_MARGIN"
    assert "functional_queue_selection" in explanation.decisive_factors
    assert explanation.alternative_candidates


def test_explanation_has_no_raw_query_fields(m3_pipeline) -> None:
    _case, _fixture, routed = routed_case(m3_pipeline, "M3-021")
    payload = routed.routing_diagnostics.model_dump(mode="json")
    assert all(
        field not in payload.get("routing_request", {})
        for field in ("original_query", "normalised_query", "answer_text", "retrieved_raw_text")
    )
