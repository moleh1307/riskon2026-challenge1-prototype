"""ER-A compatibility smoke tests over M1/M2 components."""

from pathlib import Path

import pytest
from event_intake_helpers import EVENT_ROOT, adapter, request_for

from riskon.event_intake.compatibility import CompatibilityRunner
from riskon.event_intake.errors import CorpusBlockedError
from riskon.event_intake.manifest import load_smoke_cases


def test_valid_pack_compatibility_is_three_of_three(tmp_path: Path) -> None:
    event_adapter = adapter()
    request = request_for("valid_pack", tmp_path / "out")
    prepared = event_adapter.prepare(request)
    cases = load_smoke_cases(EVENT_ROOT / "valid_pack" / "smoke_cases.json")

    report = event_adapter.smoke_test(prepared, cases)

    assert report.passed
    assert report.expected_case_count == 3
    assert report.matched_case_count == 3
    assert report.external_fetches == 0
    assert report.source_instruction_executions == 0


def test_each_smoke_case_keeps_its_expected_decision(tmp_path: Path) -> None:
    event_adapter = adapter()
    request = request_for("valid_pack", tmp_path / "out")
    prepared = event_adapter.prepare(request)
    cases = load_smoke_cases(EVENT_ROOT / "valid_pack" / "smoke_cases.json")

    report = event_adapter.smoke_test(prepared, cases)

    assert [(item.id, item.actual_decision.value) for item in report.case_results] == [
        ("ER-001", "ANSWER"),
        ("ER-002", "CLARIFY"),
        ("ER-003", "ANSWER"),
    ]


def test_blocked_corpus_cannot_enter_smoke_runner(tmp_path: Path) -> None:
    event_adapter = adapter()
    prepared = event_adapter.prepare(request_for("invalid_pack", tmp_path / "out"))
    cases = load_smoke_cases(EVENT_ROOT / "valid_pack" / "smoke_cases.json")

    with pytest.raises(CorpusBlockedError):
        event_adapter.smoke_test(prepared, cases)


def test_empty_smoke_suite_fails_closed(tmp_path: Path) -> None:
    event_adapter = adapter()
    prepared = event_adapter.prepare(request_for("valid_pack", tmp_path / "out"))

    assert prepared is not None
    report = CompatibilityRunner(
        Path(__file__).resolve().parents[1],
        Path(__file__).resolve().parents[1] / "config" / "milestone2.toml",
    ).run(prepared, ())

    assert not report.passed
    assert "NO_SMOKE_CASES" in report.failure_codes


def test_wrong_expectation_is_reported_without_source_leak(tmp_path: Path) -> None:
    event_adapter = adapter()
    request = request_for("valid_pack", tmp_path / "out")
    prepared = event_adapter.prepare(request)
    cases = load_smoke_cases(EVENT_ROOT / "valid_pack" / "smoke_cases.json")
    wrong = cases[0].model_copy(update={"expected_decision": "CLARIFY"})

    report = event_adapter.smoke_test(prepared, (wrong,))

    assert not report.passed
    assert report.case_results[0].failures == ["DECISION_MISMATCH"]
    assert "missing record" not in str(report.model_dump()).casefold()
