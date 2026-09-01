"""CLI contract tests for ER-C commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from riskon.cli import build_parser, main


def test_pitch_parser_requires_the_expected_profile_choices() -> None:
    args = build_parser().parse_args(
        ["pitch-script", "--config", "config/event_pitch.toml", "--profile", "5_MIN"]
    )
    assert args.command == "pitch-script"
    assert args.profile == "5_MIN"
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["pitch-script", "--config", "config/event_pitch.toml", "--profile", "2_MIN"]
        )


def test_pitch_validate_cli_reports_pass(
    event_pitch_build: object, capsys: pytest.CaptureFixture[str]
) -> None:
    del event_pitch_build
    assert main(["pitch-validate", "--config", "config/event_pitch.toml"]) == 0
    assert "Event pitch VALID" in capsys.readouterr().out


def test_pitch_script_cli_writes_requested_profile(
    event_pitch_build: object, capsys: pytest.CaptureFixture[str]
) -> None:
    del event_pitch_build
    assert main(["pitch-script", "--config", "config/event_pitch.toml", "--profile", "7_MIN"]) == 0
    output = capsys.readouterr().out
    assert "profile 7_MIN" in output
    assert Path("data/generated/event_pitch/speaker_script_7min.md").is_file()


def test_pitch_build_cli_reports_pass(
    allow_session_asyncio_unix_socket: None, capsys: pytest.CaptureFixture[str]
) -> None:
    del allow_session_asyncio_unix_socket
    assert main(["pitch-build", "--config", "config/event_pitch.toml"]) == 0
    assert "Event pitch PASS: slides 12/12" in capsys.readouterr().out
