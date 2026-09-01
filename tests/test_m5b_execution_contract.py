"""M5B execution-contract gate; no production governance code is imported."""

from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M5A_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m5a"
M5B_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m5b"
M5A_CASE_IDS = ["M5A-046", "M5A-047", "M5A-048", "M5A-049", "M5A-050"]
MANDATORY_CHECKS = [
    "EVIDENCE_COMPLETENESS",
    "CLAIM_SUBSET",
    "SCOPE_CONTAINMENT",
    "CONTRADICTION_DETECTION",
    "CRITICAL_CONTROL_PRESERVATION",
    "REFERENCE_RESOLUTION",
    "M0_M4D_REGRESSION",
    "COUNTERFACTUAL_CONTAINMENT",
    "SEPARATION_OF_DUTIES",
    "HUMAN_APPROVAL_PRESENT",
    "EFFECTIVE_PERIOD_VALID",
]
REGRESSION_CONFIGS = [
    "config/milestone0.toml",
    "config/milestone1.toml",
    "config/milestone2.toml",
    "config/milestone3.toml",
    "config/milestone4a.toml",
    "config/milestone4b.toml",
    "config/milestone4c.toml",
    "config/milestone4d.toml",
]
EVENT_TYPES = [
    "PATCH_PROPOSED",
    "POLICY_CI_COMPLETED",
    "PATCH_AWAITING_APPROVAL",
    "HUMAN_DECISION_RECORDED",
    "PATCH_APPROVED",
    "PATCH_REJECTED",
    "RELEASE_CREATED",
    "RELEASE_ACTIVATED",
    "PATCH_EXPIRED",
]
LIFECYCLE_STATES = {
    "PROPOSED",
    "TESTED",
    "AWAITING_APPROVAL",
    "APPROVED",
    "ACTIVE",
    "REJECTED",
    "SUPERSEDED",
    "EXPIRED",
    "ROLLED_BACK",
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def local_m5a(reference: str) -> Path:
    prefix = "local://synthetic-m5a/"
    assert reference.startswith(prefix)
    return M5A_ROOT / reference.removeprefix(prefix)


def m5a_cases() -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in load_json(M5A_ROOT / "evaluation_cases.json")["cases"]}


def iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in iter_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in iter_strings(child)]
    return []


def test_m5b_contract_file_inventory_is_closed_world() -> None:
    expected = {
        "execution_policy.json",
        "claim_relations.json",
        "regression_suites.json",
        "overlay_evaluation_cases.json",
        "release_activation_requests.json",
    }
    actual = {path.name for path in M5B_ROOT.glob("*.json") if path.is_file()}
    assert actual == expected


def test_m5b_execution_policy_has_exact_contract_shape() -> None:
    policy = load_json(M5B_ROOT / "execution_policy.json")
    assert set(policy) == {
        "schema_version",
        "contract_ref",
        "policy_ci_phases",
        "mandatory_checks",
        "lifecycle_transitions",
        "overlay_policy",
        "event_store_policy",
    }
    assert policy["schema_version"] == "1.0"
    assert policy["contract_ref"] == "local://synthetic-m5a/evaluation-cases.json"
    assert [item["phase"] for item in policy["policy_ci_phases"]] == [
        "PRE_APPROVAL",
        "ACTIVATION",
        "CURRENT_STATE",
    ]
    assert policy["mandatory_checks"] == MANDATORY_CHECKS
    assert policy["overlay_policy"]["official_corpus_immutable"] is True
    assert policy["overlay_policy"]["special_ranking_boost"] is False
    assert policy["overlay_policy"]["expert_resolution_is_evidence_unit"] is False
    assert policy["event_store_policy"]["path"] == "data/generated/m5b/governance_events.jsonl"
    assert policy["event_store_policy"]["append_only"] is True
    assert policy["event_store_policy"]["update_allowed"] is False
    assert policy["event_store_policy"]["delete_allowed"] is False
    assert policy["event_store_policy"]["allowed_event_types"] == EVENT_TYPES


