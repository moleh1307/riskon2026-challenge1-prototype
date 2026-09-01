"""M0 compatibility and deterministic M1 rerun tests."""

import json
from pathlib import Path

from riskon.config import load_config
from riskon.evaluation import M1Evaluator
from riskon.models import QueryInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_m0_config_and_scenario_fixture_remain_unchanged() -> None:
    config = load_config(PROJECT_ROOT / "config" / "milestone0.toml")
    scenarios = json.loads((config.paths.data_root / "scenarios.json").read_text(encoding="utf-8"))
    assert len(scenarios) == 5
    assert [scenario["id"] for scenario in scenarios] == [
        "M0-001",
        "M0-002",
        "M0-003",
        "M0-004",
        "M0-005",
    ]
    assert config.security.network_enabled is False


def test_m0_pipeline_run_semantics_are_not_replaced_by_verified_interface(pipeline) -> None:
    query = QueryInput(query="What is the direct rule for a delegated order giver?")
    provisional = pipeline.run(query)
    assert provisional.decision.value == "ANSWER"
    assert provisional.answer is not None
    assert pipeline._verification_engine is None


def test_plain_m0_pipeline_rejects_run_verified(pipeline) -> None:
    try:
        pipeline.run_verified(QueryInput(query="plain query"))
    except ValueError as exc:
        assert "milestone1" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("M0-only pipeline unexpectedly exposed M1 verification")


def test_m1_evaluator_reports_five_case_m0_regression(m1_config) -> None:
    document = M1Evaluator(m1_config).run()
    assert document.m0_regression == {"expected": 5, "matched": 5}
    assert document.scenario_results[0].id == "M0-001"
    assert document.scenario_results[4].id == "M0-005"


def test_m1_rerun_has_identical_metrics_and_case_outcomes(m1_config, tmp_path) -> None:
    first = M1Evaluator(m1_config).run()
    second_config = m1_config.model_copy(update={"generated_root": tmp_path / "second"})
    second = M1Evaluator(second_config).run()
    assert first.metrics == second.metrics
    first_cases = [
        (item.id, item.matched, item.failures, item.actual_decision, item.actual_reason_codes)
        for item in first.scenario_results
    ]
    second_cases = [
        (item.id, item.matched, item.failures, item.actual_decision, item.actual_reason_codes)
        for item in second.scenario_results
    ]
    assert first_cases == second_cases


def test_m1_output_never_contains_absolute_source_path(m1_config) -> None:
    document = M1Evaluator(m1_config).run()
    serialized = json.dumps(document.model_dump(mode="json"))
    assert "/Users/" not in serialized
    assert "local://synthetic" in serialized
