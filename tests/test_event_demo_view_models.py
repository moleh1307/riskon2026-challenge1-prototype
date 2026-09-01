"""ER-B view-model safety tests."""

from __future__ import annotations

from riskon.demo.runner import DemoRun


def test_story_view_contains_only_bounded_evidence(event_demo_run: DemoRun) -> None:
    for story in event_demo_run.stories:
        for evidence in story.evidence:
            assert len(evidence.excerpt) <= 280
            assert "<script" not in evidence.excerpt.casefold()
            assert not evidence.provenance_ref.startswith(("http://", "https://", "/"))


def test_trace_is_structured_and_has_no_task_prompt(event_demo_run: DemoRun) -> None:
    for story in event_demo_run.stories:
        assert [step.order for step in story.orchestra_activity] == list(
            range(1, len(story.orchestra_activity) + 1)
        )
        for step in story.orchestra_activity:
            assert "objective" not in step.detail.casefold()
            assert "chain of thought" not in step.detail.casefold()
