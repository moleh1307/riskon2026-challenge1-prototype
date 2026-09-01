"""Compilation of active governed patches into retrieval-safe overlay units."""

from datetime import datetime

from riskon.governance.models import (
    GovernedPatch,
    KnowledgeOverlaySnapshot,
    KnowledgeRelease,
    OverlayEvidenceUnit,
    PatchStatus,
)


def compile_overlay_snapshot(
    release: KnowledgeRelease,
    governed_patches: tuple[GovernedPatch, ...],
    reference_time_utc: datetime,
) -> KnowledgeOverlaySnapshot:
    """Include only active, current, explicitly approved patch claims."""

    patch_by_id = {item.patch_id: item for item in governed_patches}
    units: list[OverlayEvidenceUnit] = []
    excluded: list[str] = []
    for patch_id in release.patch_ids:
        governed = patch_by_id.get(patch_id)
        if governed is None or governed.status is not PatchStatus.ACTIVE:
            excluded.append(patch_id)
            continue
        patch = governed.knowledge_patch
        if reference_time_utc < patch.effective_from or (
            patch.effective_to is not None and reference_time_utc >= patch.effective_to
        ):
            excluded.append(patch_id)
            continue
        for claim in patch.claims:
            overlay_ref = (
                f"local://knowledge-overlay/{release.release_id}/"
                f"{patch.patch_id}#claim-{claim.claim_id}"
            )
            units.append(
                OverlayEvidenceUnit(
                    overlay_ref=overlay_ref,
                    release_id=release.release_id,
                    patch_id=patch.patch_id,
                    claim_id=claim.claim_id,
                    text=claim.text,
                    scope=patch.scope,
                    critical=claim.critical,
                    backing_evidence_refs=list(claim.evidence_refs),
                    source_resolution_id=patch.source_resolution_id,
                    approval_id=governed.approval.approval_id,
                    effective_from=patch.effective_from,
                    effective_to=patch.effective_to,
                )
            )
    active_ids = list(dict.fromkeys(item.patch_id for item in units))
    return KnowledgeOverlaySnapshot(
        release_id=release.release_id,
        release_version=release.version,
        reference_time_utc=reference_time_utc,
        active_patch_ids=active_ids,
        excluded_patch_ids=list(dict.fromkeys(excluded)),
        evidence_units=units,
    )
