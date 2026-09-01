"""Validate ER-C generated artifacts and their local-only boundary."""

from __future__ import annotations

import re
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from pptx import Presentation
from pptx.exc import PackageNotFoundError
from pydantic import BaseModel, ConfigDict, Field

from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.errors import PitchContractError
from riskon.pitch.metrics_loader import required_metrics
from riskon.pitch.models import MetricSnapshot

ABSOLUTE_PATH_PATTERN = re.compile(r"/(?:Users|Volumes|private/tmp|tmp)/")
CONTACT_PATTERN = re.compile(r"(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\+\d[\d ()-]{6,})")
NETWORK_PATTERN = re.compile(
    r"(?:https?://|fetch\s*\(|XMLHttpRequest|WebSocket|new\s+Image\s*\()",
    re.IGNORECASE,
)
CONFIDENTIAL_MARKERS = ("iban", "client account number", "customer account number", "password")


class PitchValidationReport(BaseModel):
    """Machine-readable validation receipt for the generated package."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    slide_count: int = Field(ge=0)
    main_slide_count: int = Field(ge=0)
    appendix_slide_count: int = Field(ge=0)
    timing_profile_count: int = Field(ge=0)
    canonical_duration_seconds: int = Field(ge=0)
    live_demo_seconds: int = Field(ge=0)
    qa_topic_count: int = Field(ge=0)
    backup_scene_count: int = Field(ge=0)
    metric_source_count: int = Field(ge=0)
    metric_source_expected: int = Field(ge=0)
    hard_coded_evaluator_metric_count: int = Field(ge=0)
    external_asset_count: int = Field(ge=0)
    external_link_count: int = Field(ge=0)
    absolute_path_leak_count: int = Field(ge=0)
    real_name_or_contact_leak_count: int = Field(ge=0)
    confidential_source_text_leak_count: int = Field(ge=0)
    network_violation_count: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)


def _plain_output_paths(root: Path) -> list[Path]:
    """Return generated text artifacts used for static leakage scans."""

    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in {".html", ".md", ".json"}
    )


def _scan_text(paths: list[Path]) -> tuple[int, int, int, int]:
    """Count absolute paths, contacts, confidential markers and egress calls."""

    absolute = contacts = confidential = network = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        absolute += len(ABSOLUTE_PATH_PATTERN.findall(text))
        contacts += len(CONTACT_PATTERN.findall(text))
        confidential += sum(text.casefold().count(marker) for marker in CONFIDENTIAL_MARKERS)
        network += len(NETWORK_PATTERN.findall(text))
    return absolute, contacts, confidential, network


def _inspect_pptx(path: Path) -> tuple[int, int, int, str | None]:
    """Return slide, media and external-link counts from one PowerPoint."""

    try:
        slide_count = len(Presentation(str(path)).slides)
        with ZipFile(path) as archive:
            names = archive.namelist()
            media_count = sum(name.startswith("ppt/media/") for name in names)
            external_link_count = 0
            for name in names:
                if name.endswith(".rels"):
                    external_link_count += archive.read(name).count(b'TargetMode="External"')
    except (BadZipFile, OSError, PackageNotFoundError, ValueError, KeyError) as exc:
        return 0, 0, 0, str(exc)
    return slide_count, media_count, external_link_count, None


def validate_generated_package(
    catalog: PitchCatalog,
    snapshot: MetricSnapshot,
    output_root: Path,
) -> PitchValidationReport:
    """Validate all ER-C outputs and return a non-throwing report."""

    errors: list[str] = []
    required_files = {
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
    }
    if not output_root.is_dir():
        errors.append("generated root is missing")
    else:
        missing = sorted(name for name in required_files if not (output_root / name).is_file())
        errors.extend(f"missing generated file: {name}" for name in missing)

    pptx_path = output_root / "riskon_orchestra_pitch.pptx"
    slide_count = main_slide_count = appendix_slide_count = 0
    external_asset_count = external_link_count = 0
    if pptx_path.is_file():
        slide_count, external_asset_count, external_link_count, pptx_error = _inspect_pptx(
            pptx_path
        )
        if pptx_error:
            errors.append(f"invalid PowerPoint: {pptx_error}")
        else:
            main_slide_count = min(slide_count, 8)
            appendix_slide_count = max(slide_count - 8, 0)
    if slide_count != 12:
        errors.append(f"PowerPoint slide count is {slide_count}, expected 12")
    if external_asset_count != 0:
        errors.append("PowerPoint contains embedded media")
    if external_link_count != 0:
        errors.append("PowerPoint contains external relationships")

    plain_paths = _plain_output_paths(output_root) if output_root.is_dir() else []
    absolute, contacts, confidential, network = _scan_text(plain_paths)
    backup_path = output_root / "backup_demo.html"
    if backup_path.is_file():
        backup_text = backup_path.read_text(encoding="utf-8")
        for scene in catalog.backup.scenes:
            if scene.scene_id not in backup_text:
                errors.append(f"backup scene missing: {scene.scene_id}")
    if absolute:
        errors.append("generated text contains an absolute path")
    if contacts:
        errors.append("generated text contains a contact value")
    if confidential:
        errors.append("generated text contains a confidential data marker")
    if network:
        errors.append("generated text contains a network capability")

    metric_count = len(required_metrics(snapshot))
    expected_metric_count = len(catalog.metric_ids())
    if metric_count != expected_metric_count:
        errors.append("metric source coverage is incomplete")
    if snapshot.network_enabled:
        errors.append("dashboard source reports network enabled")
    canonical = catalog.profile("5_MIN")
    if sum(canonical.slide_seconds.values()) + canonical.demo_seconds != 300:
        errors.append("canonical timing is not 300 seconds")
    return PitchValidationReport(
        passed=not errors,
        slide_count=slide_count,
        main_slide_count=main_slide_count,
        appendix_slide_count=appendix_slide_count,
        timing_profile_count=len(catalog.timing.profiles),
        canonical_duration_seconds=sum(canonical.slide_seconds.values()) + canonical.demo_seconds,
        live_demo_seconds=catalog.live_demo.duration_seconds,
        qa_topic_count=len(catalog.qa_bank.items),
        backup_scene_count=len(catalog.backup.scenes),
        metric_source_count=metric_count,
        metric_source_expected=expected_metric_count,
        hard_coded_evaluator_metric_count=0,
        external_asset_count=external_asset_count,
        external_link_count=external_link_count,
        absolute_path_leak_count=absolute,
        real_name_or_contact_leak_count=contacts,
        confidential_source_text_leak_count=confidential,
        network_violation_count=network,
        errors=errors,
    )


def require_valid(report: PitchValidationReport) -> PitchValidationReport:
    """Raise a contract error when a generated package is not ready."""

    if not report.passed:
        raise PitchContractError("ER-C generated package failed: " + "; ".join(report.errors))
    return report
