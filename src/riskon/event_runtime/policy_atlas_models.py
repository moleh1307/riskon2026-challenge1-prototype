"""Strict contracts for the Task 6 Policy Atlas and eligibility metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

POLICY_ATLAS_MODEL: str = "gpt-5.6-luna"
POLICY_ATLAS_REASONING: Literal["low"] = "low"
ELIGIBILITY_MODEL: str = "gpt-5.6-terra"
ELIGIBILITY_REASONING: Literal["medium"] = "medium"


class ScopeConstraint(BaseModel):
    """One source-declared scope dimension used only as routing metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=160)


class PolicyFingerprintPayload(BaseModel):
    """LLM-produced metadata for one page; it is never answer evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    purpose: str = Field(min_length=1, max_length=200)
    answerable_questions: list[str] = Field(min_length=3, max_length=5)
    anti_questions: list[str] = Field(min_length=2, max_length=3)
    required_context_fields: list[str] = Field(max_length=12)
    explicit_scope_constraints: list[ScopeConstraint] = Field(max_length=12)
    critical_controls: list[str] = Field(max_length=12)
    acronyms: list[str] = Field(max_length=12)
    confusable_with: list[str] = Field(max_length=8)


class PolicyFingerprint(PolicyFingerprintPayload):
    """Source-bound Policy Atlas fingerprint."""

    title: str = Field(min_length=1, max_length=240)
    source_ref: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=240)
    contains_table: bool
    contains_visual: bool
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PolicyAtlasDocument(BaseModel):
    """Complete or resumable source-hash-aware Policy Atlas cache."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    model: str = Field(min_length=1)
    complete: bool = False
    fingerprints: list[PolicyFingerprint]


class GraphEdgeType(StrEnum):
    """Closed answerability graph edge vocabulary."""

    RELATED_TO = "RELATED_TO"
    CONFUSABLE_WITH = "CONFUSABLE_WITH"
    SCOPE_ALTERNATIVE = "SCOPE_ALTERNATIVE"
    WORKFLOW_ALTERNATIVE = "WORKFLOW_ALTERNATIVE"
    SUPPORTS_CONTEXT = "SUPPORTS_CONTEXT"
    SUPPORTING_PROCEDURE = "SUPPORTING_PROCEDURE"


class AnswerabilityGraphNode(BaseModel):
    """One source page node bound to its current source hash."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_ref: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=240)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class AnswerabilityGraphEdge(BaseModel):
    """One deterministic graph relationship between two page nodes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_ref: str = Field(min_length=1, max_length=500)
    target_ref: str = Field(min_length=1, max_length=500)
    edge_type: GraphEdgeType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=240)


class AnswerabilityGraphDocument(BaseModel):
    """Lightweight graph metadata; it contains no source evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    nodes: list[AnswerabilityGraphNode]
    edges: list[AnswerabilityGraphEdge]


class EligibilityStatus(StrEnum):
    """Contrastive page eligibility status; never a final answer decision."""

    ELIGIBLE = "ELIGIBLE"
    NEEDS_CONTEXT = "NEEDS_CONTEXT"
    INELIGIBLE_SCOPE = "INELIGIBLE_SCOPE"
    INELIGIBLE_NO_DIRECT_SUPPORT = "INELIGIBLE_NO_DIRECT_SUPPORT"


class EligibilityDecision(BaseModel):
    """One contrastive eligibility assessment for a supplied page candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_ref: str = Field(min_length=1, max_length=500)
    status: EligibilityStatus
    why_can_answer: str = Field(min_length=1, max_length=300)
    why_not_authoritative: str = Field(min_length=1, max_length=300)
    missing_context_fields: list[str] = Field(max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)
    anti_question_warning: bool


class ContrastiveEligibilityOutput(BaseModel):
    """Strict batch output from the fixed Terra eligibility model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decisions: list[EligibilityDecision] = Field(min_length=1, max_length=10)


@dataclass(frozen=True)
class AtlasRoutingResult:
    """Validated routing metadata used to shape, never authorize, evidence retrieval."""

    decisions: tuple[EligibilityDecision, ...] = ()
    ranked_page_refs: tuple[str, ...] = ()
    excluded_page_refs: tuple[str, ...] = ()
    graph_neighbor_refs: tuple[str, ...] = ()
    expected_control_hints: tuple[str, ...] = ()
    supporting_procedure_refs: tuple[str, ...] = ()
    scope_alternative_refs: tuple[str, ...] = ()
    clarification_fields: tuple[str, ...] = ()
    call: object | None = None


__all__ = [
    "AnswerabilityGraphDocument",
    "AnswerabilityGraphEdge",
    "AnswerabilityGraphNode",
    "AtlasRoutingResult",
    "ContrastiveEligibilityOutput",
    "ELIGIBILITY_MODEL",
    "ELIGIBILITY_REASONING",
    "EligibilityDecision",
    "EligibilityStatus",
    "GraphEdgeType",
    "POLICY_ATLAS_MODEL",
    "POLICY_ATLAS_REASONING",
    "PolicyAtlasDocument",
    "PolicyFingerprint",
    "PolicyFingerprintPayload",
    "ScopeConstraint",
]