def test_m5b_lifecycle_transitions_preserve_approval_and_activation_gates() -> None:
    transitions = load_json(M5B_ROOT / "execution_policy.json")["lifecycle_transitions"]
    pairs = {(item["from"], item["to"]): item["requirement"] for item in transitions}
    assert pairs == {
        ("PROPOSED", "TESTED"): "PRE_APPROVAL_POLICY_CI",
        ("TESTED", "AWAITING_APPROVAL"): "AUTOMATED_CHECKS_PASS",
        ("AWAITING_APPROVAL", "APPROVED"): "VALID_HUMAN_APPROVAL",
        ("APPROVED", "ACTIVE"): "EXPLICIT_RELEASE_ACTIVATION",
        ("TESTED", "REJECTED"): "MANDATORY_CHECK_FAIL",
        ("AWAITING_APPROVAL", "REJECTED"): "HUMAN_REJECTION",
        ("ACTIVE", "EXPIRED"): "EFFECTIVE_TO_REACHED",
    }
    forbidden = {
        ("PROPOSED", "ACTIVE"),
        ("TESTED", "ACTIVE"),
        ("AWAITING_APPROVAL", "ACTIVE"),
        ("REJECTED", "APPROVED"),
        ("REJECTED", "ACTIVE"),
        ("EXPIRED", "ACTIVE"),
    }
    assert forbidden.isdisjoint(pairs)
    assert {state for pair in pairs for state in pair} <= LIFECYCLE_STATES


def test_m5b_config_is_local_only_and_points_to_m4d_and_m5b_contracts() -> None:
    raw = tomllib.loads((PROJECT_ROOT / "config" / "milestone5b.toml").read_text())
    assert set(raw) == {"base", "governance", "evaluation", "security"}
    assert raw["base"] == {"config": "config/milestone4d.toml"}
    governance = raw["governance"]
    assert governance["contract_cases"] == "data/synthetic/m5a/evaluation_cases.json"
    assert governance["generated_root"] == "data/generated/m5b"
    assert governance["official_corpus_mutation_enabled"] is False
    assert governance["automatic_approval_enabled"] is False
    assert governance["automatic_activation_enabled"] is False
    assert governance["agent_approval_enabled"] is False
    assert governance["self_approval_enabled"] is False
    assert governance["overlay"] == {
        "provenance_prefix": "local://knowledge-overlay/",
        "special_ranking_boost": False,
        "include_expired_patches": False,
        "include_rejected_patches": False,
        "include_awaiting_approval_patches": False,
    }
    assert governance["policy_ci"] == {
        "required_regression_passes": 45,
        "counterfactual_routing_enabled": False,
        "recursive_policy_ci_enabled": False,
    }
    assert raw["evaluation"] == {
        "included_cases": M5A_CASE_IDS,
        "expected_cases": 5,
        "expected_active_patches": 1,
        "expected_awaiting_approval": 1,
        "expected_rejected_patches": 2,
        "expected_expired_patches": 1,
        "expected_post_patch_transitions": 4,
    }
    assert raw["security"] == {
        "network_enabled": False,
        "external_api_enabled": False,
        "telemetry_enabled": False,
    }
    assert all("http://" not in value and "https://" not in value for value in iter_strings(raw))


def test_m5b_reuses_frozen_m5a_cases_claims_scopes_and_patch_ids() -> None:
    frozen = m5a_cases()
    assert list(frozen) == M5A_CASE_IDS
    overlay_cases = load_json(M5B_ROOT / "overlay_evaluation_cases.json")["cases"]
    assert [item["case_id"] for item in overlay_cases] == M5A_CASE_IDS
    for item in overlay_cases:
        frozen_case = frozen[item["case_id"]]
        assert item["patch_ref"] == frozen_case["knowledge_patch_ref"]
        patch = load_json(local_m5a(item["patch_ref"]))
        resolution = load_json(local_m5a(frozen_case["expert_resolution_ref"]))
        assert patch["source_resolution_id"] == resolution["resolution_id"]
        assert {claim["claim_id"] for claim in patch["claims"]} <= {
            claim["claim_id"] for claim in resolution["claims"]
        }
        assert set(patch["scope"]) == {
            "regions",
            "jurisdictions",
            "service_models",
            "solicitation_types",
            "workflow_stages",
            "client_classifications",
            "systems",
        }


