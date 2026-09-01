"""Determinism checks for repeatable event-day outputs."""

from __future__ import annotations

import json

from riskon.pitch.reporting import GENERATED_FILES
from riskon.pitch.script_builder import (
    render_live_demo_script,
    render_one_page_summary,
    render_qa_bank,
    render_timing_script,
)


def test_generated_file_manifest_is_stable(event_pitch_build: object) -> None:
    result = event_pitch_build  # type: ignore[assignment]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    assert manifest["generated_files"] == list(GENERATED_FILES)
    assert manifest["status"] == "PASS"


def test_text_renderers_are_repeatable(event_pitch_catalog: object) -> None:
    catalog = event_pitch_catalog  # type: ignore[assignment]
    renderers = [
        lambda: render_timing_script(catalog, "5_MIN"),
        lambda: render_live_demo_script(catalog),
        lambda: render_qa_bank(catalog),
        lambda: render_one_page_summary(catalog),
    ]
    for renderer in renderers:
        assert renderer() == renderer()


def test_manifest_contains_no_unstable_runtime_metadata(event_pitch_build: object) -> None:
    path = event_pitch_build.manifest_path  # type: ignore[attr-defined]
    text = path.read_text(encoding="utf-8")
    assert "timestamp" not in text.casefold()
    assert "uuid" not in text.casefold()
