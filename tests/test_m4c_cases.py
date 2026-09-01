"""End-to-end M4C frozen-case acceptance tests."""

from pathlib import Path

from m4c_helpers import m4c_config

from riskon.evaluation import M4CEvaluator


def test_all_m4c_cases_match_transition_and_final_safety_contracts(tmp_path: Path) -> None:
    document = M4CEvaluator(m4c_config(tmp_path)).run()
    assert [item.id for item in document.scenario_results] == ["M4-035", "M4-036"]
    assert all(item.matched for item in document.scenario_results)
    assert document.metrics.safe_transition_count == 3
    assert document.metrics.scope_leak_count == 1
    assert document.metrics.unsafe_answer_block_count == 1


def test_m4c_regressions_and_worker_cardinality_are_exact(tmp_path: Path) -> None:
    document = M4CEvaluator(m4c_config(tmp_path)).run()
    assert document.m4_contract == {"expected": 12, "matched": 12}
    assert document.m4a_regression == {"expected": 5, "matched": 5}
    assert document.m4b_regression == {"expected": 5, "matched": 5}
    assert document.m0_m3_regression == {"expected": 28, "matched": 28}
    assert document.metrics.counterfactual_variant_count == 4
    assert document.metrics.worker_task_count == 7
    assert document.audit_schema_valid is True
