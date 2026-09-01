"""Frozen ER-A public contract tests."""

from pathlib import Path

from riskon.event_intake import EventCorpusAdapter
from riskon.event_intake.models import CorpusIntakeRequest, CorpusStatus

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENT_ROOT = PROJECT_ROOT / "data" / "synthetic" / "event_readiness"


def _request(pack: str, tmp_path: Path) -> CorpusIntakeRequest:
    root = EVENT_ROOT / pack
    return CorpusIntakeRequest(
        source_root=root,
        manifest_path=root / "manifest.xlsx",
        column_mapping={},
        output_root=tmp_path / "generated",
    )


def test_valid_pack_contract_is_ready(tmp_path: Path) -> None:
    report = EventCorpusAdapter.from_project_root(PROJECT_ROOT).inspect(
        _request("valid_pack", tmp_path)
    )

    assert report.status is CorpusStatus.READY
    assert report.manifest_row_count == 3
    assert report.matched_html_count == 3
    assert report.blocking_issue_count == 0


def test_prepare_preserves_external_source_reference_without_copying(tmp_path: Path) -> None:
    request = _request("valid_pack", tmp_path)
    prepared = EventCorpusAdapter.from_project_root(PROJECT_ROOT).prepare(request)

    assert prepared is not None
    assert prepared.source_root == request.source_root.resolve()
    assert {item.relative_path for item in prepared.documents} == {
        "knowledge/alert_table.html",
        "knowledge/contextual_workflow.html",
        "knowledge/direct_rule.html",
    }
    assert not (request.output_root / "knowledge").exists()


def test_public_contract_methods_are_present() -> None:
    assert callable(EventCorpusAdapter.inspect)
    assert callable(EventCorpusAdapter.prepare)
    assert callable(EventCorpusAdapter.smoke_test)
