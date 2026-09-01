"""ER-A no-source-mutation invariants."""

from pathlib import Path

from event_intake_helpers import EVENT_ROOT, adapter, request_for

from riskon.event_intake.manifest import load_smoke_cases
from riskon.event_intake.path_safety import snapshot_source


def test_smoke_does_not_change_source_snapshot(tmp_path: Path) -> None:
    event_adapter = adapter()
    request = request_for("valid_pack", tmp_path / "out")
    prepared = event_adapter.prepare(request)
    cases = load_smoke_cases(EVENT_ROOT / "valid_pack" / "smoke_cases.json")
    assert prepared is not None
    before = snapshot_source(prepared.source_root)

    report = event_adapter.smoke_test(prepared, cases)

    after = snapshot_source(prepared.source_root)
    assert report.source_mutations == 0
    assert before == after


def test_inspection_does_not_create_output_inside_source(tmp_path: Path) -> None:
    source = EVENT_ROOT / "valid_pack"
    report = adapter().inspect(request_for("valid_pack", source / "generated"))

    assert report.status.value == "BLOCKED"
    assert not (source / "generated").exists()


def test_preparation_does_not_copy_html_to_output(tmp_path: Path) -> None:
    output = tmp_path / "out"
    prepared = adapter().prepare(request_for("valid_pack", output))

    assert prepared is not None
    assert not output.exists()


def test_source_hashes_are_reported_as_unchanged(tmp_path: Path) -> None:
    request = request_for("valid_pack", tmp_path / "out")
    event_adapter = adapter()
    prepared = event_adapter.prepare(request)
    cases = load_smoke_cases(EVENT_ROOT / "valid_pack" / "smoke_cases.json")
    assert prepared is not None

    report = event_adapter.smoke_test(prepared, cases)

    assert report.source_file_hashes_unchanged
    assert report.source_directory_entries_unchanged
