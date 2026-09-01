"""Release-candidate validation and explicit activation helpers."""

from datetime import timedelta

import pytest
from m5b_helpers import (
    REFERENCE_TIME,
    service,
    valid_approval,
)

from riskon.governance.errors import ExpiredPatchError, ReleaseActivationError
from riskon.governance.models import (
    MANDATORY_CHECK_ORDER,
    GovernedPatch,
    PatchStatus,
    PolicyCICheckResult,
    PolicyCIPhase,
    PolicyCIReport,
    PolicyCIStatus,
    ReleaseStatus,
)
from riskon.governance.release import make_release, validate_release_candidate


def passing_report(
    patch_id: str = "patch-1", resolution_id: str = "resolution-1"
) -> PolicyCIReport:
    return PolicyCIReport(
        phase=PolicyCIPhase.ACTIVATION,
        patch_id=patch_id,
        resolution_id=resolution_id,
        reference_time_utc=REFERENCE_TIME,
        overall_status=PolicyCIStatus.APPROVED,
        checks=[
            PolicyCICheckResult(check_id=item, status="PASS") for item in MANDATORY_CHECK_ORDER
        ],
    )


def governed_patch(tmp_path, *, status: PatchStatus = PatchStatus.APPROVED) -> GovernedPatch:
    instance = service(tmp_path)
    capsule, resolution, patch, _ = instance.load_case_inputs("M5A-046")
    patch = patch.model_copy(update={"status": PatchStatus.PROPOSED})
    approval = valid_approval(patch, resolution)
    return GovernedPatch(
        case_capsule=capsule,
        expert_resolution=resolution,
        knowledge_patch=patch,
        policy_ci_report=passing_report(patch.patch_id, resolution.resolution_id),
        approval=approval,
        status=status,
    )


def request(instance, *, patch_id: str = "M5A-046-PATCH"):
    return instance.load_release_request("M5A-046").model_copy(update={"patch_id": patch_id})


def test_approved_current_patch_is_valid_release_candidate(tmp_path) -> None:
    instance = service(tmp_path)
    governed = governed_patch(tmp_path)
    validate_release_candidate((governed,), request(instance), REFERENCE_TIME)


def test_empty_release_candidate_is_rejected(tmp_path) -> None:
    instance = service(tmp_path)
    with pytest.raises(ReleaseActivationError, match="at least one"):
        validate_release_candidate((), request(instance), REFERENCE_TIME)


def test_request_must_select_one_supplied_patch(tmp_path) -> None:
    instance = service(tmp_path)
    governed = governed_patch(tmp_path)
    with pytest.raises(ReleaseActivationError, match="not in"):
        validate_release_candidate((governed,), request(instance, patch_id="other"), REFERENCE_TIME)


@pytest.mark.parametrize("status", [PatchStatus.TESTED, PatchStatus.REJECTED, PatchStatus.ACTIVE])
def test_nonapproved_statuses_cannot_enter_release(tmp_path, status: PatchStatus) -> None:
    instance = service(tmp_path)
    governed = governed_patch(tmp_path, status=status)
    with pytest.raises(ReleaseActivationError, match="not APPROVED"):
        validate_release_candidate((governed,), request(instance), REFERENCE_TIME)


def test_expired_governed_status_raises_expired_error(tmp_path) -> None:
    instance = service(tmp_path)
    governed = governed_patch(tmp_path, status=PatchStatus.EXPIRED)
    with pytest.raises(ExpiredPatchError):
        validate_release_candidate((governed,), request(instance), REFERENCE_TIME)


def test_future_patch_is_not_eligible(tmp_path) -> None:
    instance = service(tmp_path)
    governed = governed_patch(tmp_path)
    future = governed.model_copy(
        update={
            "knowledge_patch": governed.knowledge_patch.model_copy(
                update={"effective_from": REFERENCE_TIME + timedelta(days=1)}
            )
        }
    )
    with pytest.raises(ReleaseActivationError, match="not yet effective"):
        validate_release_candidate((future,), request(instance), REFERENCE_TIME)


def test_reached_effective_to_is_expired(tmp_path) -> None:
    instance = service(tmp_path)
    governed = governed_patch(tmp_path)
    expired = governed.model_copy(
        update={
            "knowledge_patch": governed.knowledge_patch.model_copy(
                update={"effective_to": REFERENCE_TIME}
            )
        }
    )
    with pytest.raises(ExpiredPatchError):
        validate_release_candidate((expired,), request(instance), REFERENCE_TIME)


def test_make_release_returns_active_versioned_release(tmp_path) -> None:
    instance = service(tmp_path)
    governed = governed_patch(tmp_path)
    release = make_release((governed,), request(instance), REFERENCE_TIME)
    assert release.status is ReleaseStatus.ACTIVE
    assert release.patch_ids == [governed.patch_id]
    assert release.version == "1.0.0"
    assert release.activated_by_role_id == "SYN-ROLE-KNOWLEDGE-OWNER-001"


def test_make_release_accepts_explicit_previous_release_and_version(tmp_path) -> None:
    instance = service(tmp_path)
    governed = governed_patch(tmp_path)
    release = make_release(
        (governed,),
        request(instance),
        REFERENCE_TIME,
        previous_release_id="KB-SYN-V1",
        version="2.0.0",
    )
    assert release.previous_release_id == "KB-SYN-V1"
    assert release.version == "2.0.0"


def test_model_copy_keeps_governed_patch_immutable(tmp_path) -> None:
    governed = governed_patch(tmp_path)
    active = governed.model_copy(update={"status": PatchStatus.ACTIVE})
    assert governed.status is PatchStatus.APPROVED
    assert active.status is PatchStatus.ACTIVE
