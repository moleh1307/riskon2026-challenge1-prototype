"""Non-fetching local-link inventory for event HTML."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Tag

from riskon.event_intake.models import CorpusIssue, IssueSeverity, LocalLinkEdge


@dataclass(frozen=True)
class LinkScanResult:
    """Edges and safe counts produced from one parsed HTML document."""

    edges: tuple[LocalLinkEdge, ...]
    issues: tuple[CorpusIssue, ...]
    local_count: int
    broken_count: int
    external_count: int


def scan_links(
    soup: BeautifulSoup,
    source_relative_path: str,
    source_root: Path,
) -> LinkScanResult:
    """Classify anchor links without opening or fetching any target."""

    anchors = {
        str(tag.get("id")).strip()
        for tag in soup.find_all(True)
        if tag.get("id") is not None and str(tag.get("id")).strip()
    }
    anchors.update(
        str(tag.get("name")).strip()
        for tag in soup.find_all(True)
        if tag.get("name") is not None and str(tag.get("name")).strip()
    )
    edges: list[LocalLinkEdge] = []
    issues: list[CorpusIssue] = []
    local_count = 0
    broken_count = 0
    external_count = 0
    seen: set[tuple[str, str, str | None, bool]] = set()

    for tag in soup.find_all(["a", "area"]):
        if not isinstance(tag, Tag):
            continue
        raw_href = str(tag.get("href", "")).strip()
        if not raw_href:
            continue
        parsed = urlsplit(raw_href)
        if parsed.scheme.casefold() in {"http", "https"} or parsed.netloc:
            key: tuple[str, str, str | None, bool] = (
                "EXTERNAL",
                "<external-url>",
                None,
                False,
            )
            if key not in seen:
                edges.append(
                    LocalLinkEdge(
                        source_relative_path=source_relative_path,
                        href="<external-url>",
                        target_relative_path=None,
                        anchor=None,
                        kind="EXTERNAL",
                        resolved=False,
                        broken=False,
                    )
                )
                seen.add(key)
            external_count += 1
            continue
        if parsed.scheme.casefold() in {"mailto", "javascript", "data", "file"}:
            issues.append(
                CorpusIssue(
                    code="UNSUPPORTED_LINK_SCHEME",
                    severity=IssueSeverity.WARNING,
                    relative_path=source_relative_path,
                    detail="A non-local link scheme was recorded without executing it.",
                )
            )
            continue
        target, anchor, escaped = _target_path(
            source_relative_path,
            parsed.path,
            parsed.fragment,
            source_root,
        )
        if escaped:
            issues.append(
                CorpusIssue(
                    code="SYMLINK_ESCAPE",
                    severity=IssueSeverity.ERROR,
                    relative_path=source_relative_path,
                    detail="A local link resolves outside the declared source root.",
                )
            )
            continue
        if anchor is not None and not parsed.path:
            resolved = anchor in anchors
        else:
            resolved = _target_exists(target, source_root) if target is not None else False
            if anchor is not None:
                resolved = resolved and _anchor_exists(target, anchor, source_root)
        broken = not resolved
        local_count += 1
        broken_count += int(broken)
        if broken:
            issues.append(
                CorpusIssue(
                    code="BROKEN_LOCAL_LINK",
                    severity=IssueSeverity.WARNING,
                    relative_path=source_relative_path,
                    detail="A local link target or anchor could not be resolved.",
                )
            )
        key = ("LOCAL", raw_href, target, broken)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            LocalLinkEdge(
                source_relative_path=source_relative_path,
                href=raw_href,
                target_relative_path=target,
                anchor=anchor,
                kind="LOCAL",
                resolved=resolved,
                broken=broken,
            )
        )
    return LinkScanResult(
        edges=tuple(edges),
        issues=tuple(_unique_issues(issues)),
        local_count=local_count,
        broken_count=broken_count,
        external_count=external_count,
    )


def _target_path(
    source_relative_path: str,
    raw_path: str,
    raw_fragment: str,
    source_root: Path,
) -> tuple[str | None, str | None, bool]:
    """Normalize one local target and flag root traversal."""

    anchor_path = unquote(raw_path)
    if raw_path.startswith("/"):
        return None, None, True
    source_parent = PurePosixPath(source_relative_path).parent.as_posix()
    joined = (
        source_relative_path
        if not anchor_path
        else posixpath.normpath(posixpath.join(source_parent, anchor_path))
    )
    if joined == ".":
        joined = source_relative_path
    target = PurePosixPath(joined)
    if any(part in {"", ".."} for part in target.parts):
        return None, None, True
    target_relative = target.as_posix()
    resolved_path = (source_root / target_relative).resolve(strict=False)
    if not resolved_path.is_relative_to(source_root.resolve(strict=False)):
        return None, None, True
    return target_relative, unquote(raw_fragment) or None, False


def _target_exists(target: str | None, source_root: Path) -> bool:
    """Check existence locally without following a target outside the root."""

    if target is None:
        return False
    path = (source_root / target).resolve(strict=False)
    return path.is_relative_to(source_root.resolve(strict=False)) and path.is_file()


def _anchor_exists(target: str | None, anchor: str, source_root: Path) -> bool:
    """Check a target anchor without fetching or exposing document text."""

    if target is None:
        return False
    path = (source_root / target).resolve(strict=False)
    if not path.is_relative_to(source_root.resolve(strict=False)) or not path.is_file():
        return False
    try:
        target_soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    except (OSError, UnicodeDecodeError):
        return False
    return any(
        str(tag.get(attribute)).strip() == anchor
        for tag in target_soup.find_all(True)
        for attribute in ("id", "name")
        if tag.get(attribute) is not None
    )


def _unique_issues(issues: list[CorpusIssue]) -> list[CorpusIssue]:
    """Keep one deterministic issue row per observation."""

    seen: set[tuple[str, IssueSeverity, str | None, str | None]] = set()
    result: list[CorpusIssue] = []
    for issue in issues:
        key = (issue.code, issue.severity, issue.relative_path, issue.detail)
        if key not in seen:
            result.append(issue)
            seen.add(key)
    return result
