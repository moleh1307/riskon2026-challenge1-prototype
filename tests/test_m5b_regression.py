"""M5B in-process regression gate."""

from m5b_helpers import config

from riskon.governance.regression_gate import RegressionGate, _contract


def test_regression_gate_runs_frozen_upstream_stack_in_process() -> None:
    result = RegressionGate(config()).run()
    assert result.expected == 45
    assert result.matched == 45
    assert result.passed is True
    assert result.network_enabled is False
    assert set(result.suites) == {"M4D", "M4A", "M4B", "M4C", "M0_M3"}


def test_regression_gate_contract_keeps_only_expected_and_matched() -> None:
    assert _contract({"expected": "5", "matched": "4", "ignored": 99}) == {
        "expected": 5,
        "matched": 4,
    }
    assert _contract({}) == {"expected": 0, "matched": 0}


def test_regression_gate_fails_closed_when_upstream_evaluator_errors(monkeypatch) -> None:
    import riskon.m4d_evaluation

    class BrokenEvaluator:
        def __init__(self, config):
            del config

        def run(self):
            raise RuntimeError("synthetic regression error")

    monkeypatch.setattr(riskon.m4d_evaluation, "M4DEvaluator", BrokenEvaluator)
    result = RegressionGate(config()).run()
    assert result.expected == 45
    assert result.matched == 0
    assert result.passed is False
    assert result.network_enabled is True
