"""Validated contracts for the event-corpus evaluation boundary."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventExpectedBehavior(StrEnum):
    """Expected top-level behavior for one event question."""

    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    ABSTAIN_ROUTE = "ABSTAIN_ROUTE"


class EventEvalCase(BaseModel):
    """One human-reviewed event question and its deterministic checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    input_context: dict[str, str] = Field(default_factory=dict)
    expected_behavior: EventExpectedBehavior
    expected_source_title_contains: list[str] = Field(default_factory=list)
    required_answer_concepts: list[str] = Field(default_factory=list)
    forbidden_answer_concepts: list[str] = Field(default_factory=list)
    requires_table: bool = False
    requires_image: bool = False
    requires_manual_review: bool = True


class EventCaseSet(BaseModel):
    """Closed-world event evaluation-case envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    suite: str = Field(min_length=1)
    cases: list[EventEvalCase]


class EventCaseResult(BaseModel):
    """Safe result and review material for one event question."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    question: str
    expected_behavior: EventExpectedBehavior
    requires_table: bool = False
    requires_image: bool = False
    requires_manual_review: bool = True
    actual_decision: str | None = None
    route_present: bool = False
    behavior_match: bool = False
    expected_source_title_contains: list[str] = Field(default_factory=list)
    top_source_titles: list[str] = Field(default_factory=list)
    source_hit_rank: int | None = Field(default=None, ge=1)
    citation_valid: bool = False
    broken_reference_count: int = Field(default=0, ge=0)
    unsupported_modality_count: int = Field(default=0, ge=0)
    scope_violation_count: int = Field(default=0, ge=0)
    critical_control_omission_count: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    answer: str | None = None
    clarifying_question: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    route: dict[str, Any] | None = None
    evidence_excerpts: list[str] = Field(default_factory=list)
    failure_codes: list[str] = Field(default_factory=list)
    runtime_error: str | None = None


class EventEvaluationMetrics(BaseModel):
    """Required baseline metrics for the 17-case event evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cases_executed: int = Field(ge=0)
    decision_match_count: int = Field(ge=0)
    source_hit_at_1: int = Field(ge=0)
    source_hit_at_5: int = Field(ge=0)
    source_hit_at_10: int = Field(ge=0)
    citation_validity: float = Field(ge=0.0, le=1.0)
    clarification_match_count: int = Field(ge=0)
    answer_count: int = Field(ge=0)
    clarify_count: int = Field(ge=0)
    abstain_count: int = Field(ge=0)
    routed_count: int = Field(ge=0)
    table_required_count: int = Field(ge=0)
    image_required_count: int = Field(ge=0)
    unsupported_modality_count: int = Field(ge=0)
    scope_violation_count: int = Field(ge=0)
    critical_control_omission_count: int = Field(ge=0)
    broken_reference_count: int = Field(ge=0)
    median_latency_ms: float = Field(ge=0.0)
    runtime_error_count: int = Field(ge=0)
    manual_review_case_count: int = Field(ge=0)


class EventEvaluationDocument(BaseModel):
    """Machine-readable event evaluation report."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    suite: str
    metrics: EventEvaluationMetrics
    case_results: list[EventCaseResult]
    network_enabled: bool
    event_data_copied: bool
