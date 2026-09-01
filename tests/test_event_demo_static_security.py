"""Static security tests for generated ER-B HTML."""

from __future__ import annotations

import re

from riskon.demo.html_renderer import render_dashboard_html, render_index_html
from riskon.demo.runner import DemoRun


def test_generated_html_has_no_external_assets_or_requests(
    event_demo_catalog: object,
    event_demo_dashboard: object,
    event_demo_run: DemoRun,
) -> None:
    index = render_index_html(
        event_demo_run.stories,
        event_demo_dashboard,  # type: ignore[arg-type]
        event_demo_catalog.presentation_copy,  # type: ignore[union-attr]
    )
    dashboard = render_dashboard_html(
        event_demo_dashboard,  # type: ignore[arg-type]
        event_demo_catalog.presentation_copy,  # type: ignore[union-attr]
    )
    for document in (index, dashboard):
        assert not re.search(r"<script\s+[^>]*\bsrc=", document, re.IGNORECASE)
        assert not re.search(r"<link\b", document, re.IGNORECASE)
        assert not re.search(r"\bhttps?://", document, re.IGNORECASE)
        assert not re.search(r"/(?:Users|Volumes)/", document)
        assert "<iframe" not in document.casefold()
        assert "<form" not in document.casefold()
        assert "connect-src 'none'" in document
