"""ER-B dashboard metric tests."""

from __future__ import annotations

from riskon.demo.models import DashboardView


def test_dashboard_uses_current_canonical_values(event_demo_dashboard: DashboardView) -> None:
    values = {metric.id: metric.value for metric in event_demo_dashboard.metrics}
    assert values["m0_m4d_regression"] == "45/45"
    assert values["m5b_governed_evolution"] == "5/5"
    assert values["policy_ci_checks"] == "55/55"
    assert values["counterfactual_transitions"] == "4/4"
    assert values["automatic_approvals"] == "0"
    assert values["automatic_activations"] == "0"
    assert values["network_violations"] == "0"


def test_dashboard_labels_every_metric_source(event_demo_dashboard: DashboardView) -> None:
    assert len(event_demo_dashboard.metrics) == 10
    assert all(
        metric.source and "hardcode" not in metric.source.casefold()
        for metric in event_demo_dashboard.metrics
    )
    assert len(event_demo_dashboard.safety_metrics) == 7
