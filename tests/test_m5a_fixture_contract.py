"""M5A fixture validation through the existing structured contracts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from riskon.orchestra.models import CaseCapsule

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M5A_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m5a"
CASE_IDS = ["M5A-046", "M5A-047", "M5A-048", "M5A-049", "M5A-050"]
SCOPE_FIELDS = {
    "regions",
    "jurisdictions",
    "service_models",
    "solicitation_types",
    "workflow_stages",
    "client_classifications",
    "systems",
}
CLAIM_FIELDS = {"claim_id", "text", "evidence_refs", "critical"}
RESOLUTION_FIELDS = {
    "resolution_id",
    "case_capsule_id",
    "status",
    "resolution_author_role_id",
    "resolution_text",
    "authoritative_evidence_refs",
    "claims",
    "scope",
    "effective_from",
    "effective_to",
    "review_by",
    "knowledge_owner_role_id",
    "approval_required",
}
PATCH_FIELDS = {
    "patch_id",
    "operation",
    "status",
    "source_resolution_id",
    "claims",
    "scope",
    "authoritative_evidence_refs",
    "risk_level",
    "effective_from",
    "effective_to",
    "supersedes_patch_id",
    "knowledge_owner_role_id",
    "policy_ci_report_ref",
    "approval_ref",
}
APPROVAL_FIELDS = {
    "approval_id",
    "patch_id",
    "actor_type",
    "actor_role_id",
    "decision",
    "timestamp_utc",
    "reviewed_claim_ids",
    "reviewed_scope",
    "comment",
}
RELEASE_FIELDS = {
    "release_id",
    "version",
    "previous_release_id",
    "patch_ids",
    "created_at_utc",
    "activated_at_utc",
    "activated_by_role_id",
    "status",
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def cases_by_id() -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in load_json(M5A_ROOT / "evaluation_cases.json")["cases"]}


def local_path(reference: str) -> Path:
    prefix = "local://synthetic-m5a/"
    assert reference.startswith(prefix)
    return M5A_ROOT / reference.removeprefix(prefix)


def fixture_bundle(case_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    case = cases_by_id()[case_id]
    resolution = load_json(local_path(case["expert_resolution_ref"]))
    patch = load_json(local_path(case["knowledge_patch_ref"]))
    capsule = load_json(local_path(case["case_capsule_ref"]))
    return capsule, resolution, patch


def claim_ids(claims: list[dict[str, Any]]) -> set[str]:
    return {claim["claim_id"] for claim in claims}


def scope_contains(container: dict[str, list[str]], nested: dict[str, list[str]]) -> bool:
    return all(set(nested[field]) <= set(container[field]) for field in SCOPE_FIELDS)


def utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is UTC
    return parsed


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_m5a_capsule_deserializes_through_existing_case_capsule(case_id: str) -> None:
    capsule, _resolution, _patch = fixture_bundle(case_id)
    parsed = CaseCapsule.model_validate(capsule)
    assert parsed.capsule_id == f"m5a-capsule-{case_id}"
    assert parsed.baseline_decision.value == "ABSTAIN"
    assert parsed.verification_status.value == "INSUFFICIENT"
    assert parsed.evidence_refs == []
    assert parsed.model_dump(mode="json") == capsule


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_m5a_resolution_has_exact_fields_and_candidate_status(case_id: str) -> None:
    _capsule, resolution, _patch = fixture_bundle(case_id)
    assert set(resolution) == RESOLUTION_FIELDS
    assert resolution["status"] == "CANDIDATE_RESOLUTION"
    assert resolution["approval_required"] is True
    assert set(resolution["scope"]) == SCOPE_FIELDS
    assert resolution["scope"]["regions"]
    assert resolution["scope"]["service_models"]
    assert resolution["claims"]
    assert all(set(claim) == CLAIM_FIELDS for claim in resolution["claims"])
    assert all(
        reference.startswith("local://synthetic-m5a/")
        for reference in resolution["authoritative_evidence_refs"]
    )


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_m5a_patch_has_exact_fields_and_declared_lifecycle_status(case_id: str) -> None:
    _capsule, _resolution, patch = fixture_bundle(case_id)
    assert set(patch) == PATCH_FIELDS
    assert patch["operation"] in {"ADD", "UPDATE", "DEPRECATE"}
    assert patch["status"] in {
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
    assert patch["risk_level"] in {"NORMAL", "CRITICAL"}
    assert set(patch["scope"]) == SCOPE_FIELDS
    assert all(set(claim) == CLAIM_FIELDS for claim in patch["claims"])
    assert patch["policy_ci_report_ref"].startswith("local://synthetic-m5a/")
    if patch["operation"] == "UPDATE":
        assert patch["supersedes_patch_id"]


def test_m5a_claims_and_evidence_are_consistent_except_deliberate_scope_case() -> None:
    for case_id in CASE_IDS:
        _capsule, resolution, patch = fixture_bundle(case_id)
        assert claim_ids(patch["claims"]) <= claim_ids(resolution["claims"])
        resolution_refs = set(resolution["authoritative_evidence_refs"])
        patch_refs = set(patch["authoritative_evidence_refs"])
        assert patch_refs <= resolution_refs
        for claim in resolution["claims"]:
            assert set(claim["evidence_refs"]) <= resolution_refs
        for claim in patch["claims"]:
            assert set(claim["evidence_refs"]) <= patch_refs

        contained = scope_contains(resolution["scope"], patch["scope"])
        if case_id == "M5A-049":
            assert contained is False
        else:
            assert contained is True


def test_m5a_049_is_the_only_deliberately_invalid_scope_fixture() -> None:
    invalid_cases = []
    for case_id in CASE_IDS:
        _capsule, resolution, patch = fixture_bundle(case_id)
        if not scope_contains(resolution["scope"], patch["scope"]):
            invalid_cases.append(case_id)
    assert invalid_cases == ["M5A-049"]


def test_m5a_approvals_and_releases_have_exact_fields_and_utc_timestamps() -> None:
    approval_paths = sorted((M5A_ROOT / "approvals").glob("*.json"))
    assert len(approval_paths) == 3
    for path in approval_paths:
        approval = load_json(path)
        assert set(approval) == APPROVAL_FIELDS
        assert approval["actor_type"] == "HUMAN_ROLE"
        assert approval["decision"] in {"APPROVE", "REJECT"}
        assert utc_timestamp(approval["timestamp_utc"]).tzinfo is UTC
        assert set(approval["reviewed_scope"]) == SCOPE_FIELDS

    releases = [load_json(path) for path in sorted((M5A_ROOT / "releases").glob("*.json"))]
    assert len(releases) == 2
    for release in releases:
        assert set(release) == RELEASE_FIELDS
        assert release["status"] in {"DRAFT", "ACTIVE", "SUPERSEDED", "ROLLED_BACK"}
        assert utc_timestamp(release["created_at_utc"]).tzinfo is UTC
        assert utc_timestamp(release["activated_at_utc"]).tzinfo is UTC


def test_m5a_all_fixture_references_are_local_and_no_raw_confidential_content_exists() -> None:
    values: list[str] = []
    for path in M5A_ROOT.rglob("*.json"):
        values.extend(
            value
            for value in json.loads(path.read_text(encoding="utf-8")).values()
            if isinstance(value, str)
        )
        text = path.read_text(encoding="utf-8")
        assert "http://" not in text
        assert "https://" not in text
        assert "/Users/" not in text
        assert "@" not in text
        assert "Bank Julius Baer" not in text
        assert "employee" not in text.lower()
    assert all("://" not in value or value.startswith("local://synthetic-m5a/") for value in values)


def test_m5a_active_patch_release_and_expired_patch_are_not_conflated() -> None:
    cases = cases_by_id()
    active_patch = load_json(local_path(cases["M5A-046"]["knowledge_patch_ref"]))
    expired_patch = load_json(local_path(cases["M5A-050"]["knowledge_patch_ref"]))
    v1 = load_json(M5A_ROOT / "releases" / "KB-SYN-V1.release.json")
    v2 = load_json(M5A_ROOT / "releases" / "KB-SYN-V2.release.json")
    assert active_patch["status"] == "ACTIVE"
    assert active_patch["patch_id"] in v2["patch_ids"]
    assert v2["status"] == "ACTIVE"
    assert expired_patch["status"] == "EXPIRED"
    assert expired_patch["patch_id"] in v1["patch_ids"]
    assert v1["status"] == "SUPERSEDED"
    assert expired_patch["patch_id"] not in v2["patch_ids"]
