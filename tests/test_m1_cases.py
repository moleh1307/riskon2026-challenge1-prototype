"""One acceptance test per frozen M1 scenario."""

import json
from pathlib import Path

import pytest

from riskon.models import QueryInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = PROJECT_ROOT / "data" / "synthetic" / "m1" / "evaluation_cases.json"


def _case(case_id: str) -> dict[str, object]:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    return next(case for case in payload["cases"] if case["id"] == case_id)


@pytest.mark.parametrize("case_id", [f"M1-{number:03d}" for number in range(6, 13)])
def test_frozen_case_matches_exact_expected_fields(m1_pipeline, case_id: str) -> None:
    case = _case(case_id)
    verified = m1_pipeline.run_verified(
        QueryInput(query=case["query"], context=case["input_context"])
    )
    result = verified.result
    report = verified.verification
    assert result.decision.value == case["expected_decision"]
    assert [reason.value for reason in result.reason_codes] == case["expected_reason_codes"]
    assert result.clarifying_question == case["expected_clarifying_question"]
    assert set(case["required_claim_ids"]).issubset(report.supported_claim_ids)
    assert not set(case["forbidden_claim_ids"]) & set(report.supported_claim_ids)
    assert set(case["required_evidence_refs"]).issubset(report.evidence_refs)
    expected_route = case["expected_route"]
    actual_route = result.route.model_dump(mode="json") if result.route else None
    if expected_route is None:
        assert actual_route is None
    else:
        assert actual_route is not None
        assert actual_route["support_function"] == expected_route["support_function"]
        assert actual_route["expert_id"] == expected_route["expert_id"]
