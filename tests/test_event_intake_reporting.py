"""ER-A report serialization and leakage-boundary tests."""

import json
from pathlib import Path

from event_intake_helpers import EVENT_ROOT, adapter, request_for

from riskon.event_intake.manifest import load_smoke_cases
from riskon.event_intake.reporting import (
    render_inspection_markdown,
    write_compatibility_report,
    write_inspection_reports,
    write_prepared_corpus,
)


def test_inspection_reports_have_expected_safe_artifacts(tmp_path: Path) -> None:
    request = request_for("valid_pack", tmp_path / "out")
    event_adapter = adapter()
    report = event_adapter.inspect(request)

    paths = write_inspection_reports(report, request.output_root)

    assert [path.name for path in paths] == [
        "inspection.json",
        "inspection.md",
        "document_inventory.jsonl",
        "link_inventory.jsonl",
        "asset_inventory.jsonl",
    ]
    assert all(path.is_file() for path in paths)
    payload = json.loads((request.output_root / "inspection.json").read_text(encoding="utf-8"))
    assert payload["status"] == "READY"
    assert payload["documents"][0]["relative_path"].startswith("knowledge/")


def test_reports_exclude_raw_html_absolute_paths_and_external_urls(tmp_path: Path) -> None:
    request = request_for("warning_pack", tmp_path / "out")
    event_adapter = adapter()
    report = event_adapter.inspect(request)
    prepared = event_adapter.prepare(request)
    assert prepared is not None

    write_inspection_reports(report, request.output_root)
    write_prepared_corpus(prepared, request.output_root)
    cases = load_smoke_cases(EVENT_ROOT / "valid_pack" / "smoke_cases.json")
    compatibility = event_adapter.smoke_test(
        adapter().prepare(request_for("valid_pack", tmp_path / "valid-out")),
        cases,
    )
    write_compatibility_report(compatibility, request.output_root)

    content = "\n".join(
        path.read_text(encoding="utf-8") for path in request.output_root.iterdir() if path.is_file()
    )
    assert "<html" not in content.casefold()
    assert "<p>" not in content.casefold()
    assert str(request.source_root) not in content
    assert "https://" not in content
    assert "ignore previous instructions" not in content.casefold()
    prepared_payload = json.loads(
        (request.output_root / "prepared_corpus.json").read_text(encoding="utf-8")
    )
    assert prepared_payload["source_root"] == "<external-source-root>"


def test_report_redaction_applies_to_metadata_values_too(tmp_path: Path) -> None:
    request = request_for("valid_pack", tmp_path / "out")
    report = adapter().inspect(request)
    assert report.manifest is not None
    first_row = report.manifest.rows[0].model_copy(
        update={"title": "https://example.invalid/metadata"}
    )
    altered_manifest = report.manifest.model_copy(update={"rows": [first_row]})
    altered_report = report.model_copy(update={"manifest": altered_manifest})

    write_inspection_reports(altered_report, request.output_root)

    content = (request.output_root / "inspection.json").read_text(encoding="utf-8")
    assert "https://example.invalid/metadata" not in content
    assert "<external-url>" in content


def test_markdown_report_is_structure_only(tmp_path: Path) -> None:
    report = adapter().inspect(request_for("valid_pack", tmp_path / "out"))

    markdown = render_inspection_markdown(report)

    assert "Event Corpus Inspection" in markdown
    assert "READY" in markdown
    assert "source HTML and raw paragraphs are excluded" in markdown
    assert "Direct Rule" not in markdown
