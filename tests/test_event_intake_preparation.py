"""ER-A descriptor preparation tests."""

from pathlib import Path

from event_intake_helpers import adapter, request_for

from riskon.event_intake.models import CorpusStatus


def test_prepared_corpus_contains_only_descriptor_graph(tmp_path: Path) -> None:
    request = request_for("valid_pack", tmp_path / "out")
    prepared = adapter().prepare(request)

    assert prepared is not None
    assert prepared.corpus_fingerprint
    assert all(item.relative_path.startswith("knowledge/") for item in prepared.documents)
    assert not hasattr(prepared, "raw_html")


def test_prepared_warning_codes_are_sorted_and_deterministic(tmp_path: Path) -> None:
    prepared = adapter().prepare(request_for("warning_pack", tmp_path / "out"))

    assert prepared is not None
    assert prepared.warnings == sorted(prepared.warnings)
    assert set(prepared.warnings) >= {
        "ORPHAN_HTML",
        "EXTERNAL_LINK_PRESENT",
        "MISSING_NONCRITICAL_ASSET",
        "SOURCE_INSTRUCTION_SIGNAL",
    }


def test_blocked_report_never_becomes_prepared(tmp_path: Path) -> None:
    event_adapter = adapter()
    request = request_for("invalid_pack", tmp_path / "out")
    report = event_adapter.inspect(request)

    assert report.status is CorpusStatus.BLOCKED
    assert event_adapter.prepare(request) is None


def test_output_path_is_not_part_of_prepared_contract(tmp_path: Path) -> None:
    prepared = adapter().prepare(request_for("valid_pack", tmp_path / "out"))

    assert prepared is not None
    assert "output_root" not in prepared.__class__.model_fields
