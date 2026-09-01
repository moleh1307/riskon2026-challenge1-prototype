"""Evidence and local-reference checks for Policy CI."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from riskon.governance.models import ExpertResolution, KnowledgePatch

LOCAL_PREFIX = "local://"


def evidence_completeness(
    resolution: ExpertResolution,
    patch: KnowledgePatch,
) -> tuple[bool, str]:
    """Require every substantive resolution and patch claim to cite evidence."""

    resolution_refs = set(resolution.authoritative_evidence_refs)
    if not resolution.claims or not patch.claims:
        return False, "substantive resolution and patch claims are required"
    if not resolution_refs:
        return False, "resolution has no authoritative evidence references"
    missing_resolution = [claim.claim_id for claim in resolution.claims if not claim.evidence_refs]
    missing_patch = [claim.claim_id for claim in patch.claims if not claim.evidence_refs]
    if missing_resolution or missing_patch:
        missing = ", ".join(missing_resolution + missing_patch)
        return False, f"claims without evidence references: {missing}"
    return True, "all substantive claims carry evidence references"


def claim_subset(resolution: ExpertResolution, patch: KnowledgePatch) -> tuple[bool, str]:
    """Check that a patch cannot introduce a new claim identifier."""

    resolution_ids = {claim.claim_id for claim in resolution.claims}
    patch_ids = {claim.claim_id for claim in patch.claims}
    missing = sorted(patch_ids - resolution_ids)
    if missing:
        return False, f"patch claims outside resolution: {', '.join(missing)}"
    return True, "patch claim IDs are a subset of the resolution claim IDs"


def _normalise_reference(reference: str) -> str:
    """Normalize the historical M5A hyphenated evaluation filename alias."""

    return reference.replace("/evaluation-cases.json", "/evaluation_cases.json")


def reference_resolution(
    resolution: ExpertResolution,
    patch: KnowledgePatch,
    resolver: Callable[[str], object | None],
) -> tuple[bool, str]:
    """Require all evidence references to be local and resolvable."""

    for reference in all_references(resolution, patch):
        if not reference.startswith(LOCAL_PREFIX):
            return False, f"non-local reference: {reference}"
        resolved = resolver(_normalise_reference(reference))
        if resolved is None:
            return False, f"unresolved local reference: {reference}"
    return True, "all local evidence references resolve"


def all_references(resolution: ExpertResolution, patch: KnowledgePatch) -> Iterable[str]:
    """Yield the deduplicated references used by evidence checks."""

    values: list[str] = [
        *resolution.authoritative_evidence_refs,
        *patch.authoritative_evidence_refs,
        *(ref for claim in resolution.claims for ref in claim.evidence_refs),
        *(ref for claim in patch.claims for ref in claim.evidence_refs),
    ]
    yield from dict.fromkeys(values)
