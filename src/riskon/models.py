"""Validated data contracts shared by the M0 pipeline layers."""

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


class Decision(StrEnum):
    """Top-level response decision."""

    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    ABSTAIN = "ABSTAIN"


class NeedType(StrEnum):
    """Structured routing need; routing never inspects raw query text."""

    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"
    ROUTINE_PROCESS = "ROUTINE_PROCESS"
    SYSTEM_GUIDANCE = "SYSTEM_GUIDANCE"
    COMPLEX_CASE = "COMPLEX_CASE"
    POLICY_INTERPRETATION = "POLICY_INTERPRETATION"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    UNKNOWN = "UNKNOWN"


class ReasonCode(StrEnum):
    """Deterministic reasons for clarification, abstention, or routing."""

    MISSING_REQUIRED_CONTEXT = "MISSING_REQUIRED_CONTEXT"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE"
    NO_RELEVANT_EVIDENCE = "NO_RELEVANT_EVIDENCE"
    OPEN_EVIDENCE = "OPEN_EVIDENCE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    POLICY_INTERPRETATION = "POLICY_INTERPRETATION"
    AMBIGUOUS_ACRONYM = "AMBIGUOUS_ACRONYM"
    NO_EXPLICIT_SUPPORT = "NO_EXPLICIT_SUPPORT"
    UNRESOLVED_REQUIRED_REFERENCE = "UNRESOLVED_REQUIRED_REFERENCE"
    UNSUPPORTED_MODALITY = "UNSUPPORTED_MODALITY"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"


class QueryIntent(StrEnum):
    """Closed M2 query-planning intent vocabulary."""

    DEFINITION = "DEFINITION"
    APPLICABILITY = "APPLICABILITY"
    PROCEDURE = "PROCEDURE"
    ALERT_RESOLUTION = "ALERT_RESOLUTION"
    CONFIGURATION_LOOKUP = "CONFIGURATION_LOOKUP"
    REFERENCE_LOOKUP = "REFERENCE_LOOKUP"


class RetrievalChannel(StrEnum):
    """M2 structure-aware retrieval channels."""

    EXACT = "EXACT"
    WORD_TFIDF = "WORD_TFIDF"
    CHAR_TFIDF = "CHAR_TFIDF"
    TABLE_ROW = "TABLE_ROW"


class QueryInput(BaseModel):
    """Input accepted by :class:`RiskonPipeline`."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    context: dict[str, str] = Field(default_factory=dict)
    trace_id: str | None = None


class ManifestEntry(BaseModel):
    """One row from the synthetic workbook manifest."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    title: str
    url: str
    source_path: str


class ListBlock(BaseModel):
    """An ordered or unordered list preserved from an HTML section."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    items: list[str]


class TableData(BaseModel):
    """A table with headers and every data row preserved."""

    model_config = ConfigDict(extra="forbid")

    headers: list[str]
    rows: list[list[str]]
    claim_ids: list[str | None] = Field(default_factory=list)
    row_scopes: list[dict[str, str]] = Field(default_factory=list)


class LinkRef(BaseModel):
    """A local or synthetic link found in an HTML page."""

    model_config = ConfigDict(extra="forbid")

    text: str
    href: str


class ImageRef(BaseModel):
    """An image reference retained without interpreting image content."""

    model_config = ConfigDict(extra="forbid")

    src: str
    alt: str


class Section(BaseModel):
    """A heading-scoped searchable unit created by HTML ingestion."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    filename: str
    title: str
    source_ref: str
    heading_path: list[str]
    text: str
    paragraphs: list[str]
    lists: list[ListBlock]
    tables: list[TableData]
    links: list[LinkRef]
    images: list[ImageRef]
    scope: dict[str, str] = Field(default_factory=dict)
    intents: list[str] = Field(default_factory=list)
    claims: dict[str, str] = Field(default_factory=dict)


