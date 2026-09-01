"""Orchestrate ER-C generation and expose the CLI-facing build results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from riskon.config import EventPitchConfig, load_event_pitch_config
from riskon.pitch.backup_demo import load_demo_bundle, render_backup_html
from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.deck_builder import build_pptx
from riskon.pitch.demo_runbook import render_backup_demo_runbook, render_event_day_runbook
from riskon.pitch.errors import PitchSourceError
from riskon.pitch.metrics_loader import load_metric_snapshot
from riskon.pitch.models import PitchManifest
from riskon.pitch.script_builder import (
    render_live_demo_script,
    render_one_page_summary,
    render_qa_bank,
    render_timing_script,
)
from riskon.pitch.validation import (
    PitchValidationReport,
    require_valid,
    validate_generated_package,
)

GENERATED_FILES = (
    "riskon_orchestra_pitch.pptx",
    "speaker_script_3min.md",
    "speaker_script_5min.md",
    "speaker_script_7min.md",
    "live_demo_script_90s.md",
    "backup_demo.html",
    "backup_demo_runbook.md",
    "qa_bank.md",
    "event_day_runbook.md",
    "one_page_summary.md",
    "pitch_manifest.json",
)


@dataclass(frozen=True)
class PitchBuildResult:
    """Paths and validation report produced by an ER-C build."""

    output_root: Path
    report: PitchValidationReport

    @property
    def deck_path(self) -> Path:
        """Return the generated PowerPoint path."""

        return self.output_root / "riskon_orchestra_pitch.pptx"

    @property
    def backup_path(self) -> Path:
        """Return the generated offline replay path."""

        return self.output_root / "backup_demo.html"

    @property
    def manifest_path(self) -> Path:
        """Return the generated machine-readable receipt path."""

        return self.output_root / "pitch_manifest.json"


def _load_inputs(config_path: Path) -> tuple[EventPitchConfig, PitchCatalog]:
    """Load configuration and all frozen contract inputs."""

    config = load_event_pitch_config(config_path)
    catalog = PitchCatalog.from_config(config)
    return config, catalog


def _write_text(path: Path, content: str) -> None:
    """Write UTF-8 text with a stable final newline."""

    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _write_json(path: Path, value: object) -> None:
    """Write deterministic JSON output."""

    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _manifest(report: PitchValidationReport, catalog: PitchCatalog) -> PitchManifest:
    """Convert a validation report into a stable build receipt."""

    return PitchManifest(
        schema_version="1.0",
        artifact="event_pitch",
        status="PASS",
        generated_files=list(GENERATED_FILES),
        slide_count=report.slide_count,
        main_slide_count=report.main_slide_count,
        appendix_slide_count=report.appendix_slide_count,
        timing_profile_count=report.timing_profile_count,
        canonical_profile="5_MIN",
        canonical_duration_seconds=report.canonical_duration_seconds,
        live_demo_seconds=report.live_demo_seconds,
        qa_topic_count=report.qa_topic_count,
        backup_scene_count=report.backup_scene_count,
        metric_source_count=report.metric_source_count,
        metric_source_expected=report.metric_source_expected,
        hard_coded_evaluator_metric_count=report.hard_coded_evaluator_metric_count,
        external_asset_count=report.external_asset_count,
        external_link_count=report.external_link_count,
        absolute_path_leak_count=report.absolute_path_leak_count,
        real_name_or_contact_leak_count=report.real_name_or_contact_leak_count,
        confidential_source_text_leak_count=report.confidential_source_text_leak_count,
        network_violation_count=report.network_violation_count,
        network_enabled=catalog.config.security.network_enabled,
    )


def build_pitch(config_path: Path) -> PitchBuildResult:
    """Build the complete ER-C pitch package from frozen local sources."""

    config, catalog = _load_inputs(config_path)
    snapshot = load_metric_snapshot(config.runtime.dashboard_metrics)
    bundle = load_demo_bundle(config.runtime.demo_bundle)
    if bundle.security.get("network_enabled") is not False:
        raise PitchSourceError("ER-B source bundle must report network disabled")
    output_root = config.runtime.generated_root
    output_root.mkdir(parents=True, exist_ok=True)
    build_pptx(catalog, snapshot, output_root / "riskon_orchestra_pitch.pptx")
    _write_text(output_root / "speaker_script_3min.md", render_timing_script(catalog, "3_MIN"))
    _write_text(output_root / "speaker_script_5min.md", render_timing_script(catalog, "5_MIN"))
    _write_text(output_root / "speaker_script_7min.md", render_timing_script(catalog, "7_MIN"))
    _write_text(output_root / "live_demo_script_90s.md", render_live_demo_script(catalog))
    _write_text(output_root / "backup_demo_runbook.md", render_backup_demo_runbook(catalog))
    _write_text(output_root / "qa_bank.md", render_qa_bank(catalog))
    _write_text(output_root / "event_day_runbook.md", render_event_day_runbook(catalog))
    _write_text(output_root / "one_page_summary.md", render_one_page_summary(catalog))
    (output_root / "backup_demo.html").write_text(
        render_backup_html(catalog, bundle), encoding="utf-8"
    )
    # Reserve the receipt path before the first validation pass; it is replaced
    # with the complete machine-readable receipt immediately afterwards.
    _write_json(
        output_root / "pitch_manifest.json", {"schema_version": "1.0", "status": "BUILDING"}
    )
    report = require_valid(validate_generated_package(catalog, snapshot, output_root))
    _write_json(
        output_root / "pitch_manifest.json", _manifest(report, catalog).model_dump(mode="json")
    )
    final_report = require_valid(validate_generated_package(catalog, snapshot, output_root))
    return PitchBuildResult(output_root=output_root, report=final_report)


def validate_pitch(config_path: Path) -> PitchValidationReport:
    """Validate an already-generated ER-C package."""

    config, catalog = _load_inputs(config_path)
    snapshot = load_metric_snapshot(config.runtime.dashboard_metrics)
    return validate_generated_package(catalog, snapshot, config.runtime.generated_root)


def build_pitch_script(config_path: Path, profile_id: str) -> Path:
    """Render one timing script into the canonical generated directory."""

    config, catalog = _load_inputs(config_path)
    profile = catalog.profile(profile_id)
    path = (
        config.runtime.generated_root
        / f"speaker_script_{profile.profile_id.lower().replace('_', '')}.md"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text(path, render_timing_script(catalog, profile.profile_id))
    return path
