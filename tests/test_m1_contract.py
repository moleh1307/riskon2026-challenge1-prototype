"""Freeze the M1 evaluation contract before production code changes."""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "data" / "synthetic" / "m1" / "evaluation_cases.json"
ALLOWED_DECISIONS = {"ANSWER", "CLARIFY", "ABSTAIN"}
ALLOWED_REASONS = {
    "AMBIGUOUS_ACRONYM",
    "NO_EXPLICIT_SUPPORT",
    "UNRESOLVED_REQUIRED_REFERENCE",
    "UNSUPPORTED_MODALITY",
    "APPROVAL_REQUIRED",
}
REQUIRED_FIELDS = {
    "id",
    "query",
    "input_context",
    "expected_decision",
    "expected_reason_codes",
    "expected_clarifying_question",
    "required_claim_ids",
    "forbidden_claim_ids",
    "required_evidence_refs",
    "expected_route",
}


@pytest.fixture(scope="module")
def cases() -> list[dict[str, object]]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    return payload["cases"]


def test_contract_contains_exactly_seven_cases(cases: list[dict[str, object]]) -> None:
    assert [case["id"] for case in cases] == [f"M1-{number:03d}" for number in range(6, 13)]
    assert len({case["id"] for case in cases}) == 7


def test_contract_fields_and_values_are_closed_world(cases: list[dict[str, object]]) -> None:
    for case in cases:
        assert set(case) == REQUIRED_FIELDS
        assert case["expected_decision"] in ALLOWED_DECISIONS
        assert set(case["expected_reason_codes"]) <= ALLOWED_REASONS
        assert isinstance(case["input_context"], dict)
        assert isinstance(case["required_claim_ids"], list)
        assert isinstance(case["forbidden_claim_ids"], list)
        for ref in case["required_evidence_refs"]:
            assert ref.startswith("local://synthetic-m1/")
            assert "http://" not in ref and "https://" not in ref
            assert not Path(ref).is_absolute()
        assert "/Users/" not in json.dumps(case)
        assert "Julius Baer" not in json.dumps(case)


def test_contract_has_exact_decision_specific_expectations(cases: list[dict[str, object]]) -> None:
    by_id = {case["id"]: case for case in cases}
    assert by_id["M1-006"]["expected_clarifying_question"] == (
        "Do you mean Advisory Review Code or Account Routing Console?"
    )
    assert by_id["M1-008"]["required_claim_ids"] == [
        "do_not_proceed",
        "client_acceptance_does_not_override",
    ]
    assert by_id["M1-011"]["forbidden_claim_ids"] == ["unrelated_solicitation_process"]
    assert by_id["M1-007"]["expected_route"] == {
        "support_function": "SUITABILITY_EXPERT_LEGAL",
        "expert_id": "SYN-LEGAL-001",
    }
    assert by_id["M1-009"]["expected_route"] == {
        "support_function": "BUSINESS_FRONT_SUPPORT",
        "expert_id": "SYN-BFS-001",
    }
    assert by_id["M1-010"]["expected_route"] == {
        "support_function": "BRM_SUITABILITY_LEAD",
        "expert_id": None,
    }
    assert by_id["M1-012"]["expected_route"] == {
        "support_function": "SUITABILITY_EXPERT_COMPLIANCE",
        "expert_id": "SYN-COMPLIANCE-001",
    }


def test_contract_rejects_unexpected_reason_code_if_added() -> None:
    assert "SCOPE_MISMATCH" not in ALLOWED_REASONS
    assert "TECHNICAL_FAILURE" not in ALLOWED_REASONS
    with pytest.raises(AssertionError):
        assert "UNEXPECTED" in ALLOWED_REASONS
