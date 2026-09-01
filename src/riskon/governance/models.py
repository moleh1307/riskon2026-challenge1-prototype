"""Typed contracts for the M5B governed knowledge overlay.

The models in this module deliberately keep expert resolutions, proposed
patches, human decisions, releases, and retrieval snapshots separate.  That
separation is the main safety property of M5B: a proposal is never evidence
until it has passed Policy CI, received an independent human decision, and
been included in an explicitly activated release.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from riskon.orchestra.models import CaseCapsule as OrchestraCaseCapsule

CaseCapsule = OrchestraCaseCapsule


def _utc(value: datetime) -> datetime:
    """Require timezone-aware timestamps and normalize them to UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


class PolicyCIPhase(StrEnum):
    """The three non-recursive governance evaluation phases."""

    PRE_APPROVAL = "PRE_APPROVAL"
    ACTIVATION = "ACTIVATION"
    CURRENT_STATE = "CURRENT_STATE"


class CheckStatus(StrEnum):
    """Status of one mandatory Policy CI check."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


class PolicyCIStatus(StrEnum):
    """Overall status returned by one Policy CI phase."""

    AWAITING_HUMAN = "AWAITING_HUMAN"
    APPROVED = "APPROVED"
    CURRENT_OR_EXPIRED = "CURRENT_OR_EXPIRED"
    FAIL = "FAIL"


class PatchStatus(StrEnum):
    """Governed patch lifecycle states."""

    PROPOSED = "PROPOSED"
    TESTED = "TESTED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    ROLLED_BACK = "ROLLED_BACK"


class PatchOperation(StrEnum):
    """The supported patch operations."""

    ADD = "ADD"
    UPDATE = "UPDATE"
    DEPRECATE = "DEPRECATE"


class PatchRiskLevel(StrEnum):
    """Synthetic risk labels carried by a patch."""

    NORMAL = "NORMAL"
    CRITICAL = "CRITICAL"


class ApprovalDecision(StrEnum):
    """A human governance decision."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


class ActorType(StrEnum):
    """Actor classes; only HUMAN_ROLE can approve a patch."""

    HUMAN_ROLE = "HUMAN_ROLE"
    AGENT_ROLE = "AGENT_ROLE"


class ReleaseStatus(StrEnum):
    """Knowledge release lifecycle status."""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ROLLED_BACK = "ROLLED_BACK"


class GovernanceEventType(StrEnum):
    """Closed-world event vocabulary for the append-only store."""

    PATCH_PROPOSED = "PATCH_PROPOSED"
    POLICY_CI_COMPLETED = "POLICY_CI_COMPLETED"
    PATCH_AWAITING_APPROVAL = "PATCH_AWAITING_APPROVAL"
    HUMAN_DECISION_RECORDED = "HUMAN_DECISION_RECORDED"
    PATCH_APPROVED = "PATCH_APPROVED"
    PATCH_REJECTED = "PATCH_REJECTED"
    RELEASE_CREATED = "RELEASE_CREATED"
    RELEASE_ACTIVATED = "RELEASE_ACTIVATED"
    PATCH_EXPIRED = "PATCH_EXPIRED"


class MandatoryCheck(StrEnum):
    """The exact M5B mandatory-check vocabulary."""

    EVIDENCE_COMPLETENESS = "EVIDENCE_COMPLETENESS"
    CLAIM_SUBSET = "CLAIM_SUBSET"
    SCOPE_CONTAINMENT = "SCOPE_CONTAINMENT"
    CONTRADICTION_DETECTION = "CONTRADICTION_DETECTION"
    CRITICAL_CONTROL_PRESERVATION = "CRITICAL_CONTROL_PRESERVATION"
    REFERENCE_RESOLUTION = "REFERENCE_RESOLUTION"
    M0_M4D_REGRESSION = "M0_M4D_REGRESSION"
    COUNTERFACTUAL_CONTAINMENT = "COUNTERFACTUAL_CONTAINMENT"
    SEPARATION_OF_DUTIES = "SEPARATION_OF_DUTIES"
    HUMAN_APPROVAL_PRESENT = "HUMAN_APPROVAL_PRESENT"
    EFFECTIVE_PERIOD_VALID = "EFFECTIVE_PERIOD_VALID"


MANDATORY_CHECK_ORDER: tuple[MandatoryCheck, ...] = tuple(MandatoryCheck)


class Scope(BaseModel):
    """Explicit patch scope; an empty dimension is never a wildcard."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    regions: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(default_factory=list)
    service_models: list[str] = Field(default_factory=list)
    solicitation_types: list[str] = Field(default_factory=list)
    workflow_stages: list[str] = Field(default_factory=list)
    client_classifications: list[str] = Field(default_factory=list)
    systems: list[str] = Field(default_factory=list)

    def dimensions(self) -> dict[str, list[str]]:
        """Return all declared dimensions in their contract order."""

        return self.model_dump(mode="python")


class GovernanceClaim(BaseModel):
    """A structured claim proposed by an expert resolution or patch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    critical: bool = False


