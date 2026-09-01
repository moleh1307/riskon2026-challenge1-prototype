"""ER-B renderer contract tests."""

from __future__ import annotations

from riskon.demo.html_renderer import CSP, render_dashboard_html, render_index_html
from riskon.demo.runner import DemoRun


def test_index_contains_all_sections_stories_and_required_footer(
    event_demo_catalog: object,
    event_demo_dashboard: object,
    event_demo_run: DemoRun,
) -> None:
    catalog = event_demo_catalog
    dashboard = event_demo_dashboard
    html = render_index_html(
        event_demo_run.stories,
        dashboard,  # type: ignore[arg-type]
        catalog.presentation_copy,  # type: ignore[union-attr]
    )
    assert html.count("ERB-00") >= 5
    assert "Live Product Stories" in html
    assert "Evaluation Dashboard" in html
    assert "Architecture &amp; Governance" in html
    assert "Synthetic local demonstration for RiskON 2026." in html
    assert CSP in html


def test_dashboard_renderer_is_standalone(
    event_demo_catalog: object, event_demo_dashboard: object
) -> None:
    html = render_dashboard_html(
        event_demo_dashboard,  # type: ignore[arg-type]
        event_demo_catalog.presentation_copy,  # type: ignore[union-attr]
    )
    assert html.startswith("<!doctype html>")
    assert '<meta http-equiv="Content-Security-Policy"' in html
    assert "Policy CI checks" in html
    assert "Expected vs actual final decision" in html
