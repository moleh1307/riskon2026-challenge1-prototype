"""Accessibility checks for the ER-B static page."""

from __future__ import annotations

from riskon.demo.html_renderer import render_index_html
from riskon.demo.runner import DemoRun


def test_index_has_keyboard_tabs_focus_states_and_print_layout(
    event_demo_catalog: object,
    event_demo_dashboard: object,
    event_demo_run: DemoRun,
) -> None:
    html = render_index_html(
        event_demo_run.stories,
        event_demo_dashboard,  # type: ignore[arg-type]
        event_demo_catalog.presentation_copy,  # type: ignore[union-attr]
    )
    assert 'role="tablist"' in html
    assert html.count('role="tab"') == 3
    assert 'aria-selected="true"' in html
    assert 'aria-controls="stories-panel"' in html
    assert 'role="tabpanel"' in html
    assert ":focus-visible" in html
    assert "@media print" in html
    assert 'aria-label="Demo sections"' in html
