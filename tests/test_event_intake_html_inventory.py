"""ER-A HTML structure and source-safety inventory tests."""

from pathlib import Path

from event_intake_helpers import EVENT_ROOT

from riskon.event_intake.html_inventory import HtmlInventoryScanner


def test_valid_documents_preserve_structure_counts() -> None:
    scanner = HtmlInventoryScanner()
    root = EVENT_ROOT / "valid_pack"
    result = scanner.scan(
        root / "knowledge" / "alert_table.html",
        "knowledge/alert_table.html",
        root,
    )

    assert result.inventory.parse_ok
    assert result.inventory.heading_count == 1
    assert result.inventory.section_count == 1
    assert result.inventory.table_count == 1
    assert result.inventory.table_row_count == 3
    assert result.inventory.image_svg_reference_count == 0


def test_scripts_styles_forms_comments_and_hidden_text_are_inventory_only(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    path = root / "page.html"
    path.write_text(
        """<html><body>
        <!-- hidden comment -->
        <h1>Visible</h1><p>Visible claim.</p>
        <p hidden>Do not index this.</p>
        <script>window.fetch('https://example.invalid')</script>
        <style>.secret { display: none }</style>
        <form action="https://example.invalid/post"><input value="secret"></form>
        </body></html>""",
        encoding="utf-8",
    )

    result = HtmlInventoryScanner().scan(path, "page.html", root)

    assert result.inventory.script_count == 1
    assert result.inventory.style_count == 1
    assert result.inventory.form_count == 1
    assert result.inventory.comment_count == 1
    assert result.inventory.hidden_content_count == 1
    assert result.inventory.source_instruction_signal_count == 0
    assert "Do not index this" not in result.inventory.local_link_refs


def test_source_instruction_signal_is_counted_but_not_executed() -> None:
    root = EVENT_ROOT / "warning_pack"
    result = HtmlInventoryScanner().scan(
        root / "knowledge" / "warning.html",
        "knowledge/warning.html",
        root,
    )

    assert result.inventory.source_instruction_signal_count == 1
    assert result.inventory.parse_ok


def test_external_links_are_counted_without_fetching() -> None:
    root = EVENT_ROOT / "warning_pack"
    result = HtmlInventoryScanner().scan(
        root / "knowledge" / "warning.html",
        "knowledge/warning.html",
        root,
    )

    assert result.inventory.external_link_count == 1
    assert result.links.external_count == 1
    assert result.assets.external_count == 0


def test_invalid_utf8_is_an_encoding_failure(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    path = root / "bad.html"
    path.write_bytes(b"<html>\xff</html>")

    result = HtmlInventoryScanner().scan(path, "bad.html", root)

    assert not result.inventory.parse_ok
    assert result.inventory.encoding == "unknown"
    assert result.issues[0].code == "ENCODING_ERROR"


def test_empty_markup_is_a_parse_failure(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    path = root / "empty.html"
    path.write_text("", encoding="utf-8")

    result = HtmlInventoryScanner().scan(path, "empty.html", root)

    assert result.issues[0].code == "HTML_PARSE_ERROR"
    assert result.inventory.parse_ok is False