class RetrievalHit(BaseModel):
    """Stable retrieval result, including zero-score top-k candidates."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    source_ref: str
    title: str
    heading_path: list[str]
    score: float
    excerpt: str
    table_rows: list[list[str]]


class Evidence(BaseModel):
    """Evidence admitted by the deterministic evidence gate."""

    model_config = ConfigDict(extra="forbid")

    section_id: str
    source_ref: str
    title: str
    heading_path: list[str]
    score: float
    excerpt: str
    table_rows: list[list[str]]


class QueryPlan(BaseModel):
    """Deterministic M2 query-normalisation and retrieval plan."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    original_query: str
    normalised_query: str
    intent: QueryIntent
    canonical_terms: list[str]
    required_context_fields: list[str]
    missing_context_fields: list[str]
    subqueries: list[str]
    retrieval_channels: list[RetrievalChannel]
    retrieval_skipped: bool


class RetrievalDiagnostic(BaseModel):
    """One deterministic M2 channel candidate and fusion decision."""

    model_config = ConfigDict(extra="forbid")

    plan_id: str
    subquery: str
    channel: RetrievalChannel
    candidate_ref: str
    channel_rank: int
    raw_score: float
    rrf_contribution: float
    final_rank: int | None
    included: bool
    exclusion_reason: str | None


class RetrievalDiagnostics(BaseModel):
    """M2 diagnostics retained alongside a verified run."""

    model_config = ConfigDict(extra="forbid")

    entries: list[RetrievalDiagnostic] = Field(default_factory=list)


class DetectedContext(BaseModel):
    """Structured context extracted before evidence evaluation."""

    model_config = ConfigDict(extra="forbid")

    region: str | None = None
    channel: str | None = None
    workflow_stage: str | None = None
    need_type: NeedType = NeedType.UNKNOWN
    missing_context: list[str] = Field(default_factory=list)


class EvidenceCheck(BaseModel):
    """Result of applying the deterministic evidence gate."""

    model_config = ConfigDict(extra="forbid")

    reason_codes: list[ReasonCode] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)
    relevant_evidence: list[Evidence] = Field(default_factory=list)


class Route(BaseModel):
    """Optional expert route attached only to an abstention."""

    model_config = ConfigDict(extra="forbid")

    support_function: str
    expert_id: str | None = None
    routing_reason: str
    routing_confidence: float = Field(ge=0.0, le=1.0)


class AnswerClaim(BaseModel):
    """Internal M1 claim with local evidence references."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    evidence_refs: list[str]
    critical: bool = False


class VerificationStatus(StrEnum):
    """M1 evidence-contract status."""

    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class VerificationReport(BaseModel):
    """Exact M1 verification report contract."""

    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    reason_codes: list[ReasonCode]
    supported_claim_ids: list[str]
    unsupported_claim_ids: list[str]
    missing_required_claim_ids: list[str]
    scope_mismatches: list[str]
    unresolved_required_references: list[str]
    unsupported_modalities: list[str]
    evidence_refs: list[str]
    explanation: str
    _claims: list[AnswerClaim] = PrivateAttr(default_factory=list)

    @property
    def claims(self) -> tuple[AnswerClaim, ...]:
        """Expose internal claims without changing serialized report fields."""

        return tuple(self._claims)


class PipelineResult(BaseModel):
    """Public result contract with enforced ANSWER/CLARIFY/ABSTAIN invariants."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    decision: Decision
    answer: str | None = None
    clarifying_question: str | None = None
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    route: Route | None = None
    answer_confidence: float = Field(ge=0.0, le=1.0)
    routing_confidence: float = Field(ge=0.0, le=1.0)
    confidence_kind: str
    detected_context: DetectedContext
    missing_context: list[str] = Field(default_factory=list)
    retrieved_sections: list[RetrievalHit] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_decision_contract(self) -> Self:
        if self.decision is Decision.ANSWER:
            if not self.answer or not self.evidence:
                raise ValueError("ANSWER requires an answer and at least one evidence item")
            if self.clarifying_question is not None or self.route is not None:
                raise ValueError("ANSWER cannot contain clarification or routing")
        elif self.decision is Decision.CLARIFY:
            if not self.clarifying_question or self.answer is not None or self.route is not None:
                raise ValueError("CLARIFY requires one question and no answer or route")
        else:
            if not self.reason_codes or self.route is None or self.answer is not None:
                raise ValueError("ABSTAIN requires a reason, route, and no speculative answer")
        return self


class VerifiedRun(BaseModel):
    """M1 result plus its machine-verifiable evidence report."""

    model_config = ConfigDict(extra="forbid")

    result: PipelineResult
    verification: VerificationReport


