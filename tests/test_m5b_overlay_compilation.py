"""Compilation rules for active M5B overlay snapshots."""

from datetime import timedelta

import pytest
from m5b_helpers import REFERENCE_TIME, service
from test_m5b_release_activation import governed_patch

from riskon.governance.errors import ReleaseActivationError
from riskon.governance.models import KnowledgeRelease, PatchStatus, ReleaseStatus
from riskon.governance.overlay import compile_overlay_snapshot


def release(*patch_ids: str, status: ReleaseStatus = ReleaseStatus.ACTIVE) -> KnowledgeRelease:
    return KnowledgeRelease(
        release_id="release-1",
        version="1.0.0",
        patch_ids=list(patch_ids),
        created_at_utc=REFERENCE_TIME,
        activated_at_utc=REFERENCE_TIME,
        activated_by_role_id="role-owner",
        status=status,
    )


def test_active_current_patch_compiles_claim_with_canonical_provenance(tmp_path) -> None:
    governed = governed_patch(tmp_path, status=PatchStatus.ACTIVE)
    snapshot = compile_overlay_snapshot(release("M5A-046-PATCH"), (governed,), REFERENCE_TIME)
    assert snapshot.active_patch_ids == ["M5A-046-PATCH"]
    assert snapshot.excluded_patch_ids == []
    unit = snapshot.evidence_units[0]
    assert unit.overlay_ref == (
        "local://knowledge-overlay/release-1/M5A-046-PATCH#claim-meridian_beta_basic_applies"
    )
    assert unit.backing_evidence_refs == governed.knowledge_patch.claims[0].evidence_refs
    assert unit.approval_id == governed.approval.approval_id


@pytest.mark.parametrize(
    "status",
    [
        PatchStatus.PROPOSED,
        PatchStatus.TESTED,
        PatchStatus.AWAITING_APPROVAL,
        PatchStatus.APPROVED,
        PatchStatus.REJECTED,
        PatchStatus.EXPIRED,
    ],
)
def test_nonactive_statuses_are_excluded(tmp_path, status: PatchStatus) -> None:
    governed = governed_patch(tmp_path, status=status)
    snapshot = compile_overlay_snapshot(release("M5A-046-PATCH"), (governed,), REFERENCE_TIME)
    assert snapshot.evidence_units == []
    assert snapshot.excluded_patch_ids == ["M5A-046-PATCH"]


def test_missing_patch_record_is_excluded() -> None:
    snapshot = compile_overlay_snapshot(release("missing"), (), REFERENCE_TIME)
    assert snapshot.active_patch_ids == []
    assert snapshot.excluded_patch_ids == ["missing"]


def test_future_and_expired_effective_windows_are_excluded(tmp_path) -> None:
    governed = governed_patch(tmp_path, status=PatchStatus.ACTIVE)
    future = governed.model_copy(
        update={
            "knowledge_patch": governed.knowledge_patch.model_copy(
                update={"effective_from": REFERENCE_TIME + timedelta(days=1)}
            )
        }
    )
    expired = governed.model_copy(
        update={
            "knowledge_patch": governed.knowledge_patch.model_copy(
                update={"effective_to": REFERENCE_TIME}
            )
        }
    )
    assert (
        compile_overlay_snapshot(release(future.patch_id), (future,), REFERENCE_TIME).evidence_units
        == []
    )
    assert (
        compile_overlay_snapshot(
            release(expired.patch_id), (expired,), REFERENCE_TIME
        ).evidence_units
        == []
    )


def test_duplicate_patch_ids_and_claims_are_deduplicated_at_id_level(tmp_path) -> None:
    governed = governed_patch(tmp_path, status=PatchStatus.ACTIVE)
    snapshot = compile_overlay_snapshot(
        release("M5A-046-PATCH", "M5A-046-PATCH"),
        (governed,),
        REFERENCE_TIME,
    )
    assert snapshot.active_patch_ids == ["M5A-046-PATCH"]
    assert len(snapshot.evidence_units) == 2


def test_nonactive_release_cannot_be_used_by_service(tmp_path) -> None:
    instance = service(tmp_path)
    with pytest.raises(ReleaseActivationError):
        instance.compile_overlay(
            release("M5A-046-PATCH", status=ReleaseStatus.SUPERSEDED), REFERENCE_TIME
        )
