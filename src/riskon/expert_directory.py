"""Synthetic expert-directory and network-edge loaders for M3."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ExpertProfile(BaseModel):
    """One synthetic expert profile with all M3 hard-gate fields."""

    model_config = ConfigDict(extra="forbid")

    expert_id: str
    display_name: str
    active: bool
    effective_from: str
    effective_to: str
    support_function: str
    mandates: list[str]
    topics: list[str]
    jurisdictions: list[str]
    regions: list[str]
    systems: list[str]
    network_node: str
    workload_ratio: float = Field(ge=0.0, le=1.0)
    accepting_new_cases: bool
    queue_id: str
    mandate_specificity: float = Field(ge=0.0, le=1.0)


class ExpertDirectory(BaseModel):
    """Versioned synthetic expert directory."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    expert_directory_version: str
    profiles: list[ExpertProfile]

    @classmethod
    def from_file(cls, path: Path) -> "ExpertDirectory":
        """Load one local expert-directory JSON file."""

        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def queue_for_support_function(self, support_function: str) -> str | None:
        """Return the stable queue associated with a support function."""

        for profile in self.profiles:
            if profile.support_function == support_function:
                return profile.queue_id
        return None

    def queue_for_expert_id(self, expert_id: str) -> str | None:
        """Return the queue attached to one selected synthetic expert."""

        for profile in self.profiles:
            if profile.expert_id == expert_id:
                return profile.queue_id
        return None


class NetworkEdge(BaseModel):
    """One synthetic requester-team to expert-node edge."""

    model_config = ConfigDict(extra="forbid")

    requester_team: str
    network_node: str
    weight: float = Field(ge=0.0, le=1.0)


class NetworkDirectory(BaseModel):
    """Versioned synthetic network edge directory."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    network_version: str
    edges: list[NetworkEdge]

    @classmethod
    def from_file(cls, path: Path) -> "NetworkDirectory":
        """Load the local synthetic network-edge file."""

        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def weight(self, requester_team: str, network_node: str) -> float:
        """Return an edge weight or zero for an absent synthetic edge."""

        for edge in self.edges:
            if edge.requester_team == requester_team and edge.network_node == network_node:
                return edge.weight
        return 0.0
