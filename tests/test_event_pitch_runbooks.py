"""Presenter runbook and report-generation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.demo_runbook import render_backup_demo_runbook, render_event_day_runbook
from riskon.pitch.errors import PitchContractError
from riskon.pitch.reporting import build_pitch_script, validate_pitch
from riskon.pitch.script_builder import render_one_page_summary


def test_backup_runbook_covers_controls_and_all_scenes(event_pitch_catalog: PitchCatalog) -> None:
    rendered = render_backup_demo_runbook(event_pitch_catalog)
    for control in event_pitch_catalog.backup.controls:
        assert control in rendered
    for scene in event_pitch_catalog.backup.scenes:
        assert scene.title in rendered
        assert scene.story_id in rendered
    assert "Do not troubleshoot on stage" in rendered


def test_event_day_runbook_captures_open_questions_and_checklist(
    event_pitch_catalog: PitchCatalog,
) -> None:
    rendered = render_event_day_runbook(event_pitch_catalog)
    assert rendered.count("?") == 3
    assert "uv run riskon inspect-corpus ..." in rendered
    assert "READY_WITH_WARNINGS" in rendered
    assert "[ ] Deck frozen" in rendered
    assert "Airplane mode or network off" in rendered


def test_one_page_summary_keeps_the_honest_boundary(event_pitch_catalog: PitchCatalog) -> None:
    rendered = render_one_page_summary(event_pitch_catalog)
    assert "ANSWER, CLARIFY, ABSTAIN or ROUTE" in rendered
    assert "does not claim a model-driven autonomous swarm" in rendered
    assert "Canonical profile: 300 seconds." in rendered


def test_validate_pitch_and_script_builder_expose_canonical_paths(
    event_pitch_build: object,
) -> None:
    result = event_pitch_build  # type: ignore[assignment]
    report = validate_pitch(config_path=Path("config/event_pitch.toml"))
    assert report.passed is True
    assert result.deck_path.name == "riskon_orchestra_pitch.pptx"  # type: ignore[attr-defined]
    path = build_pitch_script(Path("config/event_pitch.toml"), "3_MIN")
    assert path == result.output_root / "speaker_script_3min.md"  # type: ignore[attr-defined]
    assert "3_MIN" in path.read_text(encoding="utf-8")


def test_build_pitch_script_rejects_unknown_profile() -> None:
    with pytest.raises(PitchContractError, match="Unknown ER-C timing profile"):
        build_pitch_script(Path("config/event_pitch.toml"), "8_MIN")