class ExpertResolution(BaseModel):
    """Structured expert output; it is not itself an evidence unit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resolution_id: str = Field(min_length=1)
    case_capsule_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    resolution_author_role_id: str = Field(min_length=1)
    resolution_text: str = Field(min_length=1)
    authoritative_evidence_refs: list[str] = Field(default_factory=list)
    claims: list[GovernanceClaim] = Field(default_factory=list)
    scope: Scope
    effective_from: datetime
    effective_to: datetime | None = None
    review_by: datetime | None = None
    knowledge_owner_role_id: str = Field(min_length=1)
    approval_required: bool = True

    @model_validator(mode="after")
    def validate_period(self) -> ExpertResolution:
        """Reject malformed effective periods while allowing expired history."""

        object.__setattr__(self, "effective_from", _utc(self.effective_from))
        if self.effective_to is not None:
            object.__setattr__(self, "effective_to", _utc(self.effective_to))
            if self.effective_from >= self.effective_to:
                raise ValueError("effective_from must be earlier than effective_to")
        if self.review_by is not None:
            object.__setattr__(self, "review_by", _utc(self.review_by))
        return self


class KnowledgePatch(BaseModel):
    """Versioned proposed knowledge, kept separate from official corpus data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    patch_id: str = Field(min_length=1)
    operation: PatchOperation
    status: PatchStatus
    source_resolution_id: str = Field(min_length=1)
    claims: list[GovernanceClaim] = Field(default_factory=list)
    scope: Scope
    authoritative_evidence_refs: list[str] = Field(default_factory=list)
    risk_level: PatchRiskLevel
    effective_from: datetime
    effective_to: datetime | None = None
    supersedes_patch_id: str | None = None
    knowledge_owner_role_id: str = Field(min_length=1)
    policy_ci_report_ref: str = Field(min_length=1)
    approval_ref: str | None = None

    @model_validator(mode="after")
    def validate_period(self) -> KnowledgePatch:
        """Reject malformed patch windows without rejecting expired fixtures."""

        object.__setattr__(self, "effective_from", _utc(self.effective_from))
        if self.effective_to is not None:
            object.__setattr__(self, "effective_to", _utc(self.effective_to))
            if self.effective_from >= self.effective_to:
                raise ValueError("effective_from must be earlier than effective_to")
        return self


class HumanApproval(BaseModel):
    """Independent human approval or rejection record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: str = Field(min_length=1)
    patch_id: str = Field(min_length=1)
    actor_type: ActorType
    actor_role_id: str = Field(min_length=1)
    decision: ApprovalDecision
    timestamp_utc: datetime
    reviewed_claim_ids: list[str] = Field(default_factory=list)
    reviewed_scope: Scope
    comment: str = ""

    @model_validator(mode="after")
    def normalize_timestamp(self) -> HumanApproval:
        """Normalize the human decision timestamp to UTC."""

        object.__setattr__(self, "timestamp_utc", _utc(self.timestamp_utc))
        return self


class ClaimRelation(BaseModel):
    """Generic relationship between two already-known claim IDs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    left_claim_id: str = Field(min_length=1)
    right_claim_id: str = Field(min_length=1)
    relation: str = Field(pattern="^(SUPPORTS|CONTRADICTS|SUPERSEDES)$")
    critical: bool = False
    evidence_refs: list[str] = Field(default_factory=list)


class PolicyCICheckResult(BaseModel):
    """One check result in a deterministic Policy CI report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check_id: MandatoryCheck
    status: CheckStatus
    reason_codes: list[str] = Field(default_factory=list)
    details: str = ""


class PolicyCIReport(BaseModel):
    """Machine-readable result of one Policy CI phase."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: PolicyCIPhase
    patch_id: str
    resolution_id: str
    reference_time_utc: datetime
    overall_status: PolicyCIStatus
    checks: list[PolicyCICheckResult]
    failed_check_ids: list[MandatoryCheck] = Field(default_factory=list)
    approval_id: str | None = None
    regression: dict[str, Any] = Field(default_factory=dict)
    counterfactual_transitions: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def normalize_timestamp(self) -> PolicyCIReport:
        """Normalize report timestamps and derive failed IDs consistently."""

        object.__setattr__(self, "reference_time_utc", _utc(self.reference_time_utc))
        failed = [item.check_id for item in self.checks if item.status is CheckStatus.FAIL]
        object.__setattr__(self, "failed_check_ids", failed)
        return self

    @property
    def check_results(self) -> list[PolicyCICheckResult]:
        """Compatibility alias used by callers that prefer the longer name."""

        return self.checks

    def status_for(self, check_id: MandatoryCheck | str) -> CheckStatus:
        """Return one check status, failing clearly for an unknown check."""

        wanted = MandatoryCheck(check_id)
        for item in self.checks:
            if item.check_id is wanted:
                return item.status
        raise KeyError(wanted.value)

    @property
    def all_mandatory_checks_pass(self) -> bool:
        """Whether every declared mandatory check is PASS."""

        return len(self.checks) == len(MANDATORY_CHECK_ORDER) and all(
            item.status is CheckStatus.PASS for item in self.checks
        )