def test_m5b_claim_relations_use_only_frozen_claim_ids_and_no_case_branching() -> None:
    claim_ids: set[str] = set()
    for case in m5a_cases().values():
        resolution = load_json(local_m5a(case["expert_resolution_ref"]))
        claim_ids.update(claim["claim_id"] for claim in resolution["claims"])
    relations = load_json(M5B_ROOT / "claim_relations.json")["relations"]
    assert relations
    for relation in relations:
        assert relation["left_claim_id"] in claim_ids
        assert relation["right_claim_id"] in claim_ids
        assert relation["relation"] in {"SUPPORTS", "CONTRADICTS", "SUPERSEDES"}
        assert relation["evidence_refs"]
        assert all(ref.startswith("local://") for ref in relation["evidence_refs"])
        assert not any(case_id in json.dumps(relation) for case_id in M5A_CASE_IDS)


def test_m5b_regression_suite_is_in_process_and_exactly_45() -> None:
    suites = load_json(M5B_ROOT / "regression_suites.json")
    assert suites["schema_version"] == "1.0"
    assert suites["suite_configs"] == REGRESSION_CONFIGS
    assert suites["expected_aggregate"] == 45
    assert suites["execution_mode"] == "IN_PROCESS_EXISTING_EVALUATORS"
    assert suites["subprocess_execution_allowed"] is False


def test_m5b_overlay_cases_have_four_exact_m5a_046_transitions() -> None:
    cases = load_json(M5B_ROOT / "overlay_evaluation_cases.json")["cases"]
    first = cases[0]
    assert first["case_id"] == "M5A-046"
    assert [item["snapshot_id"] for item in first["queries"]] == [
        "M5A-046-exact-scope",
        "M5A-046-alternate-region",
        "M5A-046-alternate-service-model",
        "M5A-046-required-context-removed",
    ]
    assert [item["expected_decision"] for item in first["queries"]] == [
        "ANSWER",
        "ABSTAIN",
        "ABSTAIN",
        "CLARIFY",
    ]
    assert first["queries"][0]["expected_overlay_claim_ids"] == ["meridian_beta_basic_applies"]
    for item in first["queries"]:
        query_input = item["query_input"]
        assert set(query_input) == {"query", "context"}
        assert query_input["query"]
        assert isinstance(query_input["context"], dict)


def test_m5b_non_active_cases_have_minimum_non_retrieval_probes() -> None:
    cases = load_json(M5B_ROOT / "overlay_evaluation_cases.json")["cases"]
    for item in cases[1:]:
        assert len(item["queries"]) == 1
        query = item["queries"][0]
        assert query["expected_decision"] == "ABSTAIN"
        assert query["expected_overlay_claim_ids"] == []
        assert query["query_input"]["query"]


def test_m5b_release_requests_cover_all_five_governance_outcomes() -> None:
    requests = load_json(M5B_ROOT / "release_activation_requests.json")["requests"]
    assert [item["case_id"] for item in requests] == M5A_CASE_IDS
    assert [item["expected_outcome"] for item in requests] == [
        "ACTIVE",
        "BLOCKED_NO_APPROVAL",
        "BLOCKED_POLICY_CI",
        "BLOCKED_POLICY_CI",
        "BLOCKED_EXPIRED",
    ]
    assert len({item["request_id"] for item in requests}) == 5
    for item in requests:
        parsed = datetime.fromisoformat(item["requested_at_utc"].replace("Z", "+00:00"))
        assert parsed.tzinfo is UTC
        assert item["requested_by_role_id"] == "SYN-ROLE-KNOWLEDGE-OWNER-001"
        assert item["patch_id"] == f"{item['case_id']}-PATCH"


def test_m5b_fixture_data_contains_no_external_or_confidential_material() -> None:
    values: list[str] = []
    for path in M5B_ROOT.glob("*.json"):
        payload = load_json(path)
        values.extend(iter_strings(payload))
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text
        assert "https://" not in text
        assert "/Users/" not in text
        assert "@" not in text
        assert "Bank Julius Baer" not in text
        assert "employee" not in text.lower()
    assert all("://" not in value or value.startswith("local://") for value in values)


@pytest.mark.parametrize("case_id", M5A_CASE_IDS)
def test_m5b_overlay_case_binds_to_existing_m5a_patch(case_id: str) -> None:
    case = next(
        item
        for item in load_json(M5B_ROOT / "overlay_evaluation_cases.json")["cases"]
        if item["case_id"] == case_id
    )
    assert case["patch_ref"] == m5a_cases()[case_id]["knowledge_patch_ref"]
    patch = load_json(local_m5a(case["patch_ref"]))
    assert patch["patch_id"] == f"{case_id}-PATCH"
