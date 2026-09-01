"""Typed M4A/M4B orchestration errors."""


class OrchestraWorkersNotImplementedError(RuntimeError):
    """Raised when an M4B worker-backed profile is requested in M4A."""

    def __init__(
        self,
        activation_profile: str,
        required_agent_roles: list[str],
        message: str | None = None,
    ) -> None:
        self.activation_profile = activation_profile
        self.required_agent_roles = list(required_agent_roles)
        self.message = message or (
            f"Orchestration profile {activation_profile} requires M4B workers and is not "
            "available in M4A."
        )
        super().__init__(self.message)


class OrchestraWorkerExecutionError(RuntimeError):
    """Raised when one bounded worker fails without exposing source content."""

    def __init__(self, task_id: str, agent_role: str, cause_type: str) -> None:
        self.task_id = task_id
        self.agent_role = agent_role
        self.cause_type = cause_type
        self.message = f"Worker task {task_id} ({agent_role}) failed with cause type {cause_type}."
        super().__init__(self.message)


class CounterfactualDimensionNotImplementedError(ValueError):
    """Raised when a caller requests a dimension outside the M4C registry."""


class RecursiveCounterfactualExecutionError(RuntimeError):
    """Raised when a counterfactual runner would exceed the frozen depth bound."""


class OrchestraConfigurationError(ValueError):
    """Raised when a M4D policy or runtime contract cannot be trusted."""


class OrchestraExecutionBudgetExceededError(RuntimeError):
    """Raised when a M4D structural execution budget would be exceeded."""


class OrchestraFailClosedError(RuntimeError):
    """Raised when a required M4D safety check fails before a safe answer exists."""

    safe_message = "Orchestration safety checks could not be completed. No answer was produced."

    def __init__(
        self,
        *,
        stage: str,
        activation_profile: str,
        baseline_decision: str,
        failed_task_ids: list[str] | tuple[str, ...] = (),
        cause_types: list[str] | tuple[str, ...] = (),
        message: str | None = None,
    ) -> None:
        self.stage = stage
        self.activation_profile = activation_profile
        self.baseline_decision = baseline_decision
        self.failed_task_ids = list(failed_task_ids)
        self.cause_types = list(cause_types)
        self.safe_message = message or self.safe_message
        super().__init__(self.safe_message)
