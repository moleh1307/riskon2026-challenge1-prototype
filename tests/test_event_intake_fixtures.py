"""ER-A synthetic pack behavior tests."""

from pathlib import Path

from event_intake_helpers import adapter, request_for

from riskon.event_intake.models import CorpusStatus


def test_warning_pack_has_exact_nonblocking_signals(tmp_path: Path) -> None:
    report = adapter().inspect(request_for("warning_pack", tmp_path / "out"))

    assert report.status is CorpusStatus.READY_WITH_WARNINGS
    assert report.external_links == 1
    assert report.source_instruction_signal_count == 1
    assert report.missing_local_assets == ["knowledge/assets/missing-noncritical.png"]
    assert report.orphan_html_files == ["knowledge/orphan.html"]


def test_warning_pack_has_zero_external_fetches(tmp_path: Path) -> None:
    report = adapter().inspect(request_for("warning_pack", tmp_path / "out"))

    assert report.external_fetches == 0
    assert all(issue.code != "EXTERNAL_FETCH" for issue in report.issues)


def test_invalid_pack_is_blocked_and_has_no_prepared_corpus(tmp_path: Path) -> None:
    request = request_for("invalid_pack", tmp_path / "out")
    event_adapter = adapter()

    report = event_adapter.inspect(request)
    prepared = event_adapter.prepare(request)

    assert report.status is CorpusStatus.BLOCKED
    assert {issue.code for issue in report.blocking_issues} >= {
        "DUPLICATE_FILENAME",
        "MANIFEST_HTML_MISSING",
        "SYMLINK_ESCAPE",
    }
    assert prepared is None


def test_valid_pack_counts_every_required_document(tmp_path: Path) -> None:
    report = adapter().inspect(request_for("valid_pack", tmp_path / "out"))

    assert report.status is CorpusStatus.READY
    assert [item.relative_path for item in report.documents] == [
        "knowledge/direct_rule.html",
        "knowledge/contextual_workflow.html",
        "knowledge/alert_table.html",
    ]
    assert {item.title for item in report.documents} == {
        "Direct Rule",
        "Contextual Workflow",
        "Session Alerts",
    }


def test_valid_pack_fingerprint_is_stable(tmp_path: Path) -> None:
    event_adapter = adapter()
    first = event_adapter.inspect(request_for("valid_pack", tmp_path / "out-1"))
    second = event_adapter.inspect(request_for("valid_pack", tmp_path / "out-2"))

    assert first.corpus_fingerprint == second.corpus_fingerprint
