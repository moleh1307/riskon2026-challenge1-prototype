"""The closed M5B patch lifecycle state machine."""

from riskon.governance.errors import InvalidLifecycleTransitionError
from riskon.governance.models import PatchStatus

ALLOWED_TRANSITIONS: dict[tuple[PatchStatus, PatchStatus], str] = {
    (PatchStatus.PROPOSED, PatchStatus.TESTED): "PRE_APPROVAL_POLICY_CI",
    (PatchStatus.TESTED, PatchStatus.AWAITING_APPROVAL): "AUTOMATED_CHECKS_PASS",
    (PatchStatus.AWAITING_APPROVAL, PatchStatus.APPROVED): "VALID_HUMAN_APPROVAL",
    (PatchStatus.APPROVED, PatchStatus.ACTIVE): "EXPLICIT_RELEASE_ACTIVATION",
    (PatchStatus.TESTED, PatchStatus.REJECTED): "MANDATORY_CHECK_FAIL",
    (PatchStatus.AWAITING_APPROVAL, PatchStatus.REJECTED): "HUMAN_REJECTION",
    (PatchStatus.ACTIVE, PatchStatus.EXPIRED): "EFFECTIVE_TO_REACHED",
}


def transition_requirement(previous: PatchStatus, new: PatchStatus) -> str | None:
    """Return the frozen requirement for one transition, if it is allowed."""

    return ALLOWED_TRANSITIONS.get((previous, new))


def validate_transition(previous: PatchStatus, new: PatchStatus) -> None:
    """Raise rather than silently permitting a lifecycle shortcut."""

    if transition_requirement(previous, new) is None:
        raise InvalidLifecycleTransitionError(
            f"Forbidden M5B lifecycle transition: {previous.value} -> {new.value}"
        )


def transition(previous: PatchStatus, new: PatchStatus) -> PatchStatus:
    """Validate and return the target status."""

    validate_transition(previous, new)
    return new
