"""Configuration-boundary tests for the ER-C package."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from riskon.config import EventPitchConfig, load_event_pitch_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mutable_pitch_config(tmp_path: Path) -> Path:
    """Create a temporary config file whose resolved project root is the repo."""

    directory = ROOT / f".event-pitch-config-test-{tmp_path.name}"
    directory.mkdir(exist_ok=True)
    path = directory / "event_pitch.toml"
    path.write_text(
        (ROOT / "config" / "event_pitch.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    yield path
    shutil.rmtree(directory, ignore_errors=True)


def test_event_pitch_loader_returns_closed_local_config(
    event_pitch_config: EventPitchConfig,
) -> None:
    assert event_pitch_config.project_root == ROOT
    assert event_pitch_config.deck.total_slide_count == 12
    assert event_pitch_config.timing.default_profile == "5_MIN"
    assert event_pitch_config.security.network_enabled is False
    assert all(
        path.is_absolute() for path in event_pitch_config.runtime.model_dump(mode="python").values()
    )


@pytest.mark.parametrize(
    ("replacement", "expected"),
    [
        ("\n[extra]\nvalue = false\n", "fields mismatch for root"),
        ('[runtime]\nextra = "unexpected"\n', "fields mismatch for runtime"),
        (
            'pitch_contract = "data/synthetic/event_pitch/pitch_contract.json"',
            'pitch_contract = "/tmp/pitch.json"',
        ),
        (
            'pitch_contract = "data/synthetic/event_pitch/pitch_contract.json"',
            'pitch_contract = "../pitch.json"',
        ),
        ('aspect_ratio = "16:9"', 'aspect_ratio = "4:3"'),
        ("main_slide_count = 8", "main_slide_count = 7"),
        ('default_profile = "5_MIN"', 'default_profile = "3_MIN"'),
        ("live_demo_seconds = 90", "live_demo_seconds = 89"),
        ("network_enabled = false", "network_enabled = true"),
    ],
)
def test_event_pitch_loader_rejects_contract_mutations(
    mutable_pitch_config: Path,
    replacement: str,
    expected: str,
) -> None:
    text = mutable_pitch_config.read_text(encoding="utf-8")
    if replacement.startswith("\n[extra]"):
        text += replacement
    elif replacement.startswith("[runtime]"):
        text = text.replace("[runtime]\n", replacement, 1)
    else:
        old, new = replacement, expected
        assert old in text
        text = text.replace(old, new, 1)
    mutable_pitch_config.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_event_pitch_config(mutable_pitch_config)


def test_event_pitch_loader_rejects_missing_input(mutable_pitch_config: Path) -> None:
    text = mutable_pitch_config.read_text(encoding="utf-8")
    text = text.replace(
        'pipeline_config = "config/milestone5b.toml"',
        'pipeline_config = "config/missing-for-test.toml"',
        1,
    )
    mutable_pitch_config.write_text(text, encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Event pitch contract input not found"):
        load_event_pitch_config(mutable_pitch_config)


def test_event_pitch_loader_rejects_missing_config() -> None:
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_event_pitch_config(ROOT / "config" / "missing-event-pitch.toml")
