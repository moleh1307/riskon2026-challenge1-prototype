"""Regression guardrails proving ER-C remains downstream of ER-B."""

from __future__ import annotations

from riskon.demo.models import DashboardView
from riskon.demo.runner import DemoRun


def test_er_b_story_decisions_remain_frozen(event_demo_run: DemoRun) -> None:
    assert [
        (story.case_id, story.decision, story.activation_profile)
        for story in event_demo_run.stories
    ] == [
        ("ERB-001", "ANSWER", "FAST_PATH"),
        ("ERB-002", "CLARIFY", "SHORT_CIRCUIT_CLARIFY"),
        ("ERB-003", "ANSWER", "FULL_ORCHESTRA"),
        ("ERB-004", "ABSTAIN", "HUMAN_FIRST"),
        ("ERB-005", "ANSWER", "GOVERNED_EVOLUTION"),
    ]


def test_er_b_dashboard_metrics_are_the_pitch_source(event_demo_dashboard: DashboardView) -> None:
    values = {metric.id: metric.value for metric in event_demo_dashboard.metrics}
    assert values == {
        "m0_m4d_regression": "45/45",
        "m5b_governed_evolution": "5/5",
        "policy_ci_checks": "55/55",
        "counterfactual_transitions": "4/4",
        "scope_violations": "0",
        "unsupported_claims": "0",
        "unsafe_routing": "0",
        "automatic_approvals": "0",
        "automatic_activations": "0",
        "network_violations": "0",
    }


def test_er_c_report_consumes_the_frozen_er_b_cardinality(event_pitch_build: object) -> None:
    report = event_pitch_build.report  # type: ignore[attr-defined]
    assert report.slide_count == 12
    assert report.metric_source_count == 7
    assert report.metric_source_expected == 7
    assert report.hard_coded_evaluator_metric_count == 0


def test_er_c_does_not_claim_a_new_runtime_layer(event_pitch_catalog: object) -> None:
    catalog = event_pitch_catalog  # type: ignore[assignment]
    assert catalog.backup.independent_of == [
        "Python runtime",
        "CLI",
        "terminal",
        "live pipeline",
        "generated evaluator execution",
        "network",
        "server",
    ]
    assert catalog.config.security.server_enabled is False
