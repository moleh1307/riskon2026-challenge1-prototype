"""Structure-only HTML inspection with executable markup removed."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Comment, Tag

from riskon.event_intake.assets import AssetScanResult, scan_assets
from riskon.event_intake.links import LinkScanResult, scan_links
from riskon.event_intake.models import CorpusIssue, HtmlInventory, IssueSeverity

_SOURCE_INSTRUCTION_PATTERNS = (
    re.compile(
        r"\b(ignore|disregard|override|forget)\b.{0,100}\b(previous|prior|above|system|developer|instructions?)\b",
        re.I | re.S,
    ),
    re.compile(
        r"\b(reveal|print|show|expose)\b.{0,80}\b(prompt|secret|credential|api key|password)\b",
        re.I | re.S,
    ),
    re.compile(
        r"\b(execute|run|call|upload|send)\b.{0,80}\b(command|tool|script|api|request)\b",
        re.I | re.S,
    ),
)


@dataclass(frozen=True)
class HtmlScanResult:
    """Inventory plus link/asset observations for one HTML file."""

    inventory: HtmlInventory
    links: LinkScanResult
    assets: AssetScanResult
    issues: tuple[CorpusIssue, ...]


class HtmlInventoryScanner:
    """Read HTML bytes locally and retain only safe structural metadata."""

    def scan(self, path: Path, relative_path: str, source_root: Path) -> HtmlScanResult:
        """Inspect one file without executing markup or retaining page content."""

        try:
            raw = path.read_bytes()
        except OSError:
            return self._failure(
                relative_path,
                "ENCODING_ERROR",
                "The HTML file could not be read.",
            )
        digest = hashlib.sha256(raw).hexdigest()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return self._failure(
                relative_path,
                "ENCODING_ERROR",
                "The HTML file is not valid UTF-8.",
                digest=digest,
                size_bytes=len(raw),
            )
        try:
            soup = BeautifulSoup(text, "lxml")
            if soup.find(True) is None:
                raise ValueError("empty HTML tree")
        except (TypeError, ValueError) as exc:
            del exc
            return self._failure(
                relative_path,
                "HTML_PARSE_ERROR",
                "The HTML file could not be parsed.",
                digest=digest,
                size_bytes=len(raw),
            )

        script_count = len(soup.find_all("script"))
        style_count = len(soup.find_all("style"))
        form_count = len(soup.find_all("form"))
        comment_count = len(soup.find_all(string=lambda value: isinstance(value, Comment)))
        hidden_count = sum(
            1 for tag in soup.find_all(True) if isinstance(tag, Tag) and _is_hidden(tag)
        )
        visible = _visible_soup(text)
        heading_count = len(visible.find_all(re.compile(r"^h[1-6]$")))
        table_count = len(visible.find_all("table"))
        table_row_count = len(visible.find_all("tr"))
        source_text = " ".join(visible.get_text(" ", strip=True).split())
        source_signal_count = sum(
            1 for pattern in _SOURCE_INSTRUCTION_PATTERNS if pattern.search(source_text)
        )
        links = scan_links(visible, relative_path, source_root)
        assets = scan_assets(visible, relative_path, source_root)
        issues = [*links.issues, *assets.issues]
        if links.external_count or assets.external_count:
            issues.append(
                CorpusIssue(
                    code="EXTERNAL_LINK_PRESENT",
                    severity=IssueSeverity.WARNING,
                    relative_path=relative_path,
                    detail="External URLs were inventoried without fetching them.",
                )
            )
        if source_signal_count:
            issues.append(
                CorpusIssue(
                    code="SOURCE_INSTRUCTION_SIGNAL",
                    severity=IssueSeverity.WARNING,
                    relative_path=relative_path,
                    detail="Instruction-like source text was recorded and will not execute.",
                )
            )
        inventory = HtmlInventory(
            relative_path=relative_path,
            sha256=digest,
            size_bytes=len(raw),
            encoding="utf-8",
            parse_ok=True,
            heading_count=heading_count,
            section_count=heading_count or 1,
            table_count=table_count,
            table_row_count=table_row_count,
            image_svg_reference_count=assets.image_svg_reference_count,
            local_link_count=links.local_count,
            broken_local_link_count=links.broken_count,
            external_link_count=links.external_count + assets.external_count,
            script_count=script_count,
            style_count=style_count,
            form_count=form_count,
            comment_count=comment_count,
            hidden_content_count=hidden_count,
            source_instruction_signal_count=source_signal_count,
            asset_refs=list(assets.refs),
            local_link_refs=[edge.href for edge in links.edges if edge.kind == "LOCAL"],
        )
        return HtmlScanResult(inventory, links, assets, tuple(_unique_issues(issues)))

    @staticmethod
    def _failure(
        relative_path: str,
        code: str,
        detail: str,
        *,
        digest: str = "",
        size_bytes: int = 0,
    ) -> HtmlScanResult:
        """Create a safe zero-count failure inventory."""

        issue = CorpusIssue(
            code=code,
            severity=IssueSeverity.ERROR,
            relative_path=relative_path,
            detail=detail,
        )
        inventory = HtmlInventory(
            relative_path=relative_path,
            sha256=digest,
            size_bytes=size_bytes,
            encoding="unknown",
            parse_ok=False,
            heading_count=0,
            section_count=0,
            table_count=0,
            table_row_count=0,
            image_svg_reference_count=0,
            local_link_count=0,
            broken_local_link_count=0,
            external_link_count=0,
            script_count=0,
            style_count=0,
            form_count=0,
            comment_count=0,
            hidden_content_count=0,
            source_instruction_signal_count=0,
            asset_refs=[],
            local_link_refs=[],
        )
        empty_links = LinkScanResult((), (), 0, 0, 0)
        empty_assets = AssetScanResult((), (), (), 0, 0, ())
        return HtmlScanResult(inventory, empty_links, empty_assets, (issue,))


def _visible_soup(text: str) -> BeautifulSoup:
    """Return a detached soup with executable, hidden, and comment nodes removed."""

    soup = BeautifulSoup(text, "lxml")
    for node in soup.find_all(["script", "style", "template", "noscript", "form"]):
        node.decompose()
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in list(soup.find_all(True)):
        if isinstance(tag, Tag) and _is_hidden(tag):
            tag.decompose()
    return soup


def _is_hidden(tag: Tag) -> bool:
    """Recognize common explicit hidden-content markers."""

    if tag.has_attr("hidden"):
        return True
    aria_hidden = str(tag.get("aria-hidden", "")).strip().casefold()
    if aria_hidden == "true":
        return True
    style = str(tag.get("style", "")).replace(" ", "").casefold()
    return "display:none" in style or "visibility:hidden" in style


def _unique_issues(issues: list[CorpusIssue]) -> list[CorpusIssue]:
    """Deduplicate issues emitted by link and asset scans."""

    seen: set[tuple[str, IssueSeverity, str | None, str | None]] = set()
    result: list[CorpusIssue] = []
    for issue in issues:
        key = (issue.code, issue.severity, issue.relative_path, issue.detail)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result
