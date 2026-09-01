"""Generic claim-relation and critical-control checks."""

from __future__ import annotations

from collections.abc import Iterable

from riskon.governance.models import ClaimRelation, ExpertResolution, KnowledgePatch


def detect_contradictions(
    patch: KnowledgePatch,
    relations: Iterable[ClaimRelation],
) -> tuple[bool, str]:
    """Reject a proposed claim on the proposal side of a CONTRADICTS relation."""

    patch_ids = {claim.claim_id for claim in patch.claims}
    for relation in relations:
        if relation.relation != "CONTRADICTS":
            continue
        if relation.left_claim_id in patch_ids:
            return False, (
                f"claim {relation.left_claim_id} contradicts authoritative claim "
                f"{relation.right_claim_id}"
            )
    return True, "no generic contradiction relation applies"


def preserves_critical_controls(
    resolution: ExpertResolution,
    patch: KnowledgePatch,
    relations: Iterable[ClaimRelation],
) -> tuple[bool, str]:
    """Ensure critical updates/deprecations have a critical superseding claim."""

    patch_ids = {claim.claim_id for claim in patch.claims}
    critical_patch_ids = {claim.claim_id for claim in patch.claims if claim.critical}
    if patch.operation.value == "ADD" and not any(
        relation.critical
        and relation.relation == "CONTRADICTS"
        and relation.left_claim_id in patch_ids
        for relation in relations
    ):
        return True, "new patch does not remove an existing critical control"
    if patch.operation.value == "ADD" and critical_patch_ids:
        return False, "critical ADD patch conflicts with an existing critical control"

    resolution_ids = {claim.claim_id for claim in resolution.claims}
    if patch.operation.value in {"UPDATE", "DEPRECATE"}:
        for relation in relations:
            if relation.relation != "SUPERSEDES" or relation.left_claim_id not in patch_ids:
                continue
            if relation.right_claim_id in resolution_ids and any(
                claim.claim_id == relation.left_claim_id and claim.critical
                for claim in patch.claims
            ):
                return True, "critical replacement explicitly supersedes the prior claim"
        return False, "critical update/deprecation lacks a critical SUPERSEDES relation"
    return True, "critical controls remain preserved"
