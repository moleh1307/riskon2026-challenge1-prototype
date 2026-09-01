"""Tests for the 90-second live demonstration contract."""

from __future__ import annotations

from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.script_builder import render_live_demo_script


def test_live_demo_contract_has_three_story_handoffs(event_pitch_catalog: PitchCatalog) -> None:
    steps = event_pitch_catalog.live_demo.steps
    assert [step.story_id for step in steps] == ["ERB-001", "ERB-003", "ERB-005"]
    assert [(step.start_second, step.end_second) for step in steps] == [(0, 12), (12, 55), (55, 90)]


def test_live_demo_script_preserves_show_and_say_cues(event_pitch_catalog: PitchCatalog) -> None:
    rendered = render_live_demo_script(event_pitch_catalog)
    for step in event_pitch_catalog.live_demo.steps:
        assert step.say in rendered
        for cue in step.show:
            assert cue in rendered


def test_live_demo_script_is_explicitly_local_and_non_terminal(
    event_pitch_catalog: PitchCatalog,
) -> None:
    rendered = render_live_demo_script(event_pitch_catalog)
    assert "frozen local demo index and dashboard" in rendered
    assert "No terminal typing is required" in rendered
