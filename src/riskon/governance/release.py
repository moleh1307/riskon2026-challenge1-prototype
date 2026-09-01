"""Explicit release activation helpers."""

from datetime import datetime

from riskon.governance.errors import ExpiredPatchError, ReleaseActivationError
from riskon.governance.models import (
    GovernedPatch,
    KnowledgeRelease,
    KnowledgeReleaseRequest,
    PatchStatus,
    ReleaseStatus,
)


def validate_release_candidate(
    governed_patches: tuple[GovernedPatch, ...],
    request: KnowledgeReleaseRequest,
    reference_time_utc: datetime,
) -> None:
    """Ensure an explicit request contains only approved, current patches."""

    if not governed_patches:
        raise ReleaseActivationError("An active release must contain at least one patch")
    selected = {patch.patch_id for patch in governed_patches}
    if request.patch_id not in selected:
        raise ReleaseActivationError("Release request patch is not in the governed patch set")
    for governed in governed_patches:
        if governed.status is not PatchStatus.APPROVED:
            if governed.status is PatchStatus.EXPIRED:
                raise ExpiredPatchError("Expired patches cannot enter an active release")
            raise ReleaseActivationError(
                f"Patch {governed.patch_id} is not APPROVED for release activation"
            )
        patch = governed.knowledge_patch
        if reference_time_utc < patch.effective_from:
            raise ReleaseActivationError(f"Patch {patch.patch_id} is not yet effective")
        if patch.effective_to is not None and reference_time_utc >= patch.effective_to:
            raise ExpiredPatchError(f"Patch {patch.patch_id} is expired")


def make_release(
    governed_patches: tuple[GovernedPatch, ...],
    request: KnowledgeReleaseRequest,
    reference_time_utc: datetime,
    *,
    previous_release_id: str | None = None,
    version: str = "1.0.0",
) -> KnowledgeRelease:
    """Create a release record after validation; activation remains explicit."""

    validate_release_candidate(governed_patches, request, reference_time_utc)
    return KnowledgeRelease(
        release_id=request.release_id,
        version=version,
        previous_release_id=previous_release_id,
        patch_ids=[item.patch_id for item in governed_patches],
        created_at_utc=reference_time_utc,
        activated_at_utc=reference_time_utc,
        activated_by_role_id=request.requested_by_role_id,
        status=ReleaseStatus.ACTIVE,
    )
