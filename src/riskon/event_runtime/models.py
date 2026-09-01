"""Typed public records for the external event runtime boundary."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventQueryPayload(BaseModel):
    """Safe terminal payload for one event-corpus query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: str = Field(min_length=1)
    answer: str | None = None
    clarification: str | None = None
    abstention_reason: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    route: dict[str, Any] | None = None
    activation_profile: str = Field(min_length=1)
    worker_roles: list[str] = Field(default_factory=list)
    worker_execution_count: int = Field(ge=0)
