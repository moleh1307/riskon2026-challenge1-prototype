"""Deterministic rendering tests for ER-B."""

from __future__ import annotations

from riskon.demo.html_renderer import render_dashboard_html, render_index_html
from riskon.demo.runner import DemoRun


def test_same_payload_renders_byte_identically(
    event_demo_catalog: object,
    event_demo_dashboard: object,
    event_demo_run: DemoRun,
) -> None:
    first = render_index_html(
        event_demo_run.stories,
        event_demo_dashboard,  # type: ignore[arg-type]
        event_demo_catalog.presentation_copy,  # type: ignore[union-attr]
    )
    second = render_index_html(
        event_demo_run.stories,
        event_demo_dashboard,  # type: ignore[arg-type]
        event_demo_catalog.presentation_copy,  # type: ignore[union-attr]
    )
    assert first == second
    assert render_dashboard_html(
        event_demo_dashboard,  # type: ignore[arg-type]
        event_demo_catalog.presentation_copy,  # type: ignore[union-attr]
    ) == render_dashboard_html(
        event_demo_dashboard,  # type: ignore[arg-type]
        event_demo_catalog.presentation_copy,  # type: ignore[union-attr]
    )
