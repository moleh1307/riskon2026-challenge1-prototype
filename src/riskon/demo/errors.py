"""Errors raised at the ER-B demo boundary."""


class DemoContractError(ValueError):
    """Raised when runtime output cannot satisfy the frozen presentation contract."""


class DemoSecurityError(RuntimeError):
    """Raised when a generated demo would violate the local-only boundary."""
