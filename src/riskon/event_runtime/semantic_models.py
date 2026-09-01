"""Typed contracts for the Task 4 semantic retrieval metadata path."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PageCardPayload(BaseModel):
    """Small LLM-produced page metadata record; it is never answer evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=240)
    purpose: str = Field(min_length=1, max_length=240)
    topics: list[str] = Field(max_length=8)
    acronyms: list[str] = Field(max_length=12)
    likely_scope_terms: list[str] = Field(max_length=12)
    contains_table: bool
    contains_visual: bool


class PageCard(PageCardPayload):
    """Cached page metadata bound to one source hash and local source reference."""

    source_ref: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class PageCardDocument(BaseModel):
    """Generated page-card cache; source content is intentionally absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    model: str = Field(min_length=1)
    complete: bool = False
    cards: list[PageCard]


class RouterSelection(BaseModel):
    """One LLM page-routing suggestion, never a source citation or answer claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_ref: str = Field(min_length=1)
    rank: int = Field(ge=1, le=10)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=160)


class RouterOutput(BaseModel):
    """Strict structured output expected from the title router."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    selections: list[RouterSelection] = Field(min_length=1, max_length=10)


class SemanticFailureReason(StrEnum):
    """Bounded reasons that permit exactly one router retry."""

    NO_DIRECT_SUPPORT = "NO_DIRECT_SUPPORT"
    WRONG_SCOPE = "WRONG_SCOPE"
    WRONG_PAGE = "WRONG_PAGE"


class SufficiencyStatus(StrEnum):
    """Result of the deterministic lightweight post-retrieval sufficiency check."""

    SUFFICIENT = "SUFFICIENT"
    RETRY = "RETRY"


class EvidenceSufficiency(BaseModel):
    """Routing-only sufficiency result; it does not authorize an answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: SufficiencyStatus
    reason: SemanticFailureReason | None = None
    detail: str = Field(min_length=1, max_length=240)
