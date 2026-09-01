"""Typed contracts for the local ER-B demo and evaluation dashboard."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DemoCase(BaseModel):
    """One presentation story mapped to a frozen evaluator case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_case_id: str
    source_milestone: str
    story_kind: str
    title: str
    question: str
    expected_decision: str
    expected_activation_profile: str
    expected_reason_codes: list[str] = Field(default_factory=list)
    expected_agent_roles: list[str] = Field(default_factory=list)
    expected_counterfactuals: list[dict[str, Any]] = Field(default_factory=list)
    expected_route: dict[str, Any] | None = None
    expected_evidence: bool
    expected_clarifying_question: str | None = None
    expected_case_capsule: bool = False
    expected_before: dict[str, Any] | None = None
    expected_after: dict[str, Any] | None = None
    expected_governance_checks: dict[str, Any] | None = None
    presentation_message: str


class ExpectedView(BaseModel):
    """Expected safe fields for a rendered story view."""

    model_config = ConfigDict(extra="allow")

    schema_version: str
    case_id: str
    source_case_id: str
    decision: str
    reason_codes: list[str] = Field(default_factory=list)
    activation_profile: str
    agent_roles: list[str]
    answer_present: bool
    clarifying_question: str | None
    route: dict[str, Any] | None
    evidence_required: bool
    counterfactuals: list[dict[str, Any]]
    governance: dict[str, Any] | None
    audit_reference: str


class EvidenceView(BaseModel):
    """Redacted evidence descriptor suitable for a public demo card."""

    model_config = ConfigDict(extra="forbid")

    source_title: str
    section_heading: str
    provenance_ref: str
    scope: dict[str, str] = Field(default_factory=dict)
    criticality: str
    excerpt: str


class RouteView(BaseModel):
    """Synthetic functional route without real people or contact details."""

    model_config = ConfigDict(extra="forbid")

    support_function: str
    route_mode: str
    queue_id: str | None = None
    selected_expert_id: str | None = None
    routing_reason: str
    routing_confidence: float = Field(ge=0.0, le=1.0)
    confidence_kind: str


class TraceStep(BaseModel):
    """One safe, structured event in the Orchestra timeline."""

    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    stage: str
    actor: str
    detail: str


class CounterfactualView(BaseModel):
    """One visible context transition and its safe decision."""

    model_config = ConfigDict(extra="forbid")

    variant_id: str
    dimension: str
    before: str | None
    after: str | None
    decision: str
    reason_codes: list[str] = Field(default_factory=list)
    passed: bool


class BeforeView(BaseModel):
    """Pre-governance state shown in the governed-evolution story."""

    model_config = ConfigDict(extra="forbid")

    decision: str
    reason_codes: list[str]
    route_present: bool
    route: RouteView | None = None


class GovernanceChecksView(BaseModel):
    """Observed M5B governance counters and approval gates."""

    model_config = ConfigDict(extra="forbid")

    policy_ci: dict[str, int]
    regression: dict[str, int]
    counterfactual_containment: dict[str, int]
    automatic_approval: int = Field(ge=0)
    automatic_activation: int = Field(ge=0)
    human_approval: bool
    release_activation: bool


class GovernanceView(BaseModel):
    """Safe governed-evolution lifecycle for ERB-005."""

    model_config = ConfigDict(extra="forbid")

    before: BeforeView
    lifecycle: list[str]
    checks: GovernanceChecksView
    after: dict[str, str]
    patch_status: str
    active_release: str | None


class StoryView(BaseModel):
    """Complete redacted view model for one demo story."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    source_case_id: str
    story_kind: str
    title: str
    question: str
    detected_context: dict[str, str] = Field(default_factory=dict)
    decision: str
    reason_codes: list[str] = Field(default_factory=list)
    activation_profile: str
    runtime_activation_profile: str
    answer: str | None = None
    clarifying_question: str | None = None
    abstention_reason: str | None = None
    evidence: list[EvidenceView] = Field(default_factory=list)
    why: str
    orchestra_activity: list[TraceStep] = Field(default_factory=list)
    counterfactuals: list[CounterfactualView] = Field(default_factory=list)
    open_material_objection_count: int = Field(ge=0)
    route: RouteView | None = None
    case_capsule_id: str | None = None
    governance: GovernanceView | None = None
    audit_reference: str


class MetricView(BaseModel):
    """One dashboard metric with its evaluator provenance."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    value: str
    status: str
    source: str
    matched: int | None = Field(default=None, ge=0)
    expected: int | None = Field(default=None, ge=0)


class DecisionMatrixCell(BaseModel):
    """One expected-vs-actual decision matrix cell."""

    model_config = ConfigDict(extra="forbid")

    expected: str
    actual: str
    count: int = Field(ge=0)
    case_ids: list[str] = Field(default_factory=list)


class DecisionMatrixView(BaseModel):
    """Canonical expected/actual decision matrix."""

    model_config = ConfigDict(extra="forbid")

    labels: list[str]
    cells: list[DecisionMatrixCell]
    source: str


class SafetyMetricView(BaseModel):
    """A measured safety metric or an explicit honest limitation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    value: str
    status: str
    source: str


class DashboardView(BaseModel):
    """Complete dashboard payload used by the HTML renderer."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    metrics: list[MetricView]
    decision_matrix: DecisionMatrixView
    safety_metrics: list[SafetyMetricView]


class DemoBundle(BaseModel):
    """Self-contained data bundle emitted next to the HTML demo."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    stories: list[StoryView]
    dashboard: DashboardView
    security: dict[str, Any]


class AuditRecord(BaseModel):
    """Safe audit line for one ER-B generation event."""

    model_config = ConfigDict(extra="forbid")

    artifact: str
    status: str
    story_count: int = Field(ge=0)
    dashboard_metric_count: int = Field(ge=0)
    external_asset_count: int = Field(ge=0)
    network_enabled: bool


class ContextPreset(BaseModel):
    """One named live-query context preset."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    context: dict[str, str]
