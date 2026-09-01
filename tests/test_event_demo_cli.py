"""ER-B CLI contract tests."""

from __future__ import annotations

from pathlib import Path

from riskon.cli import build_parser, main
from riskon.demo.reporting import build_demo

ROOT = Path(__file__).resolve().parents[1]


def test_demo_cli_parser_exposes_three_commands() -> None:
    assert (
        build_parser().parse_args(["demo-build", "--config", "config/event_demo.toml"]).command
        == "demo-build"
    )
    assert (
        build_parser()
        .parse_args(
            [
                "demo-query",
                "--config",
                "config/event_demo.toml",
                "--question",
                "What is the Synthetic Stability Marker?",
                "--output",
                "live.html",
            ]
        )
        .command
        == "demo-query"
    )


def test_demo_case_cli_writes_standalone_file(tmp_path: Path, capsys: object) -> None:
    output = tmp_path / "case.html"
    status = main(
        [
            "demo-case",
            "--config",
            str(ROOT / "config" / "event_demo.toml"),
            "--case",
            "ERB-003",
            "--output",
            str(output),
        ]
    )
    assert status == 0
    assert output.is_file()
    assert (
        "Demo case PASS: ERB-003; decision ANSWER; evidence valid; external assets 0."
        in capsys.readouterr().out
    )  # type: ignore[union-attr]


def test_demo_build_writes_the_canonical_bundle() -> None:
    result = build_demo(ROOT / "config" / "event_demo.toml")
    assert len(result.stories) == 5
    for path in (
        result.index_path,
        result.dashboard_path,
        result.bundle_path,
        result.metrics_path,
        result.audit_path,
    ):
        assert path.is_file()
    assert '"status": "PASS"' in result.audit_path.read_text(encoding="utf-8")
