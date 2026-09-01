"""ER-B live synthetic query tests."""

from __future__ import annotations

from pathlib import Path

from riskon.demo.live_query import load_context_file, run_live_query

ROOT = Path(__file__).resolve().parents[1]


def test_live_query_uses_the_local_orchestrated_runtime(tmp_path: Path) -> None:
    output = tmp_path / "live.html"
    story = run_live_query(
        ROOT / "config" / "event_demo.toml",
        "What is the Synthetic Stability Marker?",
        output=output,
    )
    assert story.decision == "ANSWER"
    assert output.is_file()
    assert "Synthetic Stability Marker" in output.read_text(encoding="utf-8")


def test_live_query_context_preset_is_loaded_from_local_json() -> None:
    context = load_context_file(
        ROOT / "data" / "synthetic" / "event_demo" / "context_presets.json",
        "REGION_BETA_SERVICE_BASIC",
    )
    assert context == {"region": "REGION_BETA", "service_model": "SERVICE_BASIC"}
