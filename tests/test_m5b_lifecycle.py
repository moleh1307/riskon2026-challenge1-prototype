"""Closed-world M5B lifecycle transitions."""

import pytest

from riskon.governance.errors import InvalidLifecycleTransitionError
from riskon.governance.lifecycle import (
    ALLOWED_TRANSITIONS,
    transition,
    transition_requirement,
    validate_transition,
)
from riskon.governance.models import PatchStatus


@pytest.mark.parametrize(
    ("previous", "new", "requirement"),
    [
        (PatchStatus.PROPOSED, PatchStatus.TESTED, "PRE_APPROVAL_POLICY_CI"),
        (PatchStatus.TESTED, PatchStatus.AWAITING_APPROVAL, "AUTOMATED_CHECKS_PASS"),
        (PatchStatus.AWAITING_APPROVAL, PatchStatus.APPROVED, "VALID_HUMAN_APPROVAL"),
        (PatchStatus.APPROVED, PatchStatus.ACTIVE, "EXPLICIT_RELEASE_ACTIVATION"),
        (PatchStatus.TESTED, PatchStatus.REJECTED, "MANDATORY_CHECK_FAIL"),
        (PatchStatus.AWAITING_APPROVAL, PatchStatus.REJECTED, "HUMAN_REJECTION"),
        (PatchStatus.ACTIVE, PatchStatus.EXPIRED, "EFFECTIVE_TO_REACHED"),
    ],
)
def test_allowed_transition_requirements_are_exact(
    previous: PatchStatus,
    new: PatchStatus,
    requirement: str,
) -> None:
    assert transition_requirement(previous, new) == requirement
    assert transition(previous, new) is new


@pytest.mark.parametrize(
    ("previous", "new"),
    [
        (PatchStatus.PROPOSED, PatchStatus.ACTIVE),
        (PatchStatus.TESTED, PatchStatus.ACTIVE),
        (PatchStatus.AWAITING_APPROVAL, PatchStatus.ACTIVE),
        (PatchStatus.REJECTED, PatchStatus.APPROVED),
        (PatchStatus.REJECTED, PatchStatus.ACTIVE),
        (PatchStatus.EXPIRED, PatchStatus.ACTIVE),
        (PatchStatus.ACTIVE, PatchStatus.APPROVED),
        (PatchStatus.APPROVED, PatchStatus.REJECTED),
    ],
)
def test_forbidden_shortcuts_fail_closed(previous: PatchStatus, new: PatchStatus) -> None:
    assert transition_requirement(previous, new) is None
    with pytest.raises(InvalidLifecycleTransitionError, match="Forbidden"):
        validate_transition(previous, new)
    with pytest.raises(InvalidLifecycleTransitionError):
        transition(previous, new)


def test_transition_table_contains_only_declared_states() -> None:
    assert len(ALLOWED_TRANSITIONS) == 7
    assert {state for pair in ALLOWED_TRANSITIONS for state in pair} <= set(PatchStatus)
