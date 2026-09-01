"""Read-only path validation and source mutation snapshots."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from riskon.event_intake.models import CorpusIntakeRequest, CorpusIssue, IssueSeverity


@dataclass(frozen=True)
class SourceSnapshot:
    """Stable source tree snapshot used by the compatibility invariant."""

    entries: tuple[str, ...]
    file_hashes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class PathAssessment:
    """Resolved paths plus safe file candidates and path issues."""

    source_root: Path
    manifest_path: Path
    output_root: Path
    files: tuple[Path, ...]
    html_files: tuple[Path, ...]
    issues: tuple[CorpusIssue, ...]


def resolve_path(path: Path) -> Path:
    """Resolve a user-provided path without requiring it to exist."""

    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve(strict=False)


def relative_path(path: Path, root: Path) -> str:
    """Return a normalized relative path suitable for a report."""

    return path.relative_to(root).as_posix()


def assess_paths(request: CorpusIntakeRequest) -> PathAssessment:
    """Validate source, manifest, output, and symlink boundaries."""

    root = resolve_path(request.source_root)
    manifest = resolve_path(request.manifest_path)
    output = resolve_path(request.output_root)
    issues: list[CorpusIssue] = []

    if not root.exists():
        issues.append(
            CorpusIssue(
                code="SOURCE_ROOT_NOT_FOUND",
                severity=IssueSeverity.ERROR,
                detail="The declared source root does not exist.",
            )
        )
        return PathAssessment(root, manifest, output, (), (), tuple(issues))
    if not root.is_dir():
        issues.append(
            CorpusIssue(
                code="SOURCE_ROOT_NOT_DIRECTORY",
                severity=IssueSeverity.ERROR,
                detail="The declared source root is not a directory.",
            )
        )
        return PathAssessment(root, manifest, output, (), (), tuple(issues))

    if output == root or output.is_relative_to(root):
        issues.append(
            CorpusIssue(
                code="OUTPUT_INSIDE_SOURCE_ROOT",
                severity=IssueSeverity.ERROR,
                detail="Generated output must remain outside the read-only source root.",
            )
        )

    if not manifest.is_relative_to(root):
        issues.append(
            CorpusIssue(
                code="MANIFEST_OUTSIDE_SOURCE_ROOT",
                severity=IssueSeverity.ERROR,
                detail="The manifest must be located below the declared source root.",
            )
        )

    files: list[Path] = []
    html_files: list[Path] = []
    for current_root, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_root)
        for directory in list(directories):
            candidate = current / directory
            if not candidate.is_symlink():
                continue
            directories.remove(directory)
            _check_symlink(candidate, root, issues)
        for filename in filenames:
            candidate = current / filename
            files.append(candidate)
            if candidate.is_symlink():
                if not _check_symlink(candidate, root, issues):
                    continue
            if candidate.suffix.lower() in {".html", ".htm"} and candidate.is_file():
                html_files.append(candidate)

    if manifest.is_symlink() and not _check_symlink(manifest, root, issues):
        issues.append(
            CorpusIssue(
                code="MANIFEST_NOT_FOUND",
                severity=IssueSeverity.ERROR,
                detail="The manifest symlink does not resolve inside the source root.",
            )
        )

    if not manifest.is_file():
        issues.append(
            CorpusIssue(
                code="MANIFEST_NOT_FOUND",
                severity=IssueSeverity.ERROR,
                detail="The declared manifest is not a file.",
            )
        )
    return PathAssessment(root, manifest, output, tuple(files), tuple(html_files), tuple(issues))


def _check_symlink(path: Path, root: Path, issues: list[CorpusIssue]) -> bool:
    """Record a root escape and return whether a symlink remains safe."""

    target = path.resolve(strict=False)
    if target.is_relative_to(root):
        return True
    issues.append(
        CorpusIssue(
            code="SYMLINK_ESCAPE",
            severity=IssueSeverity.ERROR,
            relative_path=relative_path(path, root),
            detail="A source symlink resolves outside the declared root.",
        )
    )
    return False


def snapshot_source(root: Path) -> SourceSnapshot:
    """Hash regular source files and record every directory entry."""

    entries: list[str] = []
    file_hashes: list[tuple[str, str]] = []
    if not root.is_dir():
        return SourceSnapshot((), ())
    for current_root, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_root)
        for directory in directories:
            candidate = current / directory
            entries.append(_entry_label(candidate, root, "D"))
        for filename in filenames:
            candidate = current / filename
            rel = relative_path(candidate, root)
            if candidate.is_symlink():
                entries.append(_entry_label(candidate, root, "L"))
                continue
            entries.append(f"F:{rel}")
            if candidate.is_file():
                file_hashes.append((rel, _sha256(candidate)))
    return SourceSnapshot(tuple(sorted(entries)), tuple(sorted(file_hashes)))


def snapshots_unchanged(before: SourceSnapshot, after: SourceSnapshot) -> bool:
    """Return whether both entry and regular-file hash snapshots are equal."""

    return before == after


def _entry_label(path: Path, root: Path, kind: str) -> str:
    """Create a stable entry label without exposing an absolute path."""

    return f"{kind}:{relative_path(path, root)}"


def _sha256(path: Path) -> str:
    """Hash one file in bounded chunks."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
