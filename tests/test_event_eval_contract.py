"""Contract tests for the event evaluation harness."""

import json
from pathlib import Path

import pytest

from riskon.event_eval.failure_taxonomy import classify_case
from riskon.event_eval.metrics import compute_metrics
from riskon.event_eval.models import (
    EventCaseResult,
    EventExpectedBehavior,
)
from riskon.event_eval.reporting import write_evaluation_reports
from riskon.event_eval.runner import load_event_cases


def _case_payload(count: int) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "suite": "RISKON_CHALLENGE_1",
        "cases": [
            {
                "id": f"CASE-{index:02d}",
                "question": f"Question {index}",
                "input_context": {},
                "expected_behavior": "CLARIFY",
                "expected_source_title_contains": [],
                "required_answer_concepts": [],
                "forbidden_answer_concepts": [],
                "requires_table": False,
                "requires_image": False,
                "requires_manual_review": True,
            }
            for index in range(count)
        ],
    }


def test_event_cases_require_exactly_17(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(_case_payload(16)), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly 17"):
        load_event_cases(cases_path)


def test_event_metrics_and_failure_taxonomy_are_deterministic() -> None:
    result = EventCaseResult(
        case_id="OBS-01",
        question="Which alerts apply?",
        expected_behavior=EventExpectedBehavior.ANSWER,
        requires_table=True,
        requires_manual_review=True,
        actual_decision="ABSTAIN",
        route_present=True,
        behavior_match=False,
        expected_source_title_contains=["Alerts"],
        top_source_titles=["Unrelated page"],
        citation_valid=True,
        latency_ms=10.0,
    )

    assert classify_case(result) == ["DECISION_MISMATCH", "NO_SOURCE_HIT", "UNEXPECTED_ROUTE"]
    metrics = compute_metrics([result])
    assert metrics.cases_executed == 1
    assert metrics.table_required_count == 1
    assert metrics.manual_review_case_count == 1
    assert metrics.median_latency_ms == 10.0


def test_manual_review_report_has_required_review_boxes(tmp_path: Path) -> None:
    result = EventCaseResult(
        case_id="DEV-01",
        question="What triggers the alert?",
        expected_behavior=EventExpectedBehavior.CLARIFY,
        actual_decision="CLARIFY",
        behavior_match=True,
        citation_valid=True,
        reason_codes=["MISSING_REQUIRED_CONTEXT"],
        evidence_excerpts=["Short excerpt"],
        latency_ms=10.0,
    )
    from riskon.event_eval.models import EventEvaluationDocument

    document = EventEvaluationDocument(
        schema_version="1.0",
        suite="RISKON_CHALLENGE_1",
        metrics=compute_metrics([result]),
        case_results=[result],
        network_enabled=False,
        event_data_copied=False,
    )
    paths = write_evaluation_reports(document, tmp_path / "reports")
    review = paths["manual_review"].read_text(encoding="utf-8")

    for label in (
        "Factual correctness",
        "Completeness",
        "Relevance",
        "Scope safety",
        "Critical-control safety",
        "Citation actionability",
    ):
        assert label in review
    assert "MISSING_REQUIRED_CONTEXT" in review