class PlannedVerifiedRun(BaseModel):
    """M2 query plan and retrieval trace plus the existing M1 result contract."""

    model_config = ConfigDict(extra="forbid")

    query_plan: QueryPlan
    retrieval_diagnostics: RetrievalDiagnostics
    verified_run: VerifiedRun


class RouteMode(StrEnum):
    """M3 person or functional-queue route mode."""

    PERSON = "PERSON"
    FUNCTIONAL_QUEUE = "FUNCTIONAL_QUEUE"


class RoutingStatus(StrEnum):
    """M3 routing diagnostic status."""

    ROUTED = "ROUTED"
    NOT_ROUTED_DECISION = "NOT_ROUTED_DECISION"
    BLOCKED = "BLOCKED"


class RoutingContext(BaseModel):
    """Structured M3 routing context; it carries no raw query text."""

    model_config = ConfigDict(extra="forbid")

    need_type: NeedType
    reason_codes: list[ReasonCode]
    topics: list[str] = Field(default_factory=list)
    jurisdiction: str | None = None
    region: str | None = None
    system: str | None = None
    requester_team: str | None = None


class RoutingRequest(BaseModel):
    """Only public input accepted by the configurable expert router."""

    model_config = ConfigDict(extra="forbid")

    need_type: NeedType
    reason_codes: list[ReasonCode]
    topics: list[str] = Field(default_factory=list)
    jurisdiction: str | None = None
    region: str | None = None
    system: str | None = None
    requester_team: str | None = None
    routing_profile: str


class RoutingCandidateDiagnostic(BaseModel):
    """One M3 expert candidate, including hard-gate or score evidence."""

    model_config = ConfigDict(extra="forbid")

    expert_id: str
    eligible: bool
    exclusion_reason: str | None = None
    component_scores: dict[str, float] = Field(default_factory=dict)
    total_score: float | None = Field(default=None, ge=0.0, le=1.0)
    rank: int | None = Field(default=None, ge=1)
    mandate_specificity: float = Field(ge=0.0, le=1.0)


class RoutingAlternative(BaseModel):
    """Structured explanation for a non-selected eligible candidate."""

    model_config = ConfigDict(extra="forbid")

    expert_id: str
    rank: int
    total_score: float = Field(ge=0.0, le=1.0)
    reason: str


class RoutingExclusion(BaseModel):
    """Structured explanation for a hard-gated candidate."""

    model_config = ConfigDict(extra="forbid")

    expert_id: str
    reason: str


class RoutingExplanation(BaseModel):
    """Machine-readable M3 routing explanation; no free-form LLM text."""

    model_config = ConfigDict(extra="forbid")

    function_reason: str
    hard_constraints_applied: list[str]
    selected_candidate_factors: dict[str, float] = Field(default_factory=dict)
    alternative_candidates: list[RoutingAlternative] = Field(default_factory=list)
    excluded_candidates: list[RoutingExclusion] = Field(default_factory=list)
    fallback_reason: str | None = None
    decisive_factors: list[str] = Field(default_factory=list)


class ExpertRoute(BaseModel):
    """M3 configurable expert or functional-queue route."""

    model_config = ConfigDict(extra="forbid")

    support_function: str
    route_mode: RouteMode
    selected_expert_id: str | None = None
    queue_id: str | None = None
    candidate_expert_ids: list[str] = Field(default_factory=list)
    routing_confidence: float = Field(ge=0.0, le=1.0)
    confidence_kind: str
    support_model_version: str
    expected_fallback_reason: str | None = None
    explanation: RoutingExplanation


class RoutingDiagnostics(BaseModel):
    """M3 routing trace and structured explanation."""

    model_config = ConfigDict(extra="forbid")

    status: RoutingStatus
    routing_request: RoutingRequest | None = None
    support_function: str | None = None
    legacy_route_function: str | None = None
    support_model_version: str | None = None
    route_mode: RouteMode | None = None
    selected_expert_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    candidates: list[RoutingCandidateDiagnostic] = Field(default_factory=list)
    explanation: RoutingExplanation | None = None


class RoutedRun(BaseModel):
    """M3 routing result layered over an immutable planned verified run."""

    model_config = ConfigDict(extra="forbid")

    planned_verified_run: PlannedVerifiedRun
    expert_route: ExpertRoute | None = None
    routing_diagnostics: RoutingDiagnostics
