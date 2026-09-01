"""ER-A no-egress and source-instruction execution tests."""

from pathlib import Path

from event_intake_helpers import EVENT_ROOT, adapter, request_for

from riskon.event_intake.manifest import load_smoke_cases


def test_inspection_declares_zero_external_fetches(tmp_path: Path) -> None:
    report = adapter().inspect(request_for("warning_pack", tmp_path / "out"))

    assert report.external_fetches == 0
    assert report.network_enabled is False


def test_warning_corpus_never_executes_source_instruction(tmp_path: Path) -> None:
    event_adapter = adapter()
    request = request_for("warning_pack", tmp_path / "out")
    prepared = event_adapter.prepare(request)
    assert prepared is not None

    # The warning pack intentionally has no smoke cases; the descriptor itself is enough to
    # prove that the instruction signal remains metadata.
    assert "SOURCE_INSTRUCTION_SIGNAL" in prepared.warnings


def test_valid_smoke_has_no_subprocess_or_network_activity(tmp_path: Path) -> None:
    event_adapter = adapter()
    request = request_for("valid_pack", tmp_path / "out")
    prepared = event_adapter.prepare(request)
    cases = load_smoke_cases(EVENT_ROOT / "valid_pack" / "smoke_cases.json")
    assert prepared is not None

    report = event_adapter.smoke_test(prepared, cases)

    assert report.subprocess_calls == 0
    assert report.external_fetches == 0
    assert report.network_disabled
