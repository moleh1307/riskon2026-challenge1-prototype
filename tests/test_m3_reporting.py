"""M3 report and CLI acceptance tests."""

import json
from pathlib import Path

from riskon.cli import evaluate
from riskon.evaluation import M3EvaluationDocument, M3Evaluator
from riskon.reporting import render_m3_markdown, write_m3_reports

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_m3_json_markdown_and_diagnostics_are_written(m3_config) -> None:
    document = M3Evaluator(m3_config).run()
    json_path, markdown_path = write_m3_reports(document, m3_config.generated_root)
    loaded = M3EvaluationDocument.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert loaded.metrics.m3_case_match_rate == 1.0
    markdown = markdown_path.read_text(encoding="utf-8")
    rendered = render_m3_markdown(document)
    assert markdown == rendered
    assert "M3-023" in markdown
    for name in type(loaded.metrics).model_fields:
        assert name in markdown
    diagnostics = [
        json.loads(line)
        for line in (m3_config.generated_root / "routing_diagnostics.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(diagnostics) == 8
    assert all("scenario_id" in item and "routing_request" in item for item in diagnostics)
    assert "/Users/" not in json.dumps(loaded.model_dump(mode="json"))


def test_canonical_m3_cli_prints_exact_pass_line(capsys) -> None:
    exit_code = evaluate(PROJECT_ROOT / "config" / "milestone3.toml")
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == (
        "M3 PASS: aggregate 28/28; M0 5/5; M1-new 7/7; M2-new 8/8; "
        "M3-new 8/8; support functions 8/8; person-or-queue 8/8; "
        "hot-swap 1/1; hard-constraint violations 0; network disabled."
    )
    report_path = PROJECT_ROOT / "data" / "generated" / "m3" / "evaluation.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["metrics"]["support_model_hot_swap_accuracy"] == 1.0
    assert (PROJECT_ROOT / "data" / "generated" / "m3" / "evaluation.md").is_file()
    assert (PROJECT_ROOT / "data" / "generated" / "m3" / "routing_diagnostics.jsonl").is_file()
