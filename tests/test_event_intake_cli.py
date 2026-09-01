"""ER-A command-line contract tests."""

import json
from pathlib import Path

from event_intake_helpers import EVENT_ROOT

from riskon.cli import main


def _pack_args(pack: str, output: Path) -> list[str]:
    root = EVENT_ROOT / pack
    return [
        "--root",
        str(root),
        "--manifest",
        str(root / "manifest.xlsx"),
        "--output",
        str(output),
    ]


def test_inspect_cli_emits_ready_contract_and_reports(tmp_path: Path, capsys) -> None:
    output = tmp_path / "valid"

    exit_code = main(["inspect-corpus", *_pack_args("valid_pack", output)])

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "Corpus intake READY: 3 manifest rows; 3 HTML files matched; "
        "0 blocking issues; external fetches 0.\n"
    )
    assert (output / "inspection.json").is_file()
    assert (output / "prepared_corpus.json").is_file()


def test_smoke_cli_emits_three_of_three_contract(tmp_path: Path, capsys) -> None:
    output = tmp_path / "valid"
    root = EVENT_ROOT / "valid_pack"

    exit_code = main(
        [
            "smoke-corpus",
            *_pack_args("valid_pack", output),
            "--cases",
            str(root / "smoke_cases.json"),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == (
        "Corpus compatibility PASS: 3/3 smoke cases; source mutations 0; "
        "external fetches 0; network disabled.\n"
    )
    compatibility = json.loads((output / "compatibility.json").read_text(encoding="utf-8"))
    assert compatibility["matched_case_count"] == 3


def test_warning_and_invalid_cli_statuses_are_fail_closed(tmp_path: Path, capsys) -> None:
    warning_output = tmp_path / "warning"
    invalid_output = tmp_path / "invalid"

    warning_code = main(["inspect-corpus", *_pack_args("warning_pack", warning_output)])
    warning_stdout = capsys.readouterr().out
    invalid_code = main(["inspect-corpus", *_pack_args("invalid_pack", invalid_output)])
    invalid_stdout = capsys.readouterr().out

    assert warning_code == 0
    assert warning_stdout == (
        "Corpus intake READY_WITH_WARNINGS: 4 warnings; 0 blocking issues; external fetches 0.\n"
    )
    assert invalid_code == 1
    assert invalid_stdout == (
        "Corpus intake BLOCKED: 3 blocking issues; no prepared corpus created.\n"
    )
    assert (invalid_output / "inspection.json").is_file()
    assert not (invalid_output / "prepared_corpus.json").exists()


def test_blocked_smoke_cli_does_not_write_prepared_or_compatibility(tmp_path: Path, capsys) -> None:
    output = tmp_path / "invalid"
    root = EVENT_ROOT / "valid_pack"

    exit_code = main(
        [
            "smoke-corpus",
            *_pack_args("invalid_pack", output),
            "--cases",
            str(root / "smoke_cases.json"),
        ]
    )

    assert exit_code == 1
    assert capsys.readouterr().out == (
        "Corpus intake BLOCKED: 3 blocking issues; no prepared corpus created.\n"
    )
    assert (output / "inspection.json").is_file()
    assert not (output / "prepared_corpus.json").exists()
    assert not (output / "compatibility.json").exists()


def test_output_inside_source_is_blocked_without_creating_output(capsys) -> None:
    source = EVENT_ROOT / "valid_pack"
    output = source / "generated-by-cli-test"

    exit_code = main(
        [
            "inspect-corpus",
            "--root",
            str(source),
            "--manifest",
            str(source / "manifest.xlsx"),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert capsys.readouterr().out == (
        "Corpus intake BLOCKED: 1 blocking issues; no prepared corpus created.\n"
    )
    assert not output.exists()


def test_invalid_column_mapping_is_rejected_before_inspection(capsys) -> None:
    source = EVENT_ROOT / "valid_pack"

    exit_code = main(
        [
            "inspect-corpus",
            "--root",
            str(source),
            "--manifest",
            str(source / "manifest.xlsx"),
            "--output",
            "/tmp/riskon-event-cli-invalid-mapping",
            "--column-mapping",
            "not-json",
        ]
    )

    assert exit_code == 2
    assert capsys.readouterr().err == "Corpus intake BLOCKED: --column-mapping must be valid JSON\n"
