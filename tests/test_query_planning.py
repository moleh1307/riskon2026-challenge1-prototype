"""M2 planner, alias, context, and decomposition contract tests."""

import json
from pathlib import Path

from riskon.models import QueryInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = PROJECT_ROOT / "data" / "synthetic" / "m2" / "evaluation_cases.json"


def _cases() -> list[dict[str, object]]:
    return json.loads(CASE_PATH.read_text(encoding="utf-8"))["cases"]


def test_all_frozen_plans_match_the_contract(m2_pipeline) -> None:
    for case in _cases():
        request = QueryInput(query=case["query"], context=case["input_context"])
        actual = m2_pipeline._m2_planner.plan(request).model_dump(mode="json")
        expected = case["expected_plan"]
        assert actual["intent"] == expected["intent"]
        assert actual["normalised_query"] == expected["normalised_query"]
        assert actual["canonical_terms"] == expected["canonical_terms"]
        assert actual["required_context_fields"] == expected["required_context_fields"]
        assert actual["missing_context_fields"] == expected["missing_context_fields"]
        assert actual["subqueries"] == expected["subqueries"]
        assert actual["retrieval_channels"] == expected["retrieval_channels"]
        assert actual["retrieval_skipped"] == expected["retrieval_skipped"]


def test_m2_017_short_circuits_before_retrieval(m2_pipeline) -> None:
    case = next(case for case in _cases() if case["id"] == "M2-017")
    planned = m2_pipeline.run_planned(
        QueryInput(query=case["query"], context=case["input_context"])
    )
    assert planned.query_plan.retrieval_skipped is True
    assert planned.retrieval_diagnostics.entries == []
    assert planned.verified_run.result.decision.value == "CLARIFY"


def test_decomposition_is_limited_to_explicit_conjunctions(m2_pipeline) -> None:
    case = next(case for case in _cases() if case["id"] == "M2-019")
    plan = m2_pipeline._m2_planner.plan(
        QueryInput(query=case["query"], context=case["input_context"])
    )
    assert plan.subqueries == [
        "What are the eligibility conditions?",
        "Where is the application form?",
    ]
    assert len(plan.subqueries) <= 3


def test_same_query_and_context_have_same_plan(m2_pipeline) -> None:
    case = next(case for case in _cases() if case["id"] == "M2-013")
    request = QueryInput(query=case["query"], context=case["input_context"])
    first = m2_pipeline._m2_planner.plan(request)
    second = m2_pipeline._m2_planner.plan(request)
    assert first == second
