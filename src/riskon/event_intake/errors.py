"""Typed failures for the ER-A event corpus adapter."""


class EventIntakeError(ValueError):
    """Base error for deterministic event corpus operations."""


class ManifestError(EventIntakeError):
    """Raised when a manifest cannot be safely interpreted."""


class CorpusBlockedError(EventIntakeError):
    """Raised by callers that require a prepared corpus but received none."""


class UnsafePathError(EventIntakeError):
    """Raised for a path that would escape the declared source root."""


class SmokeCaseError(EventIntakeError):
    """Raised when a smoke-case file violates its closed schema."""
