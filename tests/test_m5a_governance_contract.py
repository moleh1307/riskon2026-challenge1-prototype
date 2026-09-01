"""M5A governance invariants without implementing production activation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M5A_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m5a"
REFERENCE_TIME = datetime(2026, 8, 27, tzinfo=UTC)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def case(case_id: str) -> dict[str, Any]:
    return next(
        item
        for item in load_json(M5A_ROOT / "evaluation_cases.json")["cases"]
        if item["id"] == case_id
    )


def fixture(case_id: str, field: str) -> dict[str, Any]:
    reference = case(case_id)[field]
    assert isinstance(reference, str)
    return load_json(M5A_ROOT / reference.removeprefix("local://synthetic-m5a/"))


def activation_allowed(
    resolution: dict[str, Any],
    patch: dict[str, Any],
    expected_checks: dict[str, str],
    approval: dict[str, Any] | None,
    release: dict[str, Any] | None,
) -> bool:
    """Encode the frozen M5A activation predicate for contract tests."""

    if patch["status"] not in {"APPROVED", "ACTIVE"}:
        return False
    if any(status != "PASS" for status in expected_checks.values()):
        return False
    if approval is None or approval["actor_type"] != "HUMAN_ROLE":
        return False
    if approval["decision"] != "APPROVE":
        return False
    if approval["actor_role_id"] == resolution["resolution_author_role_id"]:
        return False
    effective_from = datetime.fromisoformat(patch["effective_from"].replace("Z", "+00:00"))
    effective_to = patch["effective_to"]
    if effective_from > REFERENCE_TIME:
        return False
    if effective_to is not None:
        parsed_to = datetime.fromisoformat(effective_to.replace("Z", "+00:00"))
        if REFERENCE_TIME >= parsed_to:
            return False
    if release is None or release["status"] != "ACTIVE":
        return False
    return patch["patch_id"] in release["patch_ids"]


def approved_copy(patch: dict[str, Any]) -> dict[str, Any]:
    return {**patch, "status": "APPROVED"}


def valid_release(patch: dict[str, Any]) -> dict[str, Any]:
    return {
        "release_id": "SYNTHETIC-TEST-RELEASE",
        "status": "ACTIVE",
        "patch_ids": [patch["patch_id"]],
    }


def valid_approval(case_id: str) -> dict[str, Any]:
    approval_ref = case(case_id)["approval_ref"]
    assert isinstance(approval_ref, str)
    return load_json(M5A_ROOT / approval_ref.removeprefix("local://synthetic-m5a/"))


def automated_checks_pass(case_id: str) -> bool:
    checks = case(case_id)["expected_policy_ci_checks"]
    return all(
        status == "PASS"
        for check_id, status in checks.items()
        if check_id != "HUMAN_APPROVAL_PRESENT"
    )


def test_expert_resolution_alone_cannot_activate_a_patch() -> None:
    resolution = fixture("M5A-046", "expert_resolution_ref")
    patch = approved_copy(fixture("M5A-046", "knowledge_patch_ref"))
    assert (
        activation_allowed(
            resolution,
            patch,
            case("M5A-046")["expected_policy_ci_checks"],
            approval=None,
            release=None,
        )
        is False
    )


def test_automated_checks_alone_cannot_activate_m5a_047() -> None:
    resolution = fixture("M5A-047", "expert_resolution_ref")
    patch = approved_copy(fixture("M5A-047", "knowledge_patch_ref"))
    assert automated_checks_pass("M5A-047") is True
    assert (
        activation_allowed(
            resolution,
            patch,
            case("M5A-047")["expected_policy_ci_checks"],
            approval=None,
            release=None,
        )
        is False
    )


def test_human_approval_cannot_override_failed_mandatory_checks() -> None:
    resolution = fixture("M5A-048", "expert_resolution_ref")
    patch = approved_copy(fixture("M5A-048", "knowledge_patch_ref"))
    approval = {**valid_approval("M5A-048"), "decision": "APPROVE"}
    assert (
        activation_allowed(
            resolution,
            patch,
            case("M5A-048")["expected_policy_ci_checks"],
            approval=approval,
            release=valid_release(patch),
        )
        is False
    )


def test_same_role_self_approval_is_rejected() -> None:
    resolution = fixture("M5A-046", "expert_resolution_ref")
    patch = approved_copy(fixture("M5A-046", "knowledge_patch_ref"))
    approval = {
        **valid_approval("M5A-046"),
        "actor_role_id": resolution["resolution_author_role_id"],
    }
    assert (
        activation_allowed(
            resolution,
            patch,
            case("M5A-046")["expected_policy_ci_checks"],
            approval=approval,
            release=valid_release(patch),
        )
        is False
    )


def test_approved_is_not_equivalent_to_active() -> None:
    resolution = fixture("M5A-046", "expert_resolution_ref")
    patch = approved_copy(fixture("M5A-046", "knowledge_patch_ref"))
    approval = valid_approval("M5A-046")
    assert patch["status"] == "APPROVED"
    assert (
        activation_allowed(
            resolution,
            patch,
            case("M5A-046")["expected_policy_ci_checks"],
            approval=approval,
            release=None,
        )
        is False
    )


def test_release_inclusion_is_mandatory_for_activation() -> None:
    resolution = fixture("M5A-046", "expert_resolution_ref")
    patch = approved_copy(fixture("M5A-046", "knowledge_patch_ref"))
    approval = valid_approval("M5A-046")
    release_without_patch = {"release_id": "EMPTY", "status": "ACTIVE", "patch_ids": []}
    assert (
        activation_allowed(
            resolution,
            patch,
            case("M5A-046")["expected_policy_ci_checks"],
            approval=approval,
            release=release_without_patch,
        )
        is False
    )


def test_expired_patch_is_excluded_even_if_it_was_previously_released() -> None:
    resolution = fixture("M5A-050", "expert_resolution_ref")
    patch = fixture("M5A-050", "knowledge_patch_ref")
    old_release = fixture_from_path("releases/KB-SYN-V1.release.json")
    approval = {
        "actor_type": "HUMAN_ROLE",
        "actor_role_id": "SYN-ROLE-KNOWLEDGE-OWNER-001",
        "decision": "APPROVE",
    }
    assert patch["status"] == "EXPIRED"
    assert patch["patch_id"] in old_release["patch_ids"]
    assert (
        activation_allowed(
            resolution,
            patch,
            {key: "PASS" for key in case("M5A-050")["expected_policy_ci_checks"]},
            approval=approval,
            release=old_release,
        )
        is False
    )


def fixture_from_path(relative_path: str) -> dict[str, Any]:
    return load_json(M5A_ROOT / relative_path)


def test_rejected_patch_cannot_enter_a_release() -> None:
    patch = fixture("M5A-049", "knowledge_patch_ref")
    assert patch["status"] == "REJECTED"
    release = valid_release(patch)
    assert (
        activation_allowed(
            fixture("M5A-049", "expert_resolution_ref"),
            patch,
            case("M5A-049")["expected_policy_ci_checks"],
            approval={
                "actor_type": "HUMAN_ROLE",
                "actor_role_id": "SYN-ROLE-KNOWLEDGE-OWNER-001",
                "decision": "APPROVE",
            },
            release=release,
        )
        is False
    )


def test_agent_catalog_has_no_approval_authority() -> None:
    policy = fixture_from_path("approval_policy.json")
    orchestration_roles = {
        "CONDUCTOR",
        "EVIDENCE_SCOUT",
        "SCOPE_SENTINEL",
        "PROCESS_TABLE_SCOUT",
        "SKEPTIC",
        "COUNTERFACTUAL_SENTINEL",
        "EXPERT_ROUTER",
        "PATCH_PROPOSER",
        "POLICY_CI",
    }
    assert orchestration_roles.isdisjoint(policy["approval_authority_roles"])
    assert policy["agent_approval_allowed"] is False


def test_official_corpus_is_immutable_and_release_versions_are_explicit() -> None:
    lifecycle = fixture_from_path("lifecycle_policy.json")
    overlay = fixture_from_path("knowledge_overlay_policy.json")
    assert lifecycle["official_corpus_mutable"] is False
    assert overlay["official_corpus_immutable"] is True
    assert overlay["versioned"] is True
    assert overlay["mutation_policy"]["official_corpus_write_allowed"] is False
    assert overlay["mutation_policy"]["silent_patch_overwrite_allowed"] is False


def test_active_release_does_not_contain_an_expired_patch() -> None:
    active = fixture_from_path("releases/KB-SYN-V2.release.json")
    expired = fixture("M5A-050", "knowledge_patch_ref")
    assert active["status"] == "ACTIVE"
    assert expired["patch_id"] not in active["patch_ids"]


@pytest.mark.parametrize(
    ("case_id", "expected_status"),
    [
        ("M5A-046", "ACTIVE"),
        ("M5A-047", "AWAITING_APPROVAL"),
        ("M5A-048", "REJECTED"),
        ("M5A-049", "REJECTED"),
        ("M5A-050", "EXPIRED"),
    ],
)
def test_fixture_statuses_match_the_governance_outcomes(case_id: str, expected_status: str) -> None:
    patch = fixture(case_id, "knowledge_patch_ref")
    assert patch["status"] == expected_status
