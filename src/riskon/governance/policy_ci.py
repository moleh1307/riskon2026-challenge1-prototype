"""Deterministic execution of the eleven M5B Policy CI checks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from riskon.governance.approval import validate_human_approval
from riskon.governance.contradiction import detect_contradictions, preserves_critical_controls
from riskon.governance.evidence_checks import (
    claim_subset,
    evidence_completeness,
    reference_resolution,
)
from riskon.governance.models import (
    MANDATORY_CHECK_ORDER,
    CheckStatus,
    ClaimRelation,
    ExpertResolution,
    HumanApproval,
    KnowledgePatch,
    MandatoryCheck,
    PolicyCICheckResult,
    PolicyCIPhase,
    PolicyCIReport,
    PolicyCIStatus,
)
from riskon.governance.scope_checks import scope_containment


class PolicyCIExecutor:
    """Run Policy CI as a pure check coordinator with injected local hooks."""

    def __init__(
        self,
        relations: list[ClaimRelation],
        resolver: Callable[[str], object | None],
        regression: Callable[[], tuple[bool, str, dict[str, dict[str, int]]]],
        counterfactual: Callable[[KnowledgePatch], tuple[bool, int, str]],
    ) -> None:
        self.relations = relations
        self.resolver = resolver
        self.regression = regression
        self.counterfactual = counterfactual

    def run(
        self,
        resolution: ExpertResolution,
        patch: KnowledgePatch,
        approval: HumanApproval | None,
        reference_time_utc: datetime,
        phase: PolicyCIPhase,
    ) -> PolicyCIReport:
        """Evaluate all checks in the exact contract order."""

        results: list[PolicyCICheckResult] = []

        def add(check: MandatoryCheck, status: CheckStatus, details: str) -> None:
            results.append(PolicyCICheckResult(check_id=check, status=status, details=details))

        ok, details = evidence_completeness(resolution, patch)
        add(MandatoryCheck.EVIDENCE_COMPLETENESS, _status(ok), details)
        ok, details = claim_subset(resolution, patch)
        add(MandatoryCheck.CLAIM_SUBSET, _status(ok), details)
        ok, details = scope_containment(resolution, patch)
        add(MandatoryCheck.SCOPE_CONTAINMENT, _status(ok), details)
        ok, details = detect_contradictions(patch, self.relations)
        add(MandatoryCheck.CONTRADICTION_DETECTION, _status(ok), details)
        ok, details = preserves_critical_controls(resolution, patch, self.relations)
        add(MandatoryCheck.CRITICAL_CONTROL_PRESERVATION, _status(ok), details)
        ok, details = reference_resolution(resolution, patch, self.resolver)
        add(MandatoryCheck.REFERENCE_RESOLUTION, _status(ok), details)
        regression_ok, regression_details, regression_summary = self.regression()
        add(
            MandatoryCheck.M0_M4D_REGRESSION,
            _status(regression_ok),
            regression_details,
        )
        cf_ok, transition_count, cf_details = self.counterfactual(patch)
        add(MandatoryCheck.COUNTERFACTUAL_CONTAINMENT, _status(cf_ok), cf_details)

        separation_ok, separation_details = _separation_of_duties(resolution, approval)
        add(
            MandatoryCheck.SEPARATION_OF_DUTIES,
            _status(separation_ok),
            separation_details,
        )
        if phase is PolicyCIPhase.CURRENT_STATE and approval is None:
            human_status = CheckStatus.PASS
            human_details = "human approval is not required to classify current-state expiry"
        elif phase is PolicyCIPhase.CURRENT_STATE or approval is not None:
            human_ok, human_details = validate_human_approval(resolution, approval)
            human_status = _status(human_ok)
        else:
            human_status = CheckStatus.NOT_RUN
            human_details = "human approval is intentionally deferred"
        add(MandatoryCheck.HUMAN_APPROVAL_PRESENT, human_status, human_details)

        effective_ok, effective_details = _effective_period(patch, reference_time_utc)
        add(
            MandatoryCheck.EFFECTIVE_PERIOD_VALID,
            _status(effective_ok),
            effective_details,
        )

        failed = [item for item in results if item.status is CheckStatus.FAIL]
        if failed:
            overall = PolicyCIStatus.FAIL
        elif phase is PolicyCIPhase.PRE_APPROVAL:
            overall = PolicyCIStatus.AWAITING_HUMAN
        elif phase is PolicyCIPhase.ACTIVATION:
            overall = PolicyCIStatus.APPROVED
        else:
            overall = PolicyCIStatus.CURRENT_OR_EXPIRED
        return PolicyCIReport(
            phase=phase,
            patch_id=patch.patch_id,
            resolution_id=resolution.resolution_id,
            reference_time_utc=reference_time_utc,
            overall_status=overall,
            checks=results,
            approval_id=approval.approval_id if approval else None,
            regression=regression_summary,
            counterfactual_transitions=transition_count,
        )


def _status(ok: bool) -> CheckStatus:
    return CheckStatus.PASS if ok else CheckStatus.FAIL


def _separation_of_duties(
    resolution: ExpertResolution,
    approval: HumanApproval | None,
) -> tuple[bool, str]:
    actor = approval.actor_role_id if approval is not None else resolution.knowledge_owner_role_id
    if actor == resolution.resolution_author_role_id:
        return False, "resolution author and approval actor/owner are identical"
    return True, "resolution author is separated from the approval role"


def _effective_period(
    patch: KnowledgePatch,
    reference_time_utc: datetime,
) -> tuple[bool, str]:
    if reference_time_utc < patch.effective_from:
        return False, "patch effective_from is in the future"
    if patch.effective_to is not None and reference_time_utc >= patch.effective_to:
        return False, "patch effective_to has been reached"
    return True, "patch is effective at the reference time"


def expected_check_ids() -> tuple[MandatoryCheck, ...]:
    """Expose the exact check order for evaluators and tests."""

    return MANDATORY_CHECK_ORDER
