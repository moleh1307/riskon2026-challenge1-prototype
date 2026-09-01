"""M1 report schema, content, and failure diagnostics."""

import json
from pathlib import Path

from riskon.cli import evaluate
from riskon.evaluation import M1EvaluationDocument, M1Evaluator, M1Metrics, ScenarioResult
from riskon.reporting import render_markdown, write_reports

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_json_and_markdown_reports_are_written_and_schema_valid(m1_config) -> None:
    document = M1Evaluator(m1_config).run()
    json_path, markdown_path = write_reports(document, m1_config.generated_root)
    loaded = M1EvaluationDocument.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert loaded.metrics.scenario_match_rate == 1.0
    markdown = markdown_path.read_text(encoding="utf-8")
    for name in type(loaded.metrics).model_fields:
        assert name in markdown
    assert "M1-006" in markdown
    assert "M1-012" in markdown


def test_failure_rendering_keeps_scenario_field_expected_and_actual() -> None:
    failure = "M1-008: required_claim_ids expected=['do_not_proceed'] actual=[]"
    scenario = ScenarioResult(
        id="M1-008",
        matched=False,
        failures=[failure],
        expected_decision="ANSWER",
        actual_decision="ABSTAIN",
        expected_reason_codes=[],
        actual_reason_codes=["UNSUPPORTED_CLAIM"],
        required_claim_ids=["do_not_proceed"],
        supported_claim_ids=[],
        forbidden_claim_ids=[],
        required_evidence_refs=[],
        actual_evidence_refs=[],
        expected_route=None,
        actual_route=None,
        result={},
    )
    document = M1EvaluationDocument(
        schema_version="1.0",
        metrics=M1Metrics(
            scenario_match_rate=0.0,
            decision_accuracy=0.0,
            clarification_accuracy=1.0,
            answer_case_claim_recall=0.0,
            critical_claim_recall=0.0,
            citation_validity=1.0,
            route_function_accuracy=1.0,
            route_expert_accuracy=1.0,
            correct_abstention_rate=1.0,
            unnecessary_abstention_rate=1.0,
            scope_violation_count=0,
            unsupported_claim_count=1,
            unresolved_reference_false_negative_count=0,
            network_violation_count=0,
        ),
        m0_regression={"expected": 5, "matched": 0},
        scenario_results=[scenario],
        network_enabled=False,
        audit_schema_valid=True,
    )
    rendered = render_markdown(document)
    assert "M1-008" in rendered
    assert "required_claim_ids" in rendered
    assert "expected=['do_not_proceed']" in rendered
    assert "actual=[]" in rendered


def test_reports_contain_no_absolute_paths_or_http_urls(m1_config) -> None:
    document = M1Evaluator(m1_config).run()
    json_text = json.dumps(document.model_dump(mode="json"))
    markdown = render_markdown(document)
    assert "/Users/" not in json_text + markdown
    assert "http://" not in json_text + markdown
    assert "https://" not in json_text + markdown


def test_canonical_m1_cli_prints_exact_pass_line(capsys) -> None:
    exit_code = evaluate(PROJECT_ROOT / "config" / "milestone1.toml")
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == (
        "M1 PASS: 12/12 scenarios matched; M0 regression 5/5; "
        "claim support valid; network disabled."
    )
