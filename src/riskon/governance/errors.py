"""Fail-closed errors raised by the M5B governance boundary."""


class GovernanceError(RuntimeError):
    """Base class for safe, user-actionable governance failures."""


class MandatoryPolicyChecksFailedError(GovernanceError):
    """Raised when approval attempts to override a failed mandatory check."""

    def __init__(self, failed_check_ids: list[str] | tuple[str, ...]) -> None:
        self.failed_check_ids = tuple(failed_check_ids)
        joined = ", ".join(self.failed_check_ids) or "unknown"
        super().__init__(f"Mandatory Policy CI checks failed: {joined}")


class SelfApprovalError(GovernanceError):
    """Raised when the resolution author attempts to approve the patch."""


class InvalidLifecycleTransitionError(GovernanceError):
    """Raised for a transition outside the frozen M5B state machine."""


class OfficialCorpusMutationError(GovernanceError):
    """Raised if an operation would write to the official corpus."""


class ReferenceResolutionError(GovernanceError):
    """Raised when a claimed evidence reference is not local and resolvable."""


class MissingHumanApprovalError(GovernanceError):
    """Raised when activation is attempted without an independent human record."""


class ReleaseActivationError(GovernanceError):
    """Raised when an explicit release cannot be activated safely."""


class ExpiredPatchError(ReleaseActivationError):
    """Raised when an expired patch is selected for an active release."""
