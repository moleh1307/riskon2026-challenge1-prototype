"""Shared ER-A test helpers."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from riskon.event_intake import CorpusIntakeRequest, EventCorpusAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENT_ROOT = PROJECT_ROOT / "data" / "synthetic" / "event_readiness"


def request_for(pack: str, output_root: Path) -> CorpusIntakeRequest:
    """Build a request for one committed synthetic pack."""

    source_root = EVENT_ROOT / pack
    return CorpusIntakeRequest(
        source_root=source_root,
        manifest_path=source_root / "manifest.xlsx",
        output_root=output_root,
    )


def adapter() -> EventCorpusAdapter:
    """Return the repository-configured adapter."""

    return EventCorpusAdapter.from_project_root(PROJECT_ROOT)


def write_workbook(path: Path, headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    """Create a small XLSX fixture for manifest edge tests."""

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    workbook.save(path)
