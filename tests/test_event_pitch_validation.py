"""Generated-package validation tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.metrics_loader import load_metric_snapshot
from riskon.pitch.validation import validate_generated_package


def test_validation_accepts_the_complete_generated_package(
    event_pitch_build: object, event_pitch_config: object, event_pitch_catalog: PitchCatalog
) -> None:
    result = event_pitch_build  # type: ignore[assignment]
    config = event_pitch_config  # type: ignore[assignment]
    snapshot = load_metric_snapshot(config.runtime.dashboard_metrics)  # type: ignore[attr-defined]
    report = validate_generated_package(event_pitch_catalog, snapshot, result.output_root)  # type: ignore[attr-defined]
    assert report.passed is True
    assert report.errors == []


def test_validation_reports_missing_generated_root(
    event_pitch_config: object, event_pitch_catalog: PitchCatalog, tmp_path: Path
) -> None:
    config = event_pitch_config  # type: ignore[assignment]
    snapshot = load_metric_snapshot(config.runtime.dashboard_metrics)  # type: ignore[attr-defined]
    report = validate_generated_package(event_pitch_catalog, snapshot, tmp_path / "missing")
    assert report.passed is False
    assert "generated root is missing" in report.errors
    assert report.slide_count == 0


def test_validation_reports_invalid_pptx_and_leaky_text(
    event_pitch_config: object, event_pitch_catalog: PitchCatalog, tmp_path: Path
) -> None:
    config = event_pitch_config  # type: ignore[assignment]
    snapshot = load_metric_snapshot(config.runtime.dashboard_metrics)  # type: ignore[attr-defined]
    root = tmp_path / "generated"
    root.mkdir()
    (root / "riskon_orchestra_pitch.pptx").write_text("not a powerpoint", encoding="utf-8")
    (root / "unsafe.md").write_text("/Users/name password https://example.com", encoding="utf-8")
    report = validate_generated_package(event_pitch_catalog, snapshot, root)
    assert report.passed is False
    assert any("invalid PowerPoint" in error for error in report.errors)
    assert report.absolute_path_leak_count == 1
    assert report.confidential_source_text_leak_count == 1
    assert report.network_violation_count == 1


def test_validation_reports_missing_backup_scene(
    event_pitch_build: object,
    event_pitch_config: object,
    event_pitch_catalog: PitchCatalog,
    tmp_path: Path,
) -> None:
    source = event_pitch_build.output_root  # type: ignore[attr-defined]
    root = tmp_path / "generated"
    shutil.copytree(source, root)
    backup = root / "backup_demo.html"
    text = backup.read_text(encoding="utf-8").replace("SCENE-6", "REMOVED-SCENE", 1)
    backup.write_text(text, encoding="utf-8")
    config = event_pitch_config  # type: ignore[assignment]
    snapshot = load_metric_snapshot(config.runtime.dashboard_metrics)  # type: ignore[attr-defined]
    report = validate_generated_package(event_pitch_catalog, snapshot, root)
    assert report.passed is False
    assert "backup scene missing: SCENE-6" in report.errors
