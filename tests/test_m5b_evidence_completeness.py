"""M5B evidence completeness and reference-resolution checks."""

import pytest
from m5b_helpers import LOCAL_REF, valid_claim, valid_patch, valid_resolution

from riskon.governance.evidence_checks import (
    all_references,
    claim_subset,
    evidence_completeness,
    reference_resolution,
)


def test_complete_claims_pass_evidence_completeness() -> None:
    resolution = valid_resolution()
    patch = valid_patch(resolution)
    assert evidence_completeness(resolution, patch) == (
        True,
        "all substantive claims carry evidence references",
    )


@pytest.mark.parametrize(
    "resolution_kwargs,patch_kwargs,fragment",
    [
        ({"claims": []}, {}, "substantive"),
        ({"refs": []}, {}, "no authoritative"),
        ({"claims": [valid_claim(evidence_refs=[])]}, {}, "without evidence"),
        ({}, {"claims": [valid_claim(evidence_refs=[])]}, "without evidence"),
    ],
)
def test_incomplete_claim_sets_fail_closed(
    resolution_kwargs: dict[str, object],
    patch_kwargs: dict[str, object],
    fragment: str,
) -> None:
    resolution = valid_resolution(**resolution_kwargs)
    patch = valid_patch(resolution, **patch_kwargs)
    ok, details = evidence_completeness(resolution, patch)
    assert ok is False
    assert fragment in details


def test_claim_subset_accepts_matching_ids_and_rejects_new_ids() -> None:
    resolution = valid_resolution()
    assert claim_subset(resolution, valid_patch(resolution)) == (
        True,
        "patch claim IDs are a subset of the resolution claim IDs",
    )
    foreign = valid_claim("foreign")
    patch = valid_patch(resolution, claims=[foreign])
    ok, details = claim_subset(resolution, patch)
    assert ok is False
    assert "foreign" in details


def test_all_references_are_deduplicated_in_stable_order() -> None:
    second = "local://synthetic-m5a/policy_ci_policy.json#second"
    resolution = valid_resolution(
        refs=[LOCAL_REF, second],
        claims=[valid_claim(evidence_refs=[LOCAL_REF, second])],
    )
    patch = valid_patch(
        resolution,
        refs=[second, LOCAL_REF],
        claims=[valid_claim(evidence_refs=[second])],
    )
    assert list(all_references(resolution, patch)) == [LOCAL_REF, second]


@pytest.mark.parametrize(
    ("reference", "resolved", "expected_ok"),
    [
        (LOCAL_REF, object(), True),
        ("https://example.com/evidence", object(), False),
        ("local://synthetic-m5a/missing.json#x", None, False),
        ("local://synthetic-m5a/evaluation-cases.json#x", object(), True),
    ],
)
def test_reference_resolution_requires_local_resolvable_refs(
    reference: str,
    resolved: object | None,
    expected_ok: bool,
) -> None:
    resolution = valid_resolution(refs=[reference], claims=[valid_claim(evidence_refs=[reference])])
    patch = valid_patch(
        resolution, refs=[reference], claims=[valid_claim(evidence_refs=[reference])]
    )
    ok, _ = reference_resolution(resolution, patch, lambda value: resolved)
    assert ok is expected_ok


def test_reference_resolution_checks_all_claim_and_authority_refs() -> None:
    missing = "local://synthetic-m5a/not-found.json#claim"
    resolution = valid_resolution(claims=[valid_claim(evidence_refs=[LOCAL_REF])])
    patch = valid_patch(
        resolution,
        refs=[missing],
        claims=[valid_claim(evidence_refs=[LOCAL_REF])],
    )
    ok, details = reference_resolution(
        resolution, patch, lambda ref: None if "not-found" in ref else object()
    )
    assert ok is False
    assert missing in details


def test_reference_resolution_does_not_call_resolver_for_nonlocal_ref() -> None:
    seen: list[str] = []
    resolution = valid_resolution(
        refs=["file:///tmp/evidence"],
        claims=[valid_claim(evidence_refs=["file:///tmp/evidence"])],
    )
    patch = valid_patch(
        resolution,
        refs=["file:///tmp/evidence"],
        claims=[valid_claim(evidence_refs=["file:///tmp/evidence"])],
    )
    ok, _ = reference_resolution(resolution, patch, lambda ref: seen.append(ref))
    assert ok is False
    assert seen == []