class EvaluatedPatch(BaseModel):
    """Patch plus all inputs needed for a human decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_capsule: CaseCapsule
    expert_resolution: ExpertResolution
    knowledge_patch: KnowledgePatch
    policy_ci_report: PolicyCIReport
    approval: HumanApproval | None = None

    @property
    def patch_id(self) -> str:
        """Return the evaluated patch identifier."""

        return self.knowledge_patch.patch_id


class GovernedPatch(BaseModel):
    """Patch after a separate human decision, still not necessarily active."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_capsule: CaseCapsule
    expert_resolution: ExpertResolution
    knowledge_patch: KnowledgePatch
    policy_ci_report: PolicyCIReport
    approval: HumanApproval
    status: PatchStatus

    @property
    def patch_id(self) -> str:
        """Return the governed patch identifier."""

        return self.knowledge_patch.patch_id


class KnowledgeReleaseRequest(BaseModel):
    """Explicit request to create and activate one release."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    patch_id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    requested_by_role_id: str = Field(min_length=1)
    requested_at_utc: datetime
    expected_outcome: str = Field(min_length=1)

    @model_validator(mode="after")
    def normalize_timestamp(self) -> KnowledgeReleaseRequest:
        """Normalize the request timestamp to UTC."""

        object.__setattr__(self, "requested_at_utc", _utc(self.requested_at_utc))
        return self


class KnowledgeRelease(BaseModel):
    """Versioned, explicitly activated set of governed patches."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    release_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    previous_release_id: str | None = None
    patch_ids: list[str] = Field(default_factory=list)
    created_at_utc: datetime
    activated_at_utc: datetime
    activated_by_role_id: str = Field(min_length=1)
    status: ReleaseStatus

    @model_validator(mode="after")
    def normalize_timestamps(self) -> KnowledgeRelease:
        """Normalize release timestamps to UTC."""

        object.__setattr__(self, "created_at_utc", _utc(self.created_at_utc))
        object.__setattr__(self, "activated_at_utc", _utc(self.activated_at_utc))
        return self

    @property
    def release_version(self) -> str:
        """Expose the overlay naming used by the pipeline contract."""

        return self.version


class OverlayEvidenceUnit(BaseModel):
    """An active patch claim admitted to retrieval as local overlay evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    overlay_ref: str = Field(pattern=r"^local://knowledge-overlay/[^/]+/[^#]+#claim-.+$")
    release_id: str = Field(min_length=1)
    patch_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    scope: Scope
    critical: bool = False
    backing_evidence_refs: list[str] = Field(default_factory=list)
    source_resolution_id: str = Field(min_length=1)
    approval_id: str = Field(min_length=1)
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def validate_overlay_period(self) -> OverlayEvidenceUnit:
        """Normalize timestamps and preserve strict period ordering."""

        object.__setattr__(self, "effective_from", _utc(self.effective_from))
        if self.effective_to is not None:
            object.__setattr__(self, "effective_to", _utc(self.effective_to))
            if self.effective_from >= self.effective_to:
                raise ValueError("effective_from must be earlier than effective_to")
        return self


class KnowledgeOverlaySnapshot(BaseModel):
    """Immutable retrieval snapshot compiled from one active release."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    release_id: str = Field(min_length=1)
    release_version: str = Field(min_length=1)
    reference_time_utc: datetime
    active_patch_ids: list[str] = Field(default_factory=list)
    excluded_patch_ids: list[str] = Field(default_factory=list)
    evidence_units: list[OverlayEvidenceUnit] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_timestamp(self) -> KnowledgeOverlaySnapshot:
        """Normalize the snapshot reference time to UTC."""

        object.__setattr__(self, "reference_time_utc", _utc(self.reference_time_utc))
        return self


class GovernanceEvent(BaseModel):
    """Append-only, non-content-bearing governance audit event."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: GovernanceEventType
    timestamp_utc: datetime
    patch_id: str | None = None
    resolution_id: str | None = None
    approval_id: str | None = None
    release_id: str | None = None
    previous_status: PatchStatus | None = None
    new_status: PatchStatus | None = None
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_timestamp(self) -> GovernanceEvent:
        """Normalize event timestamps to UTC."""

        object.__setattr__(self, "timestamp_utc", _utc(self.timestamp_utc))
        return self


class RegressionGateResult(BaseModel):
    """Safe aggregate returned by the in-process upstream regression gate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected: int = Field(ge=0)
    matched: int = Field(ge=0)
    suites: dict[str, dict[str, int]] = Field(default_factory=dict)
    network_enabled: bool = False

    @property
    def passed(self) -> bool:
        """Return whether all expected suites matched with no network."""

        return self.matched == self.expected and not self.network_enabled
