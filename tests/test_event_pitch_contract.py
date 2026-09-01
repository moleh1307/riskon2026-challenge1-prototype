"""ER-C contract-freeze tests: configuration and immutable package shape."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PITCH_ROOT = ROOT / "data" / "synthetic" / "event_pitch"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_event_pitch_config_is_closed_and_local() -> None:
    raw = tomllib.loads((ROOT / "config" / "event_pitch.toml").read_text(encoding="utf-8"))
    assert set(raw) == {"runtime", "deck", "timing", "security"}
    assert raw["runtime"] == {
        "pipeline_config": "config/milestone5b.toml",
        "demo_config": "config/event_demo.toml",
        "pitch_contract": "data/synthetic/event_pitch/pitch_contract.json",
        "slide_content": "data/synthetic/event_pitch/slide_content.json",
        "timing_profiles": "data/synthetic/event_pitch/timing_profiles.json",
        "live_demo_script": "data/synthetic/event_pitch/live_demo_script.json",
        "qa_bank": "data/synthetic/event_pitch/qa_bank.json",
        "backup_demo_contract": "data/synthetic/event_pitch/backup_demo_contract.json",
        "presentation_copy": "data/synthetic/event_pitch/presentation_copy.json",
        "speaker_assignments": "data/synthetic/event_pitch/speaker_assignments.json",
        "demo_bundle": "data/generated/event_demo/demo_bundle.json",
        "dashboard_metrics": "data/generated/event_demo/dashboard_metrics.json",
        "generated_root": "data/generated/event_pitch",
    }
    assert raw["deck"] == {
        "aspect_ratio": "16:9",
        "main_slide_count": 8,
        "appendix_slide_count": 4,
        "total_slide_count": 12,
        "external_assets_enabled": False,
        "external_links_enabled": False,
        "include_real_names": False,
        "include_confidential_source_text": False,
    }
    assert raw["timing"] == {
        "default_profile": "5_MIN",
        "profiles": ["3_MIN", "5_MIN", "7_MIN"],
        "live_demo_seconds": 90,
    }
    assert raw["security"] == {
        "network_enabled": False,
        "external_api_enabled": False,
        "telemetry_enabled": False,
        "server_enabled": False,
    }


def test_pitch_contract_has_exact_twelve_slide_skeleton() -> None:
    contract = _json(PITCH_ROOT / "pitch_contract.json")
    assert contract["schema_version"] == "1.0"
    assert contract["milestone"] == "ER-C_FINAL_PITCH_PACKAGE"
    assert contract["deck"] == {
        "format": "pptx",
        "aspect_ratio": "16:9",
        "slide_width_px": 1280,
        "slide_height_px": 720,
        "main_slide_count": 8,
        "appendix_slide_count": 4,
        "total_slide_count": 12,
        "animations_required": False,
        "external_hyperlinks": False,
        "external_media": False,
    }
    slides = contract["slides"]
    assert len(slides) == 12
    assert [item["slide_id"] for item in slides] == [f"S{index:02d}" for index in range(1, 13)]
    assert [item["slide_number"] for item in slides] == list(range(1, 13))
    assert sum(item["section"] == "main" for item in slides) == 8
    assert sum(item["section"] == "appendix" for item in slides) == 4
    assert all(item["required"] for item in slides)
    assert contract["required_slide_fields"] == [
        "slide_id",
        "title",
        "purpose",
        "source_label",
        "speaker_key_message",
        "timing_profile_visibility",
    ]


def test_pitch_contract_is_no_egress_and_uses_allowed_fonts() -> None:
    contract = _json(PITCH_ROOT / "pitch_contract.json")
    assert contract["fonts"] == ["Arial", "Aptos", "Calibri"]
    assert set(contract["palette"]) == {
        "navy",
        "white",
        "warm_sand",
        "green",
        "amber",
        "red",
        "ink",
        "muted",
        "line",
    }
    assert contract["security"] == {
        "network_enabled": False,
        "external_api_enabled": False,
        "telemetry_enabled": False,
        "server_enabled": False,
        "real_names_allowed": False,
        "absolute_paths_allowed": False,
        "confidential_source_text_allowed": False,
    }
