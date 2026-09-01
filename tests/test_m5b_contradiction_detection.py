"""Generic claim-relation and critical-control checks."""

import pytest
from m5b_helpers import valid_claim, valid_patch, valid_resolution

from riskon.governance.contradiction import detect_contradictions, preserves_critical_controls
from riskon.governance.models import ClaimRelation, PatchOperation


def relation(
    left: str,
    right: str,
    relation_name: str,
    *,
    critical: bool = False,
) -> ClaimRelation:
    return ClaimRelation(
        left_claim_id=left,
        right_claim_id=right,
        relation=relation_name,
        critical=critical,
        evidence_refs=["local://synthetic-m5a/policy_ci_policy.json#relation"],
    )


@pytest.mark.parametrize(
    "relation_name",
    ["SUPPORTS", "SUPERSEDES"],
)
def test_non_contradictory_relations_do_not_fail(relation_name: str) -> None:
    patch = valid_patch(claims=[valid_claim("new")])
    assert detect_contradictions(patch, [relation("old", "new", relation_name)])[0] is True


def test_contradiction_relation_fails_only_on_proposed_left_claim() -> None:
    patch = valid_patch(claims=[valid_claim("new")])
    ok, details = detect_contradictions(
        patch,
        [relation("new", "authoritative", "CONTRADICTS")],
    )
    assert ok is False
    assert "new" in details
    assert (
        detect_contradictions(
            patch,
            [relation("authoritative", "new", "CONTRADICTS")],
        )[0]
        is True
    )


def test_empty_relations_pass_generic_contradiction_check() -> None:
    assert detect_contradictions(valid_patch(), []) == (
        True,
        "no generic contradiction relation applies",
    )


def test_normal_add_without_critical_relation_preserves_controls() -> None:
    resolution = valid_resolution()
    patch = valid_patch(resolution, claims=[valid_claim("new")])
    assert preserves_critical_controls(resolution, patch, []) == (
        True,
        "new patch does not remove an existing critical control",
    )


def test_noncritical_add_with_noncritical_contradiction_relation_passes() -> None:
    resolution = valid_resolution(claims=[valid_claim("new")])
    patch = valid_patch(resolution, claims=[valid_claim("new")])
    result = preserves_critical_controls(
        resolution,
        patch,
        [relation("new", "old", "CONTRADICTS", critical=False)],
    )
    assert result[0] is True


def test_critical_add_against_critical_control_fails() -> None:
    claim = valid_claim("new", critical=True)
    resolution = valid_resolution(claims=[claim])
    patch = valid_patch(resolution, claims=[claim])
    ok, details = preserves_critical_controls(
        resolution,
        patch,
        [relation("new", "old", "CONTRADICTS", critical=True)],
    )
    assert ok is False
    assert "critical ADD" in details


@pytest.mark.parametrize("operation", [PatchOperation.UPDATE, PatchOperation.DEPRECATE])
def test_critical_update_or_deprecation_requires_supersedes(
    operation: PatchOperation,
) -> None:
    claim = valid_claim("replacement", critical=True)
    resolution = valid_resolution(claims=[claim, valid_claim("old")])
    patch = valid_patch(resolution, operation=operation, claims=[claim])
    assert (
        preserves_critical_controls(
            resolution, patch, [relation("replacement", "old", "SUPERSEDES")]
        )[0]
        is True
    )
    assert (
        preserves_critical_controls(
            resolution, patch, [relation("replacement", "old", "CONTRADICTS")]
        )[0]
        is False
    )


def test_update_supersedes_only_unknown_claim_does_not_satisfy_control() -> None:
    claim = valid_claim("replacement", critical=True)
    resolution = valid_resolution(claims=[claim])
    patch = valid_patch(
        resolution,
        operation=PatchOperation.UPDATE,
        claims=[claim],
    )
    ok, details = preserves_critical_controls(
        resolution,
        patch,
        [relation("replacement", "unrelated", "SUPERSEDES")],
    )
    assert ok is False
    assert "lacks" in details


def test_update_with_noncritical_replacement_does_not_pass() -> None:
    claim = valid_claim("replacement", critical=False)
    resolution = valid_resolution(claims=[claim])
    patch = valid_patch(resolution, operation=PatchOperation.UPDATE, claims=[claim])
    assert (
        preserves_critical_controls(
            resolution,
            patch,
            [relation("replacement", "old", "SUPERSEDES")],
        )[0]
        is False
    )
