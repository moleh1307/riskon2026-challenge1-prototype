"""Signal-driven worker selection for the bounded M4B orchestra."""

from riskon.orchestra.models import AgentTask, RiskSignal
from riskon.orchestra.policy import WorkerSelectionPolicy
from riskon.orchestra.tasks import AgentCatalog, build_agent_tasks


class WorkerSelector:
    """Select and construct workers from policy signals, never case IDs."""

    def __init__(self, policy: WorkerSelectionPolicy, catalog: AgentCatalog) -> None:
        self.policy = policy
        self.catalog = catalog

    def select_roles(self, signals: tuple[RiskSignal, ...] | list[RiskSignal]) -> list[str]:
        """Return the policy union in canonical role order."""

        return self.policy.required_agent_roles(signals)

    def build_tasks(
        self,
        plan_id: str,
        signals: tuple[RiskSignal, ...] | list[RiskSignal],
        *,
        input_refs: list[str] | None = None,
        allow_counterfactual: bool = False,
        requested_roles: list[str] | None = None,
    ) -> list[AgentTask]:
        """Build deterministic tasks for the selected roles."""

        roles = list(requested_roles) if requested_roles is not None else self.select_roles(signals)
        return build_agent_tasks(
            plan_id,
            roles,
            self.catalog,
            input_refs=input_refs,
            allow_counterfactual=allow_counterfactual,
        )
