"""M2 aggregate regression, report, and determinism tests."""

import json
from pathlib import Path

from riskon.cli import evaluate
from riskon.evaluation import M2Evaluator
from riskon.models import QueryInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_m2_evaluator_meets_all_acceptance_metrics(m2_config) -> None:
    document = M2Evaluator(m2_config).run()
    assert document.m0_regression == {"expected": 5, "matched": 5}
    assert document.m1_regression == {"expected": 7, "matched": 7}
    metrics = document.metrics
    assert metrics.m2_case_match_rate == 1.0
    assert metrics.query_plan_accuracy == 1.0
    assert metrics.retrieval_top1_accuracy == 1.0
    assert metrics.required_evidence_recall_at_5 == 1.0
    assert metrics.subquery_coverage == 1.0
    assert metrics.table_row_recall == 1.0
    assert metrics.clarification_short_circuit_accuracy == 1.0
    assert metrics.forbidden_evidence_count == 0
    assert metrics.context_filter_violation_count == 0
    assert metrics.unsupported_claim_count == 0
    assert metrics.network_violation_count == 0


def test_m2_rerun_has_identical_plans_diagnostics_and_results(m2_pipeline) -> None:
    query = QueryInput(
        query="Which session alerts are active for Advisory Location Alpha and a Premium mandate?",
        context={"location": "ALPHA", "mandate": "PREMIUM"},
    )
    first = m2_pipeline.run_planned(query)
    second = m2_pipeline.run_planned(query)
    assert first.query_plan == second.query_plan
    assert first.retrieval_diagnostics == second.retrieval_diagnostics
    assert first.verified_run.result.model_dump(
        mode="json", exclude={"trace_id"}
    ) == second.verified_run.result.model_dump(mode="json", exclude={"trace_id"})


def test_unanswerable_query_abstains_without_speculative_claims(m2_pipeline) -> None:
    planned = m2_pipeline.run_planned(QueryInput(query="zebra quantum telescope"))
    assert planned.verified_run.result.decision.value == "ABSTAIN"
    assert planned.verified_run.result.answer is None
    assert planned.verified_run.verification.supported_claim_ids == []
    assert planned.verified_run.result.route is not None


def test_m2_cli_writes_reports_and_exact_pass_line(capsys) -> None:
    exit_code = evaluate(PROJECT_ROOT / "config" / "milestone2.toml")
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == (
        "M2 PASS: aggregate 20/20; M0 5/5; M1-new 7/7; M2-new 8/8; "
        "query plans 8/8; evidence recall@5 1.000; context violations 0; "
        "network disabled."
    )
    report_path = PROJECT_ROOT / "data" / "generated" / "m2" / "evaluation.json"
    report = json.loads(report_path.read_text())
    assert "m2_case_match_rate" in report["metrics"]
    assert (PROJECT_ROOT / "data" / "generated" / "m2" / "evaluation.md").is_file()
    assert (PROJECT_ROOT / "data" / "generated" / "m2" / "retrieval_diagnostics.jsonl").is_file()
