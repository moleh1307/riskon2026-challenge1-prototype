"""M5B separation-of-duties and approval-role checks."""

import pytest
from m5b_helpers import valid_approval, valid_patch, valid_resolution

from riskon.governance.approval import require_approvable, validate_human_approval
from riskon.governance.errors import MissingHumanApprovalError, SelfApprovalError
from riskon.governance.models import ActorType, ApprovalDecision


def test_independent_human_approval_is_valid() -> None:
    resolution = valid_resolution()
    patch = valid_patch(resolution)
    approval = valid_approval(patch, resolution)
    assert validate_human_approval(resolution, approval) == (
        True,
        "independent human decision is valid",
    )
    assert require_approvable(resolution, approval) == approval


@pytest.mark.parametrize(
    "approval",
    [
        None,
        valid_approval(actor_type=ActorType.AGENT_ROLE),
        valid_approval(actor="role-author"),
    ],
)
def test_invalid_or_missing_approval_fails_validation(approval: object) -> None:
    resolution = valid_resolution()
    ok, details = validate_human_approval(resolution, approval)  # type: ignore[arg-type]
    assert ok is False
    assert details


def test_required_approval_errors_are_typed() -> None:
    resolution = valid_resolution()
    with pytest.raises(MissingHumanApprovalError):
        require_approvable(resolution, None)
    with pytest.raises(SelfApprovalError):
        require_approvable(resolution, valid_approval(actor="role-author"))
    with pytest.raises(MissingHumanApprovalError):
        require_approvable(resolution, valid_approval(actor_type=ActorType.AGENT_ROLE))
    with pytest.raises(MissingHumanApprovalError):
        require_approvable(
            resolution,
            valid_approval(decision=ApprovalDecision.REJECT),
        )


def test_validation_can_require_approve_decision() -> None:
    resolution = valid_resolution()
    patch = valid_patch(resolution)
    rejected = valid_approval(patch, resolution, decision=ApprovalDecision.REJECT)
    assert validate_human_approval(resolution, rejected, require_approve=True) == (
        False,
        "approval decision is not APPROVE",
    )
    assert validate_human_approval(resolution, rejected, require_approve=False)[0] is True


def test_empty_approval_patch_id_is_rejected_at_validation_boundary() -> None:
    resolution = valid_resolution()
    approval = valid_approval().model_copy(update={"patch_id": ""})
    assert validate_human_approval(resolution, approval)[0] is False
