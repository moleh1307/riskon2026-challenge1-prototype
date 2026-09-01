"""Local asset inventory without fetching or interpreting asset contents."""

from __future__ import annotations

import hashlib
import posixpath
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup, Tag

from riskon.event_intake.models import AssetDescriptor, CorpusIssue, IssueSeverity


@dataclass(frozen=True)
class AssetScanResult:
    """Asset descriptors and safe counts for one HTML document."""

    descriptors: tuple[AssetDescriptor, ...]
    refs: tuple[str, ...]
    issues: tuple[CorpusIssue, ...]
    image_svg_reference_count: int
    external_count: int
    missing_paths: tuple[str, ...]


def scan_assets(
    soup: BeautifulSoup,
    source_relative_path: str,
    source_root: Path,
) -> AssetScanResult:
    """Inventory image/SVG-like references and never open external URLs."""

    occurrences: list[str] = []
    for tag in soup.find_all(["img", "source", "object", "image"]):
        if not isinstance(tag, Tag):
            continue
        attribute = "data" if tag.name == "object" else "src"
        raw = str(tag.get(attribute, "")).strip()
        if tag.name == "image" and not raw:
            raw = str(tag.get("href", tag.get("xlink:href", ""))).strip()
        if raw:
            occurrences.append(raw)

    descriptors: list[AssetDescriptor] = []
    refs: list[str] = []
    issues: list[CorpusIssue] = []
    missing_paths: list[str] = []
    seen: dict[tuple[str, str | None], AssetDescriptor] = {}
    external_count = 0

    for raw in occurrences:
        parsed = urlsplit(raw)
        scheme = parsed.scheme.casefold()
        if scheme in {"http", "https"} or parsed.netloc:
            kind = "EXTERNAL"
            relative = None
            ref = "<external-asset>"
            external_count += 1
            issues.append(
                CorpusIssue(
                    code="EXTERNAL_LINK_PRESENT",
                    severity=IssueSeverity.WARNING,
                    relative_path=source_relative_path,
                    detail="An external asset reference was recorded without fetching it.",
                )
            )
        elif scheme in {"data", "blob"}:
            kind = "INLINE"
            relative = None
            ref = "<inline-asset>"
        elif scheme or parsed.path.startswith("/"):
            kind = "UNSUPPORTED"
            relative = None
            ref = "<unsupported-asset>"
            issues.append(
                CorpusIssue(
                    code="UNSUPPORTED_ASSET_REFERENCE",
                    severity=IssueSeverity.WARNING,
                    relative_path=source_relative_path,
                    detail="A non-local asset reference was ignored.",
                )
            )
        else:
            relative, escaped = _normalize_asset_path(
                source_relative_path, parsed.path, source_root
            )
            if escaped:
                kind = "LOCAL"
                ref = "<escaped-asset>"
                issues.append(
                    CorpusIssue(
                        code="SYMLINK_ESCAPE",
                        severity=IssueSeverity.ERROR,
                        relative_path=source_relative_path,
                        detail="A local asset reference resolves outside the source root.",
                    )
                )
            else:
                kind = "LOCAL"
                ref = relative or "<missing-asset>"

        refs.append(ref)
        key = (kind, relative)
        existing = seen.get(key)
        if existing is not None:
            seen[key] = existing.model_copy(
                update={"reference_count": existing.reference_count + 1}
            )
            continue

        exists = False
        size_bytes: int | None = None
        digest: str | None = None
        if kind == "LOCAL" and relative is not None:
            candidate = (source_root / relative).resolve(strict=False)
            if not candidate.is_relative_to(source_root.resolve(strict=False)):
                issues.append(
                    CorpusIssue(
                        code="SYMLINK_ESCAPE",
                        severity=IssueSeverity.ERROR,
                        relative_path=source_relative_path,
                        detail="A local asset symlink resolves outside the source root.",
                    )
                )
            elif candidate.is_file():
                exists = True
                size_bytes = candidate.stat().st_size
                digest = _sha256(candidate)
            else:
                missing_paths.append(relative)
                issues.append(
                    CorpusIssue(
                        code="MISSING_NONCRITICAL_ASSET",
                        severity=IssueSeverity.WARNING,
                        relative_path=relative,
                        detail="A referenced non-critical local asset is missing.",
                    )
                )
        descriptor = AssetDescriptor(
            source_relative_path=source_relative_path,
            relative_path=relative,
            kind=kind,
            reference_count=1,
            exists=exists,
            size_bytes=size_bytes,
            sha256=digest,
        )
        descriptors.append(descriptor)
        seen[key] = descriptor

    # ``seen`` carries the incremented models; rebuild the deterministic list.
    descriptors = list(seen.values())
    return AssetScanResult(
        descriptors=tuple(descriptors),
        refs=tuple(dict.fromkeys(refs)),
        issues=tuple(_unique_issues(issues)),
        image_svg_reference_count=len(occurrences),
        external_count=external_count,
        missing_paths=tuple(dict.fromkeys(missing_paths)),
    )


def _normalize_asset_path(
    source_relative_path: str,
    raw_path: str,
    source_root: Path,
) -> tuple[str | None, bool]:
    """Resolve a relative asset path and detect root traversal/symlink escape."""

    path_part = unquote(raw_path)
    if not path_part:
        return None, False
    parent = PurePosixPath(source_relative_path).parent.as_posix()
    joined = posixpath.normpath(posixpath.join(parent, path_part))
    target = PurePosixPath(joined)
    if any(part in {"", ".."} for part in target.parts):
        return None, True
    relative = target.as_posix()
    resolved = (source_root / relative).resolve(strict=False)
    return relative, not resolved.is_relative_to(source_root.resolve(strict=False))


def _sha256(path: Path) -> str:
    """Hash one local asset without exposing its contents."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_issues(issues: list[CorpusIssue]) -> list[CorpusIssue]:
    """Deduplicate repeated asset observations."""

    seen: set[tuple[str, IssueSeverity, str | None, str | None]] = set()
    result: list[CorpusIssue] = []
    for issue in issues:
        key = (issue.code, issue.severity, issue.relative_path, issue.detail)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result
