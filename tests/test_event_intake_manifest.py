"""ER-A workbook mapping and fail-closed manifest tests."""

from pathlib import Path

import pytest
from event_intake_helpers import EVENT_ROOT, write_workbook

from riskon.event_intake.manifest import ManifestLoader, load_column_aliases, load_smoke_cases


def test_alias_registry_matches_frozen_aliases() -> None:
    aliases = load_column_aliases(EVENT_ROOT / "manifest_column_aliases.json")

    assert aliases["filename"] == ("filename", "file_name", "file")
    assert aliases["title"] == ("title", "page_title", "page title")
    assert aliases["url"] == ("url", "page_url", "page url")


def test_case_insensitive_aliases_and_optional_url(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "knowledge").mkdir(parents=True)
    (source / "knowledge" / "one.html").write_text("<h1>One</h1>", encoding="utf-8")
    write_workbook(
        source / "manifest.xlsx",
        ("FILE_NAME", "PAGE TITLE"),
        [("knowledge/one.html", "One")],
    )

    result = ManifestLoader().load(source / "manifest.xlsx", source)

    assert result.manifest is not None
    assert result.manifest.has_url is False
    assert result.entries[0].source_url == "local://event-corpus/knowledge/one.html"


def test_explicit_mapping_supports_nonstandard_headers(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "knowledge").mkdir(parents=True)
    (source / "knowledge" / "one.html").write_text("<h1>One</h1>", encoding="utf-8")
    write_workbook(
        source / "manifest.xlsx",
        ("Document", "Page", "Web address"),
        [("knowledge/one.html", "One", "local://event-corpus/one")],
    )

    result = ManifestLoader().load(
        source / "manifest.xlsx",
        source,
        column_mapping={"filename": "Document", "title": "Page", "url": "Web address"},
    )

    assert result.manifest is not None
    assert result.manifest.column_mapping == {
        "filename": "Document",
        "title": "Page",
        "url": "Web address",
    }
    assert not result.issues


def test_unrecognized_headers_do_not_get_guessed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    write_workbook(source / "manifest.xlsx", ("doc", "name"), [("one.html", "One")])

    result = ManifestLoader().load(source / "manifest.xlsx", source)

    assert result.manifest is None
    assert any(issue.code == "MANIFEST_SCHEMA_UNRECOGNISED" for issue in result.issues)


def test_unknown_explicit_mapping_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    write_workbook(source / "manifest.xlsx", ("filename", "title"), [("one.html", "One")])

    result = ManifestLoader().load(
        source / "manifest.xlsx",
        source,
        column_mapping={"document": "filename"},
    )

    assert result.manifest is None
    assert any(issue.code == "MANIFEST_SCHEMA_UNRECOGNISED" for issue in result.issues)


def test_duplicate_filename_is_blocking_and_first_row_is_retained(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.html").write_text("<h1>One</h1>", encoding="utf-8")
    write_workbook(
        source / "manifest.xlsx",
        ("filename", "title"),
        [("one.html", "One"), ("one.html", "One again")],
    )

    result = ManifestLoader().load(source / "manifest.xlsx", source)

    assert result.manifest is not None
    assert len(result.entries) == 1
    assert any(issue.code == "DUPLICATE_FILENAME" for issue in result.issues)


def test_duplicate_title_is_warning(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.html").write_text("<h1>One</h1>", encoding="utf-8")
    (source / "two.html").write_text("<h1>Two</h1>", encoding="utf-8")
    write_workbook(
        source / "manifest.xlsx",
        ("filename", "title"),
        [("one.html", "Same"), ("two.html", "same")],
    )

    result = ManifestLoader().load(source / "manifest.xlsx", source)

    assert any(issue.code == "DUPLICATE_TITLE" for issue in result.issues)
    assert not any(issue.code == "DUPLICATE_FILENAME" for issue in result.issues)


def test_missing_html_is_blocking(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    write_workbook(source / "manifest.xlsx", ("filename", "title"), [("missing.html", "Missing")])

    result = ManifestLoader().load(source / "manifest.xlsx", source)

    assert any(issue.code == "MANIFEST_HTML_MISSING" for issue in result.issues)
    assert not result.entries


def test_unsafe_filename_is_not_normalized_into_acceptance(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    write_workbook(
        source / "manifest.xlsx",
        ("filename", "title"),
        [("../outside.html", "Escape")],
    )

    result = ManifestLoader().load(source / "manifest.xlsx", source)

    assert result.manifest is not None
    assert any(issue.code == "MANIFEST_SCHEMA_UNRECOGNISED" for issue in result.issues)
    assert not result.entries


def test_external_manifest_url_is_recorded_without_fetching(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.html").write_text("<h1>One</h1>", encoding="utf-8")
    write_workbook(
        source / "manifest.xlsx",
        ("filename", "title", "url"),
        [("one.html", "One", "https://example.invalid/one")],
    )

    result = ManifestLoader().load(source / "manifest.xlsx", source)

    assert result.entries[0].source_url.startswith("local://")
    assert any(issue.code == "EXTERNAL_LINK_PRESENT" for issue in result.issues)


def test_smoke_cases_are_closed_and_parse_decisions(tmp_path: Path) -> None:
    cases = load_smoke_cases(EVENT_ROOT / "valid_pack" / "smoke_cases.json")

    assert [case.id for case in cases] == ["ER-001", "ER-002", "ER-003"]
    assert cases[0].expected_decision.value == "ANSWER"
    assert cases[1].expected_decision.value == "CLARIFY"


def test_invalid_smoke_case_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text('{"schema_version":"2.0","cases":[]}', encoding="utf-8")

    with pytest.raises(ValueError, match="schema"):
        load_smoke_cases(path)
