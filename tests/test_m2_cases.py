"""One acceptance test per frozen M2 scenario."""

import json
from pathlib import Path

import pytest

from riskon.models import QueryInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = PROJECT_ROOT / "data" / "synthetic" / "m2" / "evaluation_cases.json"


def _case(case_id: str) -> dict[str, object]:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    return next(case for case in payload["cases"] if case["id"] == case_id)


@pytest.mark.parametrize("case_id", [f"M2-{number:03d}" for number in range(13, 21)])
def test_frozen_case_matches_exact_expected_fields(m2_pipeline, case_id: str) -> None:
    case = _case(case_id)
    planned = m2_pipeline.run_planned(
        QueryInput(query=case["query"], context=case["input_context"])
    )
    plan = planned.query_plan
    expected_plan = case["expected_plan"]
    assert plan.intent.value == expected_plan["intent"]
    assert plan.normalised_query == expected_plan["normalised_query"]
    assert plan.canonical_terms == expected_plan["canonical_terms"]
    assert plan.required_context_fields == expected_plan["required_context_fields"]
    assert plan.missing_context_fields == expected_plan["missing_context_fields"]
    assert plan.subqueries == expected_plan["subqueries"]
    assert [channel.value for channel in plan.retrieval_channels] == expected_plan[
        "retrieval_channels"
    ]
    assert plan.retrieval_skipped == expected_plan["retrieval_skipped"]

    result = planned.verified_run.result
    expected_result = case["expected_result"]
    assert result.decision.value == expected_result["decision"]
    assert [reason.value for reason in result.reason_codes] == expected_result["reason_codes"]
    assert result.clarifying_question == expected_result["clarifying_question"]
    supported = set(planned.verified_run.verification.supported_claim_ids)
    assert set(expected_result["required_claim_ids"]).issubset(supported)
    assert not supported & set(expected_result["forbidden_claim_ids"])
    assert result.route is None

    retrieval = case["expected_retrieval"]
    subqueries = [] if plan.retrieval_skipped else plan.subqueries or [plan.normalised_query]
    actual_top1 = []
    actual_final = []
    actual_top5 = []
    for subquery in subqueries:
        entries = {
            entry.candidate_ref: entry
            for entry in planned.retrieval_diagnostics.entries
            if entry.subquery == subquery and entry.included
        }
        ordered = sorted(entries.values(), key=lambda entry: entry.final_rank or 10**9)
        actual_top1.append(ordered[0].candidate_ref)
        actual_final.extend(entry.candidate_ref for entry in ordered)
        actual_top5.extend(entry.candidate_ref for entry in ordered[:5])
    assert actual_top1 == retrieval["expected_top1_refs"]
    assert set(retrieval["required_refs_at_k"]).issubset(set(actual_top5))
