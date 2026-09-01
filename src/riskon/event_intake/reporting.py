"""Safe ER-A JSON, JSONL, and Markdown report writers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from riskon.event_intake.models import (
    CorpusCompatibilityReport,
    CorpusIntakeReport,
    PreparedCorpus,
)


def write_inspection_reports(
    report: CorpusIntakeReport,
    output_root: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    """Write inspection and inventory artifacts without source content."""

    output_root.mkdir(parents=True, exist_ok=True)
    inspection_json = output_root / "inspection.json"
    inspection_md = output_root / "inspection.md"
    document_jsonl = output_root / "document_inventory.jsonl"
    link_jsonl = output_root / "link_inventory.jsonl"
    asset_jsonl = output_root / "asset_inventory.jsonl"
    inspection_json.write_text(_json(_safe_model(report)), encoding="utf-8")
    inspection_md.write_text(render_inspection_markdown(report), encoding="utf-8")
    _write_jsonl(document_jsonl, [_safe_model(item) for item in report.documents])
    _write_jsonl(link_jsonl, [_safe_model(item) for item in report.local_link_edges])
    _write_jsonl(asset_jsonl, [_safe_model(item) for item in report.assets])
    return inspection_json, inspection_md, document_jsonl, link_jsonl, asset_jsonl


def write_prepared_corpus(prepared: PreparedCorpus, output_root: Path) -> Path:
    """Write a redacted prepared descriptor, never an absolute source path."""

    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "prepared_corpus.json"
    payload = _safe_model(prepared)
    payload["source_root"] = "<external-source-root>"
    path.write_text(_json(payload), encoding="utf-8")
    return path


def write_compatibility_report(
    report: CorpusCompatibilityReport,
    output_root: Path,
) -> Path:
    """Write the structured compatibility result."""

    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "compatibility.json"
    path.write_text(_json(_safe_model(report)), encoding="utf-8")
    return path


def render_inspection_markdown(report: CorpusIntakeReport) -> str:
    """Render a compact human-readable inventory without page text."""

    lines = [
        "# Event Corpus Inspection",
        "",
        f"- Status: `{report.status.value}`",
        f"- HTML files: {report.html_file_count}",
        f"- Manifest rows: {report.manifest_row_count}",
        f"- Matched HTML: {report.matched_html_count}",
        f"- Total corpus size: {report.total_corpus_size} bytes",
        f"- Corpus fingerprint: `{report.corpus_fingerprint}`",
        f"- External fetches: {report.external_fetches}",
        "",
        "## Inventory",
        "",
        f"- Headings / sections: {report.heading_count} / {report.section_count}",
        f"- Tables / rows: {report.table_count} / {report.table_row_count}",
        f"- Image/SVG references: {report.image_svg_reference_count}",
        f"- Local links / broken: {report.local_links} / {report.broken_local_links}",
        f"- External links: {report.external_links}",
        f"- Script/style/form tags: {report.script_count} / {report.style_count} / "
        f"{report.form_count}",
        f"- Source-instruction signals: {report.source_instruction_signal_count}",
        "",
        "## Issues",
        "",
    ]
    if report.issues:
        lines.extend(
            f"- `{issue.severity.value}` `{issue.code}`"
            + (f" ({issue.relative_path})" if issue.relative_path else "")
            for issue in report.issues
        )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "This report contains descriptors, counts, hashes, and issue codes only; "
            "source HTML and raw paragraphs are excluded.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write one safe JSON object per line."""

    content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(content, encoding="utf-8")


def _json(payload: dict[str, Any]) -> str:
    """Serialize safe payloads deterministically."""

    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _safe_model(model: Any) -> dict[str, Any]:
    """Serialize a model and redact accidental absolute/external-path values."""

    payload = cast(dict[str, Any], model.model_dump(mode="json"))
    return cast(dict[str, Any], _redact(payload))


def _redact(value: Any) -> Any:
    """Recursively keep reports free of absolute paths and fetched URLs."""

    if isinstance(value, dict):
        return {str(key): _redact_field(str(key), item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        lowered = value.casefold()
        if lowered.startswith(("http://", "https://", "//")):
            return "<external-url>"
        if value.startswith("/"):
            return "<absolute-path-redacted>"
    return value


def _redact_field(key: str, value: Any) -> Any:
    """Apply field-aware redaction before generic recursive serialization."""

    if key == "url" and isinstance(value, str):
        lowered = value.casefold()
        if lowered.startswith(("http://", "https://", "//")):
            return "<external-url>"
    if isinstance(value, str) and value.startswith("/"):
        return "<absolute-path-redacted>"
    return _redact(value)
