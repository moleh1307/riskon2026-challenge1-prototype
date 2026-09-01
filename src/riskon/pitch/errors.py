"""Typed failures for the ER-C pitch package."""


class PitchError(ValueError):
    """Base class for safe, actionable pitch-package failures."""


class PitchContractError(PitchError):
    """Raised when a frozen ER-C contract is incomplete or inconsistent."""


class PitchSourceError(PitchError):
    """Raised when a required local ER-B source artifact is unavailable."""


class PitchSecurityError(PitchError):
    """Raised when an output violates the local-only artifact boundary."""
