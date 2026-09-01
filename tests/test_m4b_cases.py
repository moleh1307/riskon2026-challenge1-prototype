"""End-to-end M4B case contract tests."""

from pathlib import Path

from m4b_helpers import m4b_config

from riskon.evaluation import M4BEvaluator


def test_all_five_m4b_cases_match_including_final_safety_outcomes(tmp_path: Path) -> None:
    document = M4BEvaluator(m4b_config(tmp_path)).run()
    assert [item.id for item in document.scenario_results] == [
        "M4-030",
        "M4-031",
        "M4-032",
        "M4-037",
        "M4-038",
    ]
    assert all(item.matched for item in document.scenario_results)
    assert document.metrics.recovered_answer_accuracy == 1.0
    assert document.metrics.final_safe_abstention_accuracy == 1.0
    assert document.metrics.prompt_injection_safe_answer_accuracy == 1.0


def test_m4b_metrics_and_regression_cardinalities_are_exact(tmp_path: Path) -> None:
    document = M4BEvaluator(m4b_config(tmp_path)).run()
    assert document.m4_contract == {"expected": 12, "matched": 12}
    assert document.m4a_regression == {"expected": 5, "matched": 5}
    assert document.m0_regression == {"expected": 5, "matched": 5}
    assert document.m1_regression == {"expected": 7, "matched": 7}
    assert document.m2_regression == {"expected": 8, "matched": 8}
    assert document.m3_regression == {"expected": 8, "matched": 8}
    assert document.metrics.worker_task_count == 12
    assert document.metrics.required_finding_recall == 1.0
    assert document.metrics.required_material_objection_recall == 1.0
