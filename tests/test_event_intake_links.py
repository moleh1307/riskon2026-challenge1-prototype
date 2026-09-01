"""ER-A local-link classification tests."""

from pathlib import Path

from bs4 import BeautifulSoup

from riskon.event_intake.links import scan_links


def test_resolved_local_link_is_an_edge(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "knowledge").mkdir(parents=True)
    (root / "knowledge" / "one.html").write_text("<h1>One</h1>", encoding="utf-8")
    (root / "knowledge" / "two.html").write_text('<a href="one.html">One</a>', encoding="utf-8")

    result = scan_links(
        BeautifulSoup((root / "knowledge" / "two.html").read_text(), "lxml"),
        "knowledge/two.html",
        root,
    )

    assert result.local_count == 1
    assert result.broken_count == 0
    assert result.edges[0].target_relative_path == "knowledge/one.html"


def test_broken_local_link_is_warning(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    result = scan_links(
        BeautifulSoup('<a href="missing.html">Missing</a>', "lxml"),
        "page.html",
        root,
    )

    assert result.broken_count == 1
    assert result.issues[0].code == "BROKEN_LOCAL_LINK"


def test_anchor_link_checks_same_page_anchor(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    soup = BeautifulSoup('<h1 id="known">Known</h1><a href="#known">Go</a>', "lxml")

    result = scan_links(soup, "page.html", root)

    assert result.edges[-1].anchor == "known"
    assert result.edges[-1].resolved


def test_external_link_is_not_resolved_or_fetched(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    result = scan_links(
        BeautifulSoup('<a href="https://example.invalid">External</a>', "lxml"),
        "page.html",
        root,
    )

    assert result.external_count == 1
    assert result.edges[0].kind == "EXTERNAL"
    assert result.edges[0].target_relative_path is None


def test_link_root_escape_is_blocking(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "knowledge").mkdir(parents=True)
    result = scan_links(
        BeautifulSoup('<a href="../../outside.html">Escape</a>', "lxml"),
        "knowledge/page.html",
        root,
    )

    assert any(issue.code == "SYMLINK_ESCAPE" for issue in result.issues)
