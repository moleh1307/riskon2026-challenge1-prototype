"""ER-A local asset inventory tests."""

from pathlib import Path

from bs4 import BeautifulSoup

from riskon.event_intake.assets import scan_assets


def test_existing_local_asset_is_hashed(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "flow.svg").write_text("<svg />", encoding="utf-8")
    soup = BeautifulSoup('<img src="assets/flow.svg" alt="flow">', "lxml")

    result = scan_assets(soup, "page.html", root)

    assert result.image_svg_reference_count == 1
    assert result.descriptors[0].exists
    assert result.descriptors[0].sha256


def test_missing_local_asset_is_noncritical_warning(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    soup = BeautifulSoup('<img src="assets/missing.png" alt="optional">', "lxml")

    result = scan_assets(soup, "page.html", root)

    assert result.missing_paths == ("assets/missing.png",)
    assert result.issues[0].code == "MISSING_NONCRITICAL_ASSET"


def test_external_asset_is_counted_without_fetching(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    soup = BeautifulSoup('<img src="https://example.invalid/flow.svg">', "lxml")

    result = scan_assets(soup, "page.html", root)

    assert result.external_count == 1
    assert result.descriptors[0].kind == "EXTERNAL"
    assert result.descriptors[0].relative_path is None


def test_inline_asset_does_not_leak_data_uri(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    soup = BeautifulSoup('<img src="data:image/png;base64,secret">', "lxml")

    result = scan_assets(soup, "page.html", root)

    assert result.descriptors[0].kind == "INLINE"
    assert "secret" not in str(result.descriptors[0].model_dump())
    assert "<inline-asset>" in result.refs


def test_asset_path_escape_is_blocking(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "knowledge").mkdir(parents=True)
    soup = BeautifulSoup('<img src="../../outside.png">', "lxml")

    result = scan_assets(soup, "knowledge/page.html", root)

    assert any(issue.code == "SYMLINK_ESCAPE" for issue in result.issues)


def test_duplicate_asset_references_are_compacted(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "flow.svg").write_text("<svg />", encoding="utf-8")
    soup = BeautifulSoup(
        '<img src="assets/flow.svg"><img src="assets/flow.svg">',
        "lxml",
    )

    result = scan_assets(soup, "page.html", root)

    assert len(result.descriptors) == 1
    assert result.descriptors[0].reference_count == 2
