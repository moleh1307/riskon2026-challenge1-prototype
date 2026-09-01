"""M5B JSON/Markdown report contract."""

import json

from m5b_helpers import config

from riskon.m5b_evaluation import M5BEvaluator
from riskon.reporting import render_m5b_markdown, write_m5b_reports


def test_m5b_report_writer_returns_canonical_paths(tmp_path) -> None:
    document = M5BEvaluator(config()).run()
    json_path, markdown_path = write_m5b_reports(document, tmp_path / "reports")
    assert json_path == tmp_path / "reports" / "evaluation.json"
    assert markdown_path == tmp_path / "reports" / "evaluation.md"
    assert json.loads(json_path.read_text(encoding="utf-8"))["schema_version"] == "1.0"
    assert markdown_path.read_text(encoding="utf-8").startswith("# M5B Evaluation Report")


def test_m5b_markdown_contains_architecture_statement_metrics_and_boundary(tmp_path) -> None:
    document = M5BEvaluator(config()).run()
    rendered = render_m5b_markdown(document)
    assert "M5B does not train or fine-tune a model from expert conversations." in rendered
    assert "It converts structured expert resolutions into proposed knowledge" in rendered
    assert "mandatory Policy CI checks" in rendered
    assert "## Metrics" in rendered
    assert "## Governance boundary" in rendered
    assert "automatic activation" in rendered
    assert rendered.endswith("\n")


def test_m5b_markdown_reports_all_case_statuses() -> None:
    document = M5BEvaluator(config()).run()
    rendered = render_m5b_markdown(document)
    for case_id in ("M5A-046", "M5A-047", "M5A-048", "M5A-049", "M5A-050"):
        assert f"### {case_id} — PASS" in rendered
