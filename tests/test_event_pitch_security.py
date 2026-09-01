"""Security-boundary tests for ER-C generated artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest

from riskon.pitch.errors import PitchContractError
from riskon.pitch.validation import (
    PitchValidationReport,
    _scan_text,
    require_valid,
)


def test_pitch_config_and_manifest_keep_every_egress_switch_off(
    event_pitch_config: object, event_pitch_build: object
) -> None:
    config = event_pitch_config  # type: ignore[assignment]
    report = event_pitch_build.report  # type: ignore[attr-defined]
    assert config.security.model_dump() == {
        "network_enabled": False,
        "external_api_enabled": False,
        "telemetry_enabled": False,
        "server_enabled": False,
    }
    assert report.external_asset_count == 0
    assert report.external_link_count == 0
    assert report.network_violation_count == 0


def test_text_scanner_counts_all_forbidden_categories(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.md"
    path.write_text(
        "/Users/private/file\nowner@example.com\npassword\nfetch(\nhttps://example.com\n",
        encoding="utf-8",
    )
    assert _scan_text([path]) == (1, 1, 1, 2)


def test_text_scanner_is_clean_for_local_copy(tmp_path: Path) -> None:
    path = tmp_path / "safe.md"
    path.write_text("Synthetic local demonstration; no external requests.\n", encoding="utf-8")
    assert _scan_text([path]) == (0, 0, 0, 0)


def test_require_valid_passes_and_rejects_reports() -> None:
    valid = PitchValidationReport(
        passed=True,
        slide_count=12,
        main_slide_count=8,
        appendix_slide_count=4,
        timing_profile_count=3,
        canonical_duration_seconds=300,
        live_demo_seconds=90,
        qa_topic_count=18,
        backup_scene_count=6,
        metric_source_count=7,
        metric_source_expected=7,
        hard_coded_evaluator_metric_count=0,
        external_asset_count=0,
        external_link_count=0,
        absolute_path_leak_count=0,
        real_name_or_contact_leak_count=0,
        confidential_source_text_leak_count=0,
        network_violation_count=0,
    )
    assert require_valid(valid) is valid
    invalid = valid.model_copy(update={"passed": False, "errors": ["bad artifact"]})
    with pytest.raises(PitchContractError, match="bad artifact"):
        require_valid(invalid)
