"""Offline backup-replay tests for ER-C."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from riskon.pitch.backup_demo import load_demo_bundle, render_backup_html
from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.errors import PitchSourceError


def test_backup_html_contains_all_scenes_and_controls(
    event_pitch_catalog: PitchCatalog, event_pitch_config: object
) -> None:
    config = event_pitch_config  # type: ignore[assignment]
    bundle = load_demo_bundle(config.runtime.demo_bundle)  # type: ignore[attr-defined]
    html = render_backup_html(event_pitch_catalog, bundle)
    for scene in event_pitch_catalog.backup.scenes:
        assert scene.scene_id in html
        assert scene.title in html
    for control in event_pitch_catalog.backup.controls:
        assert control in html
    assert "fetch(" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert "document.addEventListener" in html


def test_backup_html_is_deterministic(
    event_pitch_catalog: PitchCatalog, event_pitch_config: object
) -> None:
    config = event_pitch_config  # type: ignore[assignment]
    bundle = load_demo_bundle(config.runtime.demo_bundle)  # type: ignore[attr-defined]
    assert render_backup_html(event_pitch_catalog, bundle) == render_backup_html(
        event_pitch_catalog, bundle
    )


def test_backup_rejects_missing_story(
    event_pitch_catalog: PitchCatalog, event_pitch_config: object
) -> None:
    config = event_pitch_config  # type: ignore[assignment]
    bundle = load_demo_bundle(config.runtime.demo_bundle)  # type: ignore[attr-defined]
    candidate = deepcopy(event_pitch_catalog)
    candidate.backup.scenes[0].story_id = "MISSING-STORY"
    with pytest.raises(PitchSourceError, match="missing story"):
        render_backup_html(candidate, bundle)


@pytest.mark.parametrize("payload", ["not-json", json.dumps({"bad": True})])
def test_demo_bundle_loader_rejects_invalid_payload(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "bundle.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(PitchSourceError, match="Invalid ER-B demo bundle"):
        load_demo_bundle(path)


def test_demo_bundle_loader_reports_missing_path(tmp_path: Path) -> None:
    with pytest.raises(PitchSourceError, match="not found"):
        load_demo_bundle(tmp_path / "missing.json")
