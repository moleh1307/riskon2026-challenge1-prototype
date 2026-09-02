"""Attribute-aware parser for the Confluence storage format."""

from __future__ import annotations

from pathlib import Path

import lxml.html  # type: ignore[import-untyped]
from lxml.html import HtmlElement

from riskon.event_structure.icons import ICON_URL_MARKER
from riskon.event_structure.ir import (
    DYNAMIC_MACROS,
    AttachmentRef,
    AttachmentVia,
    Document,
    LinkKind,
    LinkRef,
    MacroRef,
    ParseIssue,
    Section,
)
from riskon.event_structure.legend import extract_legend
from riskon.event_structure.tables import build_table

WIKI_HOST = "wiki.juliusbaer.com"
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
NON_CONTENT_TAGS = frozenset({"ac:parameter", "ri:url", "ri:attachment", "ri:page"})


def _page_text(element: HtmlElement) -> str:
    parts: list[str] = []
    if element.text:
        parts.append(element.text)
    for child in element:
        if isinstance(child.tag, str) and child.tag in NON_CONTENT_TAGS:
            if child.tail:
                parts.append(child.tail)
            continue
        parts.append(_page_text(child))
        if child.tail:
            parts.append(child.tail)
    return " ".join(" ".join(parts).split())


def _headings_before_tables(root: HtmlElement) -> dict[HtmlElement, tuple[str, int]]:
    found: dict[HtmlElement, tuple[str, int]] = {}
    current = ("", 0)
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        if node.tag in HEADING_TAGS:
            text = " ".join((node.text_content() or "").split())
            if text:
                current = (text, int(node.tag[1]))
        elif node.tag == "table" and next(node.iterancestors("table"), None) is None:
            found[node] = current
    return found


def _sections(root: HtmlElement) -> list[Section]:
    sections: list[Section] = [Section()]

    def add(text: str | None) -> None:
        cleaned = " ".join((text or "").split())
        if cleaned:
            sections[-1].text = f"{sections[-1].text} {cleaned}".strip()

    def walk(element: HtmlElement) -> None:
        for child in element:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag == "table" or tag in NON_CONTENT_TAGS:
                add(child.tail)
                continue
            if tag in HEADING_TAGS:
                heading = " ".join((child.text_content() or "").split())
                if heading:
                    sections.append(Section(heading=heading, level=int(tag[1])))
                add(child.tail)
                continue
            add(child.text)
            walk(child)
            add(child.tail)

    add(root.text)
    walk(root)
    return [section for section in sections if section.text or section.heading]


def _links(root: HtmlElement) -> list[LinkRef]:
    found: list[LinkRef] = []
    for node in root.iter("ri:page"):
        title = node.get("ri:content-title")
        if title:
            parent = node.getparent()
            anchor = parent.get("ac:anchor") if parent is not None else None
            found.append(LinkRef(kind="internal_page", target=title, anchor=anchor))
    for node in root.iter("a"):
        href = node.get("href")
        if not href:
            continue
        kind: LinkKind = "wiki_url" if WIKI_HOST in href else "external"
        found.append(LinkRef(kind=kind, target=href))
    return found


def _attachments(root: HtmlElement) -> list[AttachmentRef]:
    found: list[AttachmentRef] = []
    for node in root.iter("ri:attachment"):
        filename = node.get("ri:filename")
        if not filename:
            continue
        ancestors = {
            ancestor.tag for ancestor in node.iterancestors() if isinstance(ancestor.tag, str)
        }
        via: AttachmentVia = "image" if "ac:image" in ancestors else "view-file"
        found.append(AttachmentRef(filename=filename, via=via))
    for node in root.iter("ac:image"):
        url = next(
            (child.get("ri:value") for child in node.iter("ri:url") if child.get("ri:value")),
            None,
        )
        if url and ICON_URL_MARKER not in url:
            found.append(AttachmentRef(filename=url, via="image"))
    # Keep repeated source references: the gap register measures dependency occurrences,
    # while callers may deduplicate targets separately when they need distinct assets.
    return found


def _macros(root: HtmlElement) -> tuple[list[MacroRef], list[ParseIssue]]:
    macros: list[MacroRef] = []
    issues: list[ParseIssue] = []
    for node in root.iter("ac:structured-macro"):
        name = node.get("ac:name")
        if not name:
            continue
        dynamic = name in DYNAMIC_MACROS
        macros.append(MacroRef(name=name, dynamic=dynamic))
        if dynamic:
            issues.append(
                ParseIssue(
                    code="dynamic_macro",
                    severity="note",
                    detail=f"{name!r} generates content at render time; body not in source",
                )
            )
    return macros, issues


def parse_html(source: str, page_id: str, source_path: str = "") -> Document:
    """Parse one page without flattening tables or interpreting icon meanings."""

    root = lxml.html.fromstring(source)
    issues: list[ParseIssue] = []
    tables = []
    top_level = [
        table for table in root.iter("table") if next(table.iterancestors("table"), None) is None
    ]
    headings = _headings_before_tables(root)
    for index, element in enumerate(top_level):
        table, table_issues = build_table(element, index)
        heading, heading_level = headings.get(element, ("", 0))
        tables.append(table.model_copy(update={"heading": heading, "heading_level": heading_level}))
        issues.extend(table_issues)
    macros, macro_issues = _macros(root)
    issues.extend(macro_issues)
    return Document(
        page_id=page_id,
        source_path=source_path,
        text=_page_text(root),
        legend=extract_legend(root, page_id),
        sections=_sections(root),
        tables=tables,
        links=_links(root),
        attachments=_attachments(root),
        macros=macros,
        issues=issues,
    )


def parse_page(path: Path) -> Document:
    """Parse a local page; the filename stem is its stable page id."""

    return parse_html(
        path.read_text(encoding="utf-8", errors="replace"),
        page_id=path.stem,
        source_path=str(path),
    )
