"""Strict structured contracts for the Task 5 evidence-reasoning path."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTEXT_INTERPRETER_MODEL: str = "gpt-5.6-luna"
CONTEXT_INTERPRETER_REASONING: Literal["low"] = "low"
CLAIM_BUILDER_MODEL: str = "gpt-5.6-terra"
CLAIM_BUILDER_REASONING: Literal["medium"] = "medium"
SKEPTIC_MODEL: str = "gpt-5.6-terra"
SKEPTIC_REASONING: Literal["medium"] = "medium"


class EvidenceSufficiencyStatus(StrEnum):
    """Evidence analyst outcome used by the bounded retry gate."""

    SUFFICIENT = "SUFFICIENT"
    NO_DIRECT_SUPPORT = "NO_DIRECT_SUPPORT"
    WRONG_SCOPE = "WRONG_SCOPE"
    WRONG_PAGE = "WRONG_PAGE"
    VISUAL_REQUIRED = "VISUAL_REQUIRED"


# Short public spelling used by callers that treat the field as an enum contract.
EvidenceSufficiency = EvidenceSufficiencyStatus


class EvidenceClaimKind(StrEnum):
    """Closed kinds of claims that may cross the local evidence boundary."""

    DIRECT = "DIRECT"
    SOURCE_LIMIT = "SOURCE_LIMIT"


class SkepticCategory(StrEnum):
    """Closed material-objection categories."""

    SCOPE_LEAKAGE = "SCOPE_LEAKAGE"
    UNSUPPORTED_INFERENCE = "UNSUPPORTED_INFERENCE"
    ACRONYM_MISTAKE = "ACRONYM_MISTAKE"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    CRITICAL_CONTROL_OMITTED = "CRITICAL_CONTROL_OMITTED"
    IRRELEVANT_EXTRA = "IRRELEVANT_EXTRA"
    MISSING_REQUIRED_CONTEXT = "MISSING_REQUIRED_CONTEXT"


class ContextInterpreterOutput(BaseModel):
    """LLM context interpretation; values are revalidated deterministically."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str = Field(min_length=1, max_length=120)
    explicitly_supplied_context: list[ContextField]
    answer_changing_context_fields: list[str] = Field(max_length=16)
    missing_context_fields: list[str] = Field(max_length=16)
    ambiguity_acronym_flags: list[str] = Field(max_length=16)


class SupportingSpan(BaseModel):
    """A literal source span that must be found in the original local unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str = Field(min_length=1, max_length=500)
    span: str = Field(min_length=1, max_length=2000)


class ContextField(BaseModel):
    """One explicit context key/value pair in an LLM-safe fixed object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=160)


class ScopeField(BaseModel):
    """One claim scope key/value pair in an LLM-safe fixed object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=160)


class EvidenceClaim(BaseModel):
    """One candidate claim with explicit local refs and copied supporting spans."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(min_length=1, max_length=80)
    claim_text: str = Field(min_length=1, max_length=1200)
    claim_kind: EvidenceClaimKind
    evidence_refs: list[str] = Field(min_length=1, max_length=8)
    supporting_spans: list[SupportingSpan] = Field(min_length=1, max_length=8)
    critical_control: bool
    applicable_scope: list[ScopeField] = Field(max_length=16)

    @model_validator(mode="before")
    @classmethod
    def _default_claim_kind(cls, value: Any) -> Any:
        """Keep legacy callers direct while retaining a fully required API schema."""

        if isinstance(value, dict) and "claim_kind" not in value:
            return {**value, "claim_kind": EvidenceClaimKind.DIRECT}
        return value

    @property
    def text(self) -> str:
        """Expose the common AnswerClaim-compatible spelling."""

        return self.claim_text


class EvidenceAnalysisOutput(BaseModel):
    """Strict Claim Builder output; it never decides the released response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_sufficiency: EvidenceSufficiencyStatus
    # The LLM Claim Builder remains bounded by Task5LLMConfig.max_claims.  The
    # deterministic structural fast path may admit one direct claim per matrix
    # cell, so its validated container must not impose the LLM's smaller budget.
    material_claims: list[EvidenceClaim] = Field(max_length=64)
    unresolved_issues: list[str] = Field(max_length=12)


class SkepticObjection(BaseModel):
    """One structured objection to a candidate claim set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_claim_id: str = Field(min_length=1, max_length=80)
    category: SkepticCategory
    material: bool
    detail: str = Field(min_length=1, max_length=500)
    evidence_refs: list[str] = Field(max_length=8)


class SkepticOutput(BaseModel):
    """Strict skeptic output; the deterministic firewall interprets it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    objections: list[SkepticObjection] = Field(max_length=16)


class EvidenceUnit(BaseModel):
    """Bounded original evidence supplied to Claim Builder and Skeptic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str = Field(min_length=1, max_length=500)
    kind: str = Field(min_length=1, max_length=40)
    source_ref: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=240)
    filename: str = Field(min_length=1, max_length=240)
    heading_path: list[str] = Field(default_factory=list, max_length=20)
    text: str = Field(max_length=12000)
    headers: list[str] = Field(default_factory=list, max_length=32)
    row: list[str] = Field(default_factory=list, max_length=32)
    scope: dict[str, str] = Field(default_factory=dict)
    contains_visual: bool = False
    structured_html: bool = False
    truncated: bool = False


class ContextAssessment(BaseModel):
    """Deterministically sanitized context interpretation used by the firewall."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str = Field(min_length=1, max_length=120)
    explicitly_supplied_context: dict[str, str] = Field(default_factory=dict)
    answer_changing_context_fields: list[str] = Field(default_factory=list, max_length=16)
    missing_context_fields: list[str] = Field(default_factory=list, max_length=16)
    ambiguity_acronym_flags: list[str] = Field(default_factory=list, max_length=16)


class SupportValidation(BaseModel):
    """Deterministic validation result for all Claim Builder claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    valid_claims: list[EvidenceClaim] = Field(default_factory=list, max_length=64)
    rejected_claim_ids: list[str] = Field(default_factory=list, max_length=64)
    errors: list[str] = Field(default_factory=list, max_length=32)
    scope_violation_count: int = Field(default=0, ge=0)
    unsupported_claim_count: int = Field(default=0, ge=0)
    broken_reference_count: int = Field(default=0, ge=0)


class ValidatedClaim(BaseModel):
    """Claim admitted by the local support and scope checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=1200)
    claim_kind: EvidenceClaimKind = EvidenceClaimKind.DIRECT
    evidence_refs: list[str] = Field(min_length=1, max_length=8)
    supporting_spans: list[SupportingSpan] = Field(min_length=1, max_length=8)
    critical_control: bool = False
    applicable_scope: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "CLAIM_BUILDER_MODEL",
    "CLAIM_BUILDER_REASONING",
    "CONTEXT_INTERPRETER_MODEL",
    "CONTEXT_INTERPRETER_REASONING",
    "ContextAssessment",
    "ContextField",
    "ContextInterpreterOutput",
    "EvidenceAnalysisOutput",
    "EvidenceClaim",
    "EvidenceClaimKind",
    "EvidenceSufficiency",
    "EvidenceSufficiencyStatus",
    "EvidenceUnit",
    "SKEPTIC_MODEL",
    "SKEPTIC_REASONING",
    "ScopeField",
    "SkepticCategory",
    "SkepticObjection",
    "SkepticOutput",
    "SupportValidation",
    "SupportingSpan",
    "ValidatedClaim",
]
