"""M4A/M4B orchestration contracts.

The models keep the baseline-oriented orchestration boundary explicit while
adding frozen task, finding, and objection records for M4B workers.
"""

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import core_schema

from riskon.models import (
    AnswerClaim,
    Decision,
    DetectedContext,
    PlannedVerifiedRun,
    ReasonCode,
    RoutedRun,
    RouteMode,
    RoutingContext,
    VerificationStatus,
    VerifiedRun,
)
from riskon.orchestra.counterfactual_models import CounterfactualExecutionResult, CounterfactualPlan


class ActivationProfile(StrEnum):
    """Closed M4 activation-profile vocabulary."""

    FAST_PATH = "FAST_PATH"
    SHORT_CIRCUIT_CLARIFY = "SHORT_CIRCUIT_CLARIFY"
    HUMAN_FIRST = "HUMAN_FIRST"
    DUAL_CHECK = "DUAL_CHECK"
    FULL_ORCHESTRA = "FULL_ORCHESTRA"


class RiskSignal(str):
    """One activation signal declared by the frozen M4 policy.

    The class intentionally has no Python-side signal enumeration.  The
    activation policy JSON is the source of truth for which values are
    declared; :class:`OrchestraContext` and ``ActivationPolicy`` validate
    membership against that file.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        _source_type: Any,
        _handler: Any,
    ) -> Any:
        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.str_schema(strict=True),
        )

    @classmethod
    def _validate(cls, value: str) -> "RiskSignal":
        if not value:
            raise ValueError("risk signal must be non-empty")
        return cls(value)


def _frozen_declared_risk_signals() -> frozenset[str]:
    """Read the declared signal vocabulary without maintaining a duplicate list."""

    project_root = Path(__file__).resolve().parents[3]
    policy_paths = (
        project_root / "data/synthetic/m4/activation_policy.json",
        project_root / "data/synthetic/m4d/runtime_policy.json",
    )
    signals: set[str] = set()
    for policy_path in policy_paths:
        try:
            raw = json.loads(policy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if policy_path.name == "runtime_policy.json":
            values = raw.get("risk_signal_order") if isinstance(raw, dict) else None
            if isinstance(values, list):
                signals.update(value for value in values if isinstance(value, str))
            continue
        profiles = raw.get("profiles") if isinstance(raw, dict) else None
        if not isinstance(profiles, list):
            continue
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            values = profile.get("trigger_signals", [])
            if isinstance(values, list):
                signals.update(value for value in values if isinstance(value, str))
    return frozenset(signals)


class OrchestraContext(BaseModel):
    """Structured activation and routing context with no raw query text."""

    model_config = ConfigDict(extra="forbid")

    risk_signals: tuple[RiskSignal, ...]
    routing_context: RoutingContext | None = None
    routing_profile: str = Field(min_length=1)
    structured_context: dict[str, str] = Field(
        default_factory=dict,
        exclude_if=lambda value: not value,
    )
    requested_agent_roles: tuple[str, ...] = Field(
        default=(),
        exclude_if=lambda value: not value,
    )

    @model_validator(mode="after")
    def validate_declared_signals(self) -> "OrchestraContext":
        declared = _frozen_declared_risk_signals()
        if declared:
            unknown = [str(signal) for signal in self.risk_signals if str(signal) not in declared]
            if unknown:
                raise ValueError(f"Unknown M4 risk signal(s): {sorted(set(unknown))}")
        return self


class RiskAssessment(BaseModel):
    """Immutable automatic risk assessment used by the M4D runtime."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_signals: tuple[RiskSignal, ...]
    signal_sources: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    selected_activation_profile: ActivationProfile
    profile_reason: str = Field(min_length=1)


