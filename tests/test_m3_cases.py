"""M3 fixture-backed case and aggregate evaluator tests."""

from riskon.evaluation import M3Evaluator


def test_m3_evaluator_matches_all_routing_cases(m3_config) -> None:
    document = M3Evaluator(m3_config).run()
    assert document.metrics.m3_case_match_rate == 1.0
    assert [item.id for item in document.scenario_results] == [
        f"M3-{number:03d}" for number in range(21, 29)
    ]


def test_m3_evaluator_preserves_all_regressions(m3_config) -> None:
    document = M3Evaluator(m3_config).run()
    assert document.m0_regression == {"expected": 5, "matched": 5}
    assert document.m1_regression == {"expected": 7, "matched": 7}
    assert document.m2_regression == {"expected": 8, "matched": 8}


def test_m3_evaluator_reports_zero_safety_violations(m3_config) -> None:
    document = M3Evaluator(m3_config).run()
    metrics = document.metrics
    assert metrics.hard_constraint_violation_count == 0
    assert metrics.mandate_violation_count == 0
    assert metrics.region_violation_count == 0
    assert metrics.raw_query_dependency_count == 0
    assert metrics.network_violation_count == 0
