"""Shared fixtures and builders for the M5B governance tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from riskon.config import load_milestone5b_config
from riskon.governance.counterfactual_gate import CounterfactualGate
from riskon.governance.event_store import GovernanceEventStore
from riskon.governance.models import (
    ActorType,
    ApprovalDecision,
    ExpertResolution,
    GovernanceClaim,
    HumanApproval,
    KnowledgePatch,
    PatchOperation,
    PatchRiskLevel,
    PatchStatus,
    RegressionGateResult,
    Scope,
)
from riskon.governance.service import GovernedKnowledgeService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M5B_CONFIG_PATH = PROJECT_ROOT / "config" / "milestone5b.toml"
REFERENCE_TIME = datetime(2026, 8, 27, 12, tzinfo=UTC)
LOCAL_REF = "local://synthetic-m5a/evaluation_cases.json#test"


class StubRegressionGate:
    """Fast deterministic regression hook for unit-level Policy CI tests."""

    def __init__(self, *, passed: bool = True, network_enabled: bool = False) -> None:
        self.passed = passed
        self.network_enabled = network_enabled
        self.calls = 0

    def run(self) -> RegressionGateResult:
        self.calls += 1
        matched = 45 if self.passed else 44
        return RegressionGateResult(
            expected=45,
            matched=matched,
            suites={"M4D": {"expected": 5, "matched": matched}},
            network_enabled=self.network_enabled,
        )


class StubCounterfactualGate:
    """Fast injectable counterfactual hook with controllable outcomes."""

    def __init__(self, *, passed: bool = True, count: int = 1) -> None:
        self.passed = passed
        self.count = count
        self.calls = 0

    def evaluate(self, patch: KnowledgePatch, expectations: Any) -> tuple[bool, int, str]:
        del patch, expectations
        self.calls += 1
        return self.passed, self.count if self.passed else 0, "stub counterfactual result"


def config() -> Any:
    """Load the canonical M5B configuration."""

    return load_milestone5b_config(M5B_CONFIG_PATH)


def service(
    tmp_path: Path,
    *,
    regression: StubRegressionGate | None = None,
    counterfactual: StubCounterfactualGate | CounterfactualGate | None = None,
) -> GovernedKnowledgeService:
    """Build an isolated service with local event storage."""

    return GovernedKnowledgeService(
        config(),
        event_store=GovernanceEventStore(tmp_path / "events.jsonl"),
        regression_gate=regression or StubRegressionGate(),
        counterfactual_gate=counterfactual or StubCounterfactualGate(),
    )


def raw_m5a_case(case_id: str) -> dict[str, Any]:
    raw = json.loads(
        (PROJECT_ROOT / "data" / "synthetic" / "m5a" / "evaluation_cases.json").read_text(
            encoding="utf-8"
        )
    )
    return next(item for item in raw["cases"] if item["id"] == case_id)


def case_inputs(
    service_instance: GovernedKnowledgeService,
    case_id: str = "M5A-046",
) -> tuple[Any, ExpertResolution, KnowledgePatch, HumanApproval | None]:
    return service_instance.load_case_inputs(case_id)


def valid_scope(**values: list[str]) -> Scope:
    return Scope(**values)


def valid_claim(
    claim_id: str = "claim-1",
    *,
    text: str = "A supported synthetic claim.",
    evidence_refs: list[str] | None = None,
    critical: bool = False,
) -> GovernanceClaim:
    return GovernanceClaim(
        claim_id=claim_id,
        text=text,
        evidence_refs=list(evidence_refs if evidence_refs is not None else [LOCAL_REF]),
        critical=critical,
    )


def valid_resolution(
    *,
    resolution_id: str = "resolution-1",
    claims: list[GovernanceClaim] | None = None,
    scope: Scope | None = None,
    author: str = "role-author",
    owner: str = "role-owner",
    effective_from: datetime = REFERENCE_TIME - timedelta(days=1),
    effective_to: datetime | None = None,
    refs: list[str] | None = None,
) -> ExpertResolution:
    claims = list(claims if claims is not None else [valid_claim()])
    return ExpertResolution(
        resolution_id=resolution_id,
        case_capsule_id="capsule-1",
        status="CANDIDATE_RESOLUTION",
        resolution_author_role_id=author,
        resolution_text="A synthetic expert resolution.",
        authoritative_evidence_refs=list(refs if refs is not None else [LOCAL_REF]),
        claims=claims,
        scope=scope or valid_scope(regions=["REGION_BETA"], service_models=["SERVICE_BASIC"]),
        effective_from=effective_from,
        effective_to=effective_to,
        review_by=None,
        knowledge_owner_role_id=owner,
        approval_required=True,
    )


def valid_patch(
    resolution: ExpertResolution | None = None,
    *,
    patch_id: str = "patch-1",
    claims: list[GovernanceClaim] | None = None,
    scope: Scope | None = None,
    operation: PatchOperation = PatchOperation.ADD,
    status: PatchStatus = PatchStatus.PROPOSED,
    risk_level: PatchRiskLevel = PatchRiskLevel.NORMAL,
    effective_from: datetime = REFERENCE_TIME - timedelta(days=1),
    effective_to: datetime | None = None,
    refs: list[str] | None = None,
    owner: str = "role-owner",
    supersedes_patch_id: str | None = None,
) -> KnowledgePatch:
    resolution = resolution or valid_resolution()
    claims = list(claims if claims is not None else resolution.claims)
    return KnowledgePatch(
        patch_id=patch_id,
        operation=operation,
        status=status,
        source_resolution_id=resolution.resolution_id,
        claims=claims,
        scope=scope or resolution.scope,
        authoritative_evidence_refs=list(refs if refs is not None else [LOCAL_REF]),
        risk_level=risk_level,
        effective_from=effective_from,
        effective_to=effective_to,
        supersedes_patch_id=supersedes_patch_id,
        knowledge_owner_role_id=owner,
        policy_ci_report_ref="local://synthetic-m5a/policy_ci_policy.json#test",
        approval_ref=None,
    )


def valid_approval(
    patch: KnowledgePatch | None = None,
    resolution: ExpertResolution | None = None,
    *,
    approval_id: str = "approval-1",
    actor: str = "role-approver",
    actor_type: ActorType = ActorType.HUMAN_ROLE,
    decision: ApprovalDecision = ApprovalDecision.APPROVE,
    patch_id: str | None = None,
) -> HumanApproval:
    patch = patch or valid_patch(resolution)
    resolution = resolution or valid_resolution()
    return HumanApproval(
        approval_id=approval_id,
        patch_id=patch_id if patch_id is not None else patch.patch_id,
        actor_type=actor_type,
        actor_role_id=actor,
        decision=decision,
        timestamp_utc=REFERENCE_TIME,
        reviewed_claim_ids=[claim.claim_id for claim in patch.claims],
        reviewed_scope=patch.scope,
        comment="Synthetic independent decision.",
    )


def loaded_candidate(
    service_instance: GovernedKnowledgeService,
    case_id: str = "M5A-046",
) -> tuple[Any, ExpertResolution, KnowledgePatch, HumanApproval | None]:
    capsule, resolution, fixture_patch, approval = case_inputs(service_instance, case_id)
    return (
        capsule,
        resolution,
        fixture_patch.model_copy(update={"status": PatchStatus.PROPOSED}),
        approval,
    )
