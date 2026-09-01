"""Frozen M4B agent catalog and deterministic task construction."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field

from riskon.orchestra.models import AgentTask, ExecutionWave


class AgentSpec(BaseModel):
    """Validated catalog entry for one deterministic agent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    backend: str = Field(min_length=1)
    enabled: bool
    may_delegate: bool
    allowed_delegate_ids: list[str]
    maximum_delegation_depth: int = Field(ge=0)
    final_decision_authority: bool
    allowed_inputs: list[str]
    allowed_tools: list[str]
    forbidden_capabilities: list[str]


class AgentCatalog:
    """Read-only worker-agent directory loaded from the synthetic catalog."""

    def __init__(self, agents: tuple[AgentSpec, ...], source_path: Path) -> None:
        self.source_path = source_path
        by_role = {agent.role: agent.model_copy(deep=True) for agent in agents}
        if len(by_role) != len(agents):
            raise ValueError("M4 agent catalog roles must be unique")
        self._by_role = MappingProxyType(by_role)

    @classmethod
    def from_file(cls, path: Path) -> AgentCatalog:
        """Load the closed deterministic agent catalog."""

        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"M4 agent catalog not found: {resolved}")
        try:
            raw_value = json.loads(resolved.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid M4 agent catalog: {exc}") from exc
        if not isinstance(raw_value, dict) or set(raw_value) != {
            "schema_version",
            "backend",
            "agents",
        }:
            raise ValueError("M4 agent catalog fields do not match the frozen schema")
        if raw_value.get("schema_version") != "1.0":
            raise ValueError("Unsupported M4 agent catalog schema")
        if raw_value.get("backend") != "DETERMINISTIC_FIXTURE_V1":
            raise ValueError("M4 agent catalog backend is not deterministic")
        raw_agents = raw_value.get("agents")
        if not isinstance(raw_agents, list):
            raise ValueError("M4 agent catalog agents must be an array")
        try:
            agents = tuple(AgentSpec.model_validate(item) for item in raw_agents)
        except Exception as exc:
            raise ValueError(f"Invalid M4 agent catalog: {exc}") from exc
        return cls(agents, resolved)

    @property
    def agents(self) -> tuple[AgentSpec, ...]:
        """Return detached catalog entries."""

        return tuple(agent.model_copy(deep=True) for agent in self._by_role.values())

    def for_role(self, role: str) -> AgentSpec:
        """Return one worker entry and enforce worker-only authority limits."""

        agent = self._by_role.get(role)
        if agent is None:
            raise ValueError(f"M4 agent role is not present in the catalog: {role}")
        if not agent.enabled:
            raise ValueError(f"M4 agent role is disabled: {role}")
        if agent.role == "CONDUCTOR":
            raise ValueError("CONDUCTOR is not a worker task role")
        if agent.may_delegate or agent.final_decision_authority:
            raise ValueError(f"M4 worker role violates delegation/authority boundary: {role}")
        if agent.maximum_delegation_depth != 0:
            raise ValueError(f"M4 worker role has non-zero delegation depth: {role}")
        return agent.model_copy(deep=True)


ROLE_OBJECTIVES = MappingProxyType(
    {
        "EVIDENCE_SCOUT": "Find explicit local source support for the requested claim.",
        "SCOPE_SENTINEL": "Check explicit source scope and identify scope conflicts.",
        "PROCESS_TABLE_SCOUT": "Recover complete structure-aware table rows and states.",
        "SKEPTIC": "Challenge candidate claims for support, scope, safety, and contradiction.",
        "COUNTERFACTUAL_SENTINEL": "Check decision transitions after one bounded context change.",
    }
)


def build_agent_tasks(
    plan_id: str,
    roles: list[str],
    catalog: AgentCatalog,
    *,
    input_refs: list[str] | None = None,
    allow_counterfactual: bool = False,
) -> list[AgentTask]:
    """Build the canonical discovery-then-challenge task graph."""

    refs = list(input_refs or [])
    tasks: list[AgentTask] = []
    if "COUNTERFACTUAL_SENTINEL" in roles and not allow_counterfactual:
        raise ValueError(
            "No deterministic objective is defined for worker role: COUNTERFACTUAL_SENTINEL"
        )
    ordered_roles = [role for role in roles if role not in {"SKEPTIC", "COUNTERFACTUAL_SENTINEL"}]
    ordered_roles.extend(role for role in roles if role == "SKEPTIC")
    ordered_roles.extend(role for role in roles if role == "COUNTERFACTUAL_SENTINEL")
    for role in ordered_roles:
        objective = ROLE_OBJECTIVES.get(role)
        if objective is None:
            raise ValueError(f"No deterministic objective is defined for worker role: {role}")
        agent = catalog.for_role(role)
        if role == "SKEPTIC":
            wave = ExecutionWave.CHALLENGE
        elif role == "COUNTERFACTUAL_SENTINEL":
            wave = ExecutionWave.VALIDATION
        else:
            wave = ExecutionWave.DISCOVERY
        tasks.append(
            AgentTask(
                task_id=f"task:{plan_id}:{role.lower()}",
                plan_id=plan_id,
                agent_id=agent.agent_id,
                agent_role=role,
                execution_wave=wave,
                objective=objective,
                allowed_tools=list(agent.allowed_tools),
                input_refs=refs,
            )
        )
    return tasks
