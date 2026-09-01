"""Freeze the M2 evaluation contract before production code changes."""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "data" / "synthetic" / "m2" / "evaluation_cases.json"
ALIASES_PATH = PROJECT_ROOT / "data" / "synthetic" / "m2" / "aliases.json"
ALLOWED_INTENTS = {
    "DEFINITION",
    "APPLICABILITY",
    "PROCEDURE",
    "ALERT_RESOLUTION",
    "CONFIGURATION_LOOKUP",
    "REFERENCE_LOOKUP",
}
ALLOWED_CHANNELS = {"EXACT", "WORD_TFIDF", "CHAR_TFIDF", "TABLE_ROW"}
ALLOWED_DECISIONS = {"ANSWER", "CLARIFY", "ABSTAIN"}
ALLOWED_REASONS = {"MISSING_REQUIRED_CONTEXT"}
REQUIRED_CASE_FIELDS = {
    "id",
    "query",
    "input_context",
    "expected_plan",
    "expected_retrieval",
    "expected_result",
}
REQUIRED_PLAN_FIELDS = {
    "intent",
    "normalised_query",
    "canonical_terms",
    "required_context_fields",
    "missing_context_fields",
    "subqueries",
    "retrieval_channels",
    "retrieval_skipped",
}
REQUIRED_RETRIEVAL_FIELDS = {
    "expected_top1_refs",
    "required_refs_at_k",
    "forbidden_refs",
    "required_table_row_refs",
    "forbidden_table_row_refs",
}
REQUIRED_RESULT_FIELDS = {
    "decision",
    "reason_codes",
    "clarifying_question",
    "required_claim_ids",
    "forbidden_claim_ids",
    "expected_route",
}


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cases() -> list[dict[str, object]]:
    payload = _load_json(CONTRACT_PATH)
    assert payload["schema_version"] == "1.0"
    value = payload["cases"]
    assert isinstance(value, list)
    return value


def _all_refs(case: dict[str, object]) -> list[str]:
    retrieval = case["expected_retrieval"]
    assert isinstance(retrieval, dict)
    refs: list[str] = []
    for key in REQUIRED_RETRIEVAL_FIELDS:
        value = retrieval[key]
        assert isinstance(value, list)
        refs.extend(str(item) for item in value)
    return refs


def test_contract_contains_exactly_eight_cases(cases: list[dict[str, object]]) -> None:
    assert [case["id"] for case in cases] == [f"M2-{number:03d}" for number in range(13, 21)]
    assert len({case["id"] for case in cases}) == 8


def test_contract_fields_and_values_are_closed_world(
    cases: list[dict[str, object]],
) -> None:
    for case in cases:
        assert set(case) == REQUIRED_CASE_FIELDS
        assert isinstance(case["input_context"], dict)

        plan = case["expected_plan"]
        assert isinstance(plan, dict)
        assert set(plan) == REQUIRED_PLAN_FIELDS
        assert plan["intent"] in ALLOWED_INTENTS
        assert set(plan["retrieval_channels"]) <= ALLOWED_CHANNELS
        assert isinstance(plan["retrieval_skipped"], bool)

        retrieval = case["expected_retrieval"]
        assert isinstance(retrieval, dict)
        assert set(retrieval) == REQUIRED_RETRIEVAL_FIELDS
        for ref in _all_refs(case):
            assert ref.startswith("local://synthetic-m2/")
            assert "http://" not in ref and "https://" not in ref
            assert not Path(ref).is_absolute()

        result = case["expected_result"]
        assert isinstance(result, dict)
        assert set(result) == REQUIRED_RESULT_FIELDS
        assert result["decision"] in ALLOWED_DECISIONS
        assert set(result["reason_codes"]) <= ALLOWED_REASONS
        assert isinstance(result["required_claim_ids"], list)
        assert isinstance(result["forbidden_claim_ids"], list)

        serialised = json.dumps(case)
        assert "/Users/" not in serialised
        assert "Julius Baer" not in serialised
        assert "juliusbaer" not in serialised.lower()
        assert "@" not in serialised


def test_contract_has_exact_decision_specific_expectations(
    cases: list[dict[str, object]],
) -> None:
    by_id = {str(case["id"]): case for case in cases}
    assert by_id["M2-017"]["expected_plan"]["retrieval_skipped"] is True
    assert by_id["M2-017"]["expected_plan"]["missing_context_fields"] == ["workflow_stage"]
    assert by_id["M2-017"]["expected_result"]["clarifying_question"] == (
        "Did the alert arise during an interactive session or during overnight monitoring?"
    )

    m2016_retrieval = by_id["M2-016"]["expected_retrieval"]
    assert len(m2016_retrieval["required_table_row_refs"]) == 3
    assert len(m2016_retrieval["forbidden_table_row_refs"]) == 2
    assert by_id["M2-016"]["expected_result"]["required_claim_ids"] == [
        "atlas_alert_active",
        "beacon_alert_active",
        "cedar_alert_active",
    ]
    assert by_id["M2-019"]["expected_plan"]["subqueries"] == [
        "What are the eligibility conditions?",
        "Where is the application form?",
    ]
    assert by_id["M2-019"]["expected_retrieval"]["required_refs_at_k"][-1] == (
        "local://synthetic-m2/attachments/tier-election-form.txt"
    )
    assert by_id["M2-020"]["expected_result"]["forbidden_claim_ids"] == ["reverse_request_workflow"]


def test_alias_registry_is_closed_world() -> None:
    payload = _load_json(ALIASES_PATH)
    assert payload["schema_version"] == "1.0"
    aliases = payload["aliases"]
    assert isinstance(aliases, list)
    assert len(aliases) == 3
    assert {item["kind"] for item in aliases} == {
        "DECLARED_TYPO",
        "DECLARED_ACRONYM",
        "DECLARED_SYNONYM",
    }
    assert aliases[0] == {
        "canonical": "emitter density alert",
        "variants": ["emmiter density alert"],
        "kind": "DECLARED_TYPO",
    }
    assert aliases[1] == {
        "canonical": "advisory review code",
        "variants": ["ARC"],
        "kind": "DECLARED_ACRONYM",
    }
    assert aliases[2]["canonical"] == "client tier election process"
    serialised = json.dumps(payload)
    assert "/Users/" not in serialised
    assert "http://" not in serialised
    assert "https://" not in serialised


def test_contract_rejects_unexpected_channel_or_reason() -> None:
    assert "FUZZY" not in ALLOWED_CHANNELS
    assert "TECHNICAL_FAILURE" not in ALLOWED_REASONS
    with pytest.raises(AssertionError):
        assert "UNEXPECTED" in ALLOWED_CHANNELS
