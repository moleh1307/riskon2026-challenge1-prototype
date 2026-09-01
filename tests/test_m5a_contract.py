"""M5A contract freeze: lifecycle, Policy CI, and privacy boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M5A_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m5a"

EXPECTED_CASE_IDS = ["M5A-046", "M5A-047", "M5A-048", "M5A-049", "M5A-050"]
EXPECTED_POLICY_CHECKS = [
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
EXPECTED_ROLE_IDS = [
    "SYN-ROLE-LEGAL-EXPERT-001",
    "SYN-ROLE-COMPLIANCE-EXPERT-001",
    "SYN-ROLE-BRM-LEAD-001",
    "SYN-ROLE-KNOWLEDGE-OWNER-001",
    "SYN-ROLE-COMPLIANCE-APPROVER-001",
]
EXPECTED_LIFECYCLE = [
    "PROPOSED",
    "TESTED",
    "AWAITING_APPROVAL",
    "APPROVED",
    "ACTIVE",
    "REJECTED",
    "SUPERSEDED",
    "EXPIRED",
    "ROLLED_BACK",
]


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in iter_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in iter_strings(child)]
    return []


def test_m5a_file_inventory_and_case_ids_are_closed_world() -> None:
    expected = {
        "evaluation_cases.json",
        "lifecycle_policy.json",
        "policy_ci_policy.json",
        "approval_policy.json",
        "knowledge_overlay_policy.json",
        *{f"case_capsules/{case_id}.capsule.json" for case_id in EXPECTED_CASE_IDS},
        *{f"expert_resolutions/{case_id}.resolution.json" for case_id in EXPECTED_CASE_IDS},
        *{f"knowledge_patches/{case_id}.patch.json" for case_id in EXPECTED_CASE_IDS},
        "approvals/M5A-046.approval.json",
        "approvals/M5A-048.rejection.json",
        "approvals/M5A-049.rejection.json",
        "releases/KB-SYN-V1.release.json",
        "releases/KB-SYN-V2.release.json",
    }
    actual = {str(path.relative_to(M5A_ROOT)) for path in M5A_ROOT.rglob("*") if path.is_file()}
    assert actual == expected

    document = load_json(M5A_ROOT / "evaluation_cases.json")
    assert set(document) == {"schema_version", "milestone", "cases"}
    assert document["schema_version"] == "1.0"
    assert document["milestone"] == "M5A_GOVERNED_EVOLUTION_CONTRACT"
    assert [case["id"] for case in document["cases"]] == EXPECTED_CASE_IDS
    assert len({case["id"] for case in document["cases"]}) == 5


def test_m5a_case_references_and_required_fields_are_local() -> None:
    cases = load_json(M5A_ROOT / "evaluation_cases.json")["cases"]
    required = {
        "id",
        "title",
        "case_capsule_ref",
        "expert_resolution_ref",
        "knowledge_patch_ref",
        "approval_ref",
        "pre_patch_decision",
        "expected_policy_ci_checks",
        "expected_patch_status",
        "expected_active_release",
        "expected_post_patch_behaviour",
    }
    reference_fields = {
        "case_capsule_ref",
        "expert_resolution_ref",
        "knowledge_patch_ref",
        "approval_ref",
    }
    for case in cases:
        assert required <= set(case)
        assert "query" not in case
        for field in reference_fields:
            value = case[field]
            assert value is None or value.startswith("local://synthetic-m5a/")
        assert set(case["expected_policy_ci_checks"]) == set(EXPECTED_POLICY_CHECKS)


def test_m5a_policy_ci_and_regression_gate_are_frozen() -> None:
    policy = load_json(M5A_ROOT / "policy_ci_policy.json")
    assert [item["check_id"] for item in policy["mandatory_checks"]] == EXPECTED_POLICY_CHECKS
    assert policy["allowed_statuses"] == ["PASS", "FAIL", "NOT_RUN"]
    assert policy["regression_gate"] == {
        "m0_m3": 28,
        "m4a": 5,
        "m4b": 5,
        "m4c": 2,
        "m4d": 5,
        "total": 45,
    }
    assert policy["activation_rule"] == {
        "all_mandatory_checks": "PASS",
        "human_approval_decision": "APPROVE",
        "approval_actor_differs_from_resolution_author": True,
        "effective_period_valid": True,
        "included_in_knowledge_release": True,
    }
    assert policy["counterfactual_requirements"] == [
        "exact patch scope",
        "alternate region",
        "alternate service model",
        "required context removed",
    ]


def test_m5a_lifecycle_and_approval_policies_forbid_automatic_power() -> None:
    lifecycle = load_json(M5A_ROOT / "lifecycle_policy.json")
    assert lifecycle["lifecycle_states"] == EXPECTED_LIFECYCLE
    assert lifecycle["automatic_approval_allowed"] is False
    assert lifecycle["automatic_activation_allowed"] is False
    assert lifecycle["approval_required_for_activation"] is True
    assert lifecycle["release_required_for_activation"] is True
    assert lifecycle["official_corpus_mutable"] is False

    approval = load_json(M5A_ROOT / "approval_policy.json")
    assert approval["approval_actor_type"] == "HUMAN_ROLE"
    assert approval["self_approval_allowed"] is False
    assert approval["automatic_approval_allowed"] is False
    assert approval["agent_approval_allowed"] is False
    assert approval["activation_without_approval_allowed"] is False
    assert approval["allowed_decisions"] == ["APPROVE", "REJECT"]
    assert approval["synthetic_role_ids"] == EXPECTED_ROLE_IDS
    assert set(approval["approval_authority_roles"]) <= set(EXPECTED_ROLE_IDS)


def test_m5a_overlay_and_release_contracts_are_versioned() -> None:
    overlay = load_json(M5A_ROOT / "knowledge_overlay_policy.json")
    assert overlay["official_corpus_immutable"] is True
    assert overlay["versioned"] is True
    assert overlay["active_selection"]["status"] == "ACTIVE"
    assert overlay["mutation_policy"] == {
        "official_corpus_write_allowed": False,
        "silent_patch_overwrite_allowed": False,
        "rollback_reactivates_old_release": False,
    }
    assert overlay["expiry_policy"]["expired_patch_retrievable"] is False

    v1 = load_json(M5A_ROOT / "releases" / "KB-SYN-V1.release.json")
    v2 = load_json(M5A_ROOT / "releases" / "KB-SYN-V2.release.json")
    assert v1["status"] == "SUPERSEDED"
    assert v2["status"] == "ACTIVE"
    assert v2["previous_release_id"] == v1["release_id"]
    assert v2["patch_ids"] == ["M5A-046-PATCH"]
    assert v1["patch_ids"] == ["M5A-050-PATCH"]


def test_m5a_case_outcomes_encode_all_five_governance_edges() -> None:
    cases = {case["id"]: case for case in load_json(M5A_ROOT / "evaluation_cases.json")["cases"]}
    assert cases["M5A-046"]["expected_patch_status"] == "ACTIVE"
    assert cases["M5A-046"]["expected_active_release"] == "KB-SYN-V2"
    assert len(cases["M5A-046"]["expected_counterfactuals"]) == 4
    assert cases["M5A-047"]["expected_patch_status"] == "AWAITING_APPROVAL"
    assert cases["M5A-047"]["expected_active_release"] is None
    assert cases["M5A-048"]["expected_policy_ci_checks"]["CONTRADICTION_DETECTION"] == "FAIL"
    assert cases["M5A-048"]["expected_policy_ci_checks"]["CRITICAL_CONTROL_PRESERVATION"] == "FAIL"
    assert cases["M5A-049"]["expected_policy_ci_checks"]["SCOPE_CONTAINMENT"] == "FAIL"
    assert cases["M5A-049"]["expected_policy_ci_checks"]["COUNTERFACTUAL_CONTAINMENT"] == "FAIL"
    assert cases["M5A-050"]["expected_patch_status"] == "EXPIRED"
    assert cases["M5A-050"]["expected_active_release"] is None


def test_m5a_fixture_text_has_no_external_or_confidential_material() -> None:
    values: list[str] = []
    for path in M5A_ROOT.rglob("*.json"):
        values.extend(iter_strings(load_json(path)))
    combined = " ".join(values)
    assert "http://" not in combined
    assert "https://" not in combined
    assert "/Users/" not in combined
    assert "@" not in combined
    assert "Bank Julius Baer" not in combined
    assert "eva.somogyi" not in combined
    assert "marc.schmid" not in combined
    assert all(value.startswith("local://synthetic-m5a/") or "://" not in value for value in values)


@pytest.mark.parametrize("case_id", EXPECTED_CASE_IDS)
def test_m5a_every_case_starts_abstained_and_requires_approval(case_id: str) -> None:
    case = next(
        item
        for item in load_json(M5A_ROOT / "evaluation_cases.json")["cases"]
        if item["id"] == case_id
    )
    assert case["pre_patch_decision"] == {
        "decision": "ABSTAIN",
        "reason_codes": ["NO_EXPLICIT_SUPPORT"],
    }
    patch = load_json(M5A_ROOT / case["knowledge_patch_ref"].removeprefix("local://synthetic-m5a/"))
    assert patch["status"] in EXPECTED_LIFECYCLE
    assert patch["approval_ref"] is not None or case_id in {"M5A-047", "M5A-050"}
