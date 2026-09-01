"""M1 metric definitions and required acceptance values."""

from riskon.evaluation import M1Evaluator, M1Metrics, _rate


def test_required_m1_metrics_are_perfect(m1_config) -> None:
    document = M1Evaluator(m1_config).run()
    metrics = document.metrics
    assert metrics.scenario_match_rate == 1.0
    assert metrics.decision_accuracy == 1.0
    assert metrics.clarification_accuracy == 1.0
    assert metrics.answer_case_claim_recall == 1.0
    assert metrics.critical_claim_recall == 1.0
    assert metrics.citation_validity == 1.0
    assert metrics.route_function_accuracy == 1.0
    assert metrics.route_expert_accuracy == 1.0
    assert metrics.correct_abstention_rate == 1.0
    assert metrics.unnecessary_abstention_rate == 0.0
    assert metrics.scope_violation_count == 0
    assert metrics.unsupported_claim_count == 0
    assert metrics.unresolved_reference_false_negative_count == 0
    assert metrics.network_violation_count == 0
    assert document.m0_regression == {"expected": 5, "matched": 5}


def test_rate_handles_empty_denominators_and_metrics_are_bounded() -> None:
    assert _rate(0, 0) == 1.0
    assert _rate(1, 2) == 0.5
    metrics = M1Metrics(
        scenario_match_rate=1.0,
        decision_accuracy=1.0,
        clarification_accuracy=1.0,
        answer_case_claim_recall=1.0,
        critical_claim_recall=1.0,
        citation_validity=1.0,
        route_function_accuracy=1.0,
        route_expert_accuracy=1.0,
        correct_abstention_rate=1.0,
        unnecessary_abstention_rate=0.0,
        scope_violation_count=0,
        unsupported_claim_count=0,
        unresolved_reference_false_negative_count=0,
        network_violation_count=0,
    )
    assert metrics.model_dump()["scenario_match_rate"] == 1.0
