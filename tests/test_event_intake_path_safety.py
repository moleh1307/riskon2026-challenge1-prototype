"""ER-A source/output path boundary tests."""

from pathlib import Path

from event_intake_helpers import EVENT_ROOT, adapter, write_workbook

from riskon.event_intake import CorpusIntakeRequest
from riskon.event_intake.path_safety import (
    assess_paths,
    snapshot_source,
    snapshots_unchanged,
)


def test_output_inside_source_root_blocks_before_writing(tmp_path: Path) -> None:
    source = EVENT_ROOT / "valid_pack"
    request = CorpusIntakeRequest(
        source_root=source,
        manifest_path=source / "manifest.xlsx",
        output_root=source / "generated",
    )

    report = adapter().inspect(request)

    assert report.status.value == "BLOCKED"
    assert any(issue.code == "OUTPUT_INSIDE_SOURCE_ROOT" for issue in report.blocking_issues)


def test_external_manifest_file_is_allowed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.html").write_text("<h1>One</h1>", encoding="utf-8")
    manifest = tmp_path / "manifest.xlsx"
    write_workbook(manifest, ("filename", "title"), [("one.html", "One")])
    request = CorpusIntakeRequest(
        source_root=source,
        manifest_path=manifest,
        output_root=tmp_path / "out",
    )

    assessment = assess_paths(request)

    assert not any(issue.code == "MANIFEST_OUTSIDE_SOURCE_ROOT" for issue in assessment.issues)


def test_external_manifest_symlink_is_blocked(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.html").write_text("<h1>One</h1>", encoding="utf-8")
    manifest = tmp_path / "manifest.xlsx"
    write_workbook(manifest, ("filename", "title"), [("one.html", "One")])
    symlink = tmp_path / "manifest-link.xlsx"
    symlink.symlink_to(manifest)
    request = CorpusIntakeRequest(
        source_root=source,
        manifest_path=symlink,
        output_root=tmp_path / "out",
    )

    assessment = assess_paths(request)

    assert any(issue.code == "SYMLINK_ESCAPE" for issue in assessment.issues)


def test_missing_source_root_is_blocked(tmp_path: Path) -> None:
    source = tmp_path / "missing"
    request = CorpusIntakeRequest(
        source_root=source,
        manifest_path=source / "manifest.xlsx",
        output_root=tmp_path / "out",
    )

    report = adapter().inspect(request)

    assert report.status.value == "BLOCKED"
    assert any(issue.code == "SOURCE_ROOT_NOT_FOUND" for issue in report.blocking_issues)


def test_internal_symlink_is_allowed_but_external_symlink_is_not(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "knowledge").mkdir(parents=True)
    (source / "knowledge" / "inside.html").write_text("<h1>Inside</h1>", encoding="utf-8")
    (source / "knowledge" / "inside-link.html").symlink_to("inside.html")
    (source / "knowledge" / "escape.html").symlink_to(tmp_path / "outside.html")
    (tmp_path / "outside.html").write_text("<h1>Outside</h1>", encoding="utf-8")
    write_workbook(
        source / "manifest.xlsx",
        ("filename", "title"),
        [("knowledge/inside.html", "Inside")],
    )
    request = CorpusIntakeRequest(
        source_root=source,
        manifest_path=source / "manifest.xlsx",
        output_root=tmp_path / "out",
    )

    assessment = assess_paths(request)

    assert not any(
        issue.relative_path == "knowledge/inside-link.html" for issue in assessment.issues
    )
    assert any(
        issue.code == "SYMLINK_ESCAPE" and issue.relative_path == "knowledge/escape.html"
        for issue in assessment.issues
    )


def test_snapshot_detects_file_hash_changes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    path = source / "one.html"
    path.write_text("one", encoding="utf-8")
    before = snapshot_source(source)
    path.write_text("two", encoding="utf-8")
    after = snapshot_source(source)

    assert not snapshots_unchanged(before, after)


def test_snapshot_detects_directory_entry_changes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.html").write_text("one", encoding="utf-8")
    before = snapshot_source(source)
    (source / "two.html").write_text("two", encoding="utf-8")
    after = snapshot_source(source)

    assert before.file_hashes != after.file_hashes
    assert before.entries != after.entries