class RuntimeDiagnostics(BaseModel):
    """Safe runtime counters retained alongside one orchestra run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_planned_call_count: int = Field(ge=0)
    source_safety_diagnostic_codes: tuple[str, ...] = ()
    failure_stage: str | None = None
    failed_task_ids: tuple[str, ...] = ()
    cause_types: tuple[str, ...] = ()
    fallback_action: str | None = None


class InvestigationPlan(BaseModel):
    """The bounded plan handed to a future worker-capable runtime."""

    model_config = ConfigDict(extra="forbid")

    activation_profile: ActivationProfile
    required_agent_roles: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    worker_execution_required: bool


class OrchestraMetrics(BaseModel):
    """Observable worker metrics; every M4A successful path is zero-worker."""

    model_config = ConfigDict(extra="forbid")

    active_agent_count: int = Field(ge=0)
    task_count: int = Field(ge=0)
    finding_count: int = Field(ge=0)
    candidate_claim_count: int = Field(ge=0)
    material_objection_count: int = Field(ge=0)
    counterfactual_count: int = Field(ge=0)
    worker_execution_count: int = Field(ge=0)


class CaseCapsule(BaseModel):
    """Minimal structured handoff state for human-first escalation."""

    model_config = ConfigDict(extra="forbid")

    capsule_id: str = Field(min_length=1)
    baseline_trace_id: str = Field(min_length=1)
    baseline_decision: Decision
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    detected_context: DetectedContext
    missing_context: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus
    support_function: str = Field(min_length=1)
    route_mode: RouteMode
    selected_expert_id: str | None = None
    queue_id: str | None = None
    routing_reason: str = Field(min_length=1)
    routing_confidence: float = Field(ge=0.0, le=1.0)
    confidence_kind: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_local_evidence_refs(self) -> "CaseCapsule":
        invalid = [
            ref
            for ref in self.evidence_refs
            if not ref.startswith(("local://synthetic-m4/", "local://synthetic-m4d/"))
        ]
        if invalid:
            raise ValueError(f"Case capsule evidence refs must be local M4 refs: {invalid}")
        return self


class ExecutionWave(StrEnum):
    """The bounded discovery, challenge, and M4C validation waves."""

    DISCOVERY = "DISCOVERY"
    CHALLENGE = "CHALLENGE"
    VALIDATION = "VALIDATION"


class FindingStance(StrEnum):
    """A worker's relationship to a candidate claim."""

    SUPPORT = "SUPPORT"
    CHALLENGE = "CHALLENGE"
    NEUTRAL = "NEUTRAL"


class AgentTask(BaseModel):
    """One deterministic worker task in the M4B graph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    agent_role: str = Field(min_length=1)
    execution_wave: ExecutionWave
    objective: str = Field(min_length=1)
    allowed_tools: list[str] = Field(default_factory=list)
    input_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_deterministic_id(self) -> "AgentTask":
        expected = f"task:{self.plan_id}:{self.agent_role.lower()}"
        if self.task_id != expected:
            raise ValueError(f"AgentTask task_id must be {expected!r}")
        return self


class AgentFinding(BaseModel):
    """A source-grounded observation returned by one worker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    agent_role: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    stance: FindingStance
    evidence_refs: list[str] = Field(default_factory=list)
    source_scope: str = Field(min_length=1)
    criticality: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)


class MaterialObjection(BaseModel):
    """A challenge record retained by the material-objection gate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    objection_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    target_claim_id: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    materiality: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    status: str = Field(min_length=1)
    resolvable_by: str = Field(min_length=1)


class WorkerDiagnostic(BaseModel):
    """Safe structured diagnostic emitted by a worker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    diagnostic_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    agent_role: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)


class WorkerContext(BaseModel):
    """Isolated, read-only input envelope delivered to one worker."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_run: PlannedVerifiedRun
    orchestra_context: OrchestraContext
    task: AgentTask
    local_corpus_config: Any
    source_safety_policy: Any
    prior_findings: list[AgentFinding] = Field(default_factory=list)
    candidate_claims: list[AnswerClaim] = Field(default_factory=list)
    counterfactual_plan: CounterfactualPlan | None = None
    counterfactual_runner: Any = None


class WorkerResult(BaseModel):
    """Isolated worker output collected before fan-in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    agent_role: str = Field(min_length=1)
    findings: list[AgentFinding] = Field(default_factory=list)
    material_objections: list[MaterialObjection] = Field(default_factory=list)
    counterfactual_results: list[CounterfactualExecutionResult] = Field(default_factory=list)
    diagnostics: list[WorkerDiagnostic] = Field(default_factory=list)


class OrchestraRun(BaseModel):
    """Complete M4A orchestration output layered over a frozen baseline."""

    model_config = ConfigDict(extra="forbid")

    baseline_run: PlannedVerifiedRun
    activation_profile: ActivationProfile
    risk_signals: tuple[RiskSignal, ...]
    investigation_plan: InvestigationPlan
    agent_tasks: list[AgentTask] = Field(default_factory=list)
    findings: list[AgentFinding] = Field(default_factory=list)
    candidate_claims: list[AnswerClaim] = Field(default_factory=list)
    material_objections: list[MaterialObjection] = Field(default_factory=list)
    counterfactual_results: list[CounterfactualExecutionResult] = Field(default_factory=list)
    final_verified_run: VerifiedRun
    routed_run: RoutedRun | None = None
    case_capsule: CaseCapsule | None = None
    orchestra_metrics: OrchestraMetrics
    risk_assessment: RiskAssessment | None = None
    runtime_diagnostics: RuntimeDiagnostics | None = None
