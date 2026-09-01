"""Leakage and injection checks for ER-B rendered output."""

from __future__ import annotations

from riskon.demo.html_renderer import render_story_html
from riskon.demo.models import EvidenceView
from riskon.demo.runner import DemoRun


def test_malicious_evidence_cannot_create_executable_markup(
    event_demo_catalog: object,
    event_demo_run: DemoRun,
) -> None:
    story = next(item for item in event_demo_run.stories if item.case_id == "ERB-001")
    malicious = EvidenceView(
        source_title="Synthetic injection",
        section_heading="Safe section",
        provenance_ref="local://synthetic-m4d/injection.html",
        criticality="STANDARD",
        excerpt="</script><script>alert('x')</script>",
    )
    altered = story.model_copy(update={"evidence": [malicious]})
    html = render_story_html(
        altered,
        event_demo_catalog.presentation_copy,  # type: ignore[union-attr]
    )
    assert "<script>alert" not in html.casefold()
    assert "</script><script>" not in html.casefold()
    assert r"\u003c/script\u003e\u003cscript\u003e" in html
    assert "/Users/" not in html
    assert "https://" not in html
