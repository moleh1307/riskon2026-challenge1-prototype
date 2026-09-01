"""ER-B regression guards over the frozen evaluator stack."""

from __future__ import annotations

from riskon.demo.runner import DemoRun


def test_er_b_keeps_m0_to_m5b_regressions_green(event_demo_run: DemoRun) -> None:
    metrics = event_demo_run.m5b_document.metrics
    assert metrics.regression_matched == metrics.regression_expected == 45
    assert metrics.policy_ci_status_match_count == 55
    assert metrics.counterfactual_matched == metrics.counterfactual_expected == 4
    assert all(item.matched for item in event_demo_run.m5b_document.case_results)


def test_er_b_m4d_runtime_cases_remain_green(event_demo_run: DemoRun) -> None:
    assert set(event_demo_run.m4d_runs) == {
        "M4D-041",
        "M4D-042",
        "M4D-043",
        "M4D-044",
        "M4D-045",
    }
    assert all(
        run.final_verified_run.result.decision.value in {"ANSWER", "CLARIFY", "ABSTAIN"}
        for run in event_demo_run.m4d_runs.values()
    )
