"""M5B typed-model and immutability contracts."""

from datetime import datetime, timedelta

import pytest
from m5b_helpers import (
    REFERENCE_TIME,
    valid_approval,
    valid_patch,
    valid_resolution,
)
from pydantic import ValidationError

from riskon.governance.models import (
    MANDATORY_CHECK_ORDER,
    ActorType,
    ApprovalDecision,
    CheckStatus,
    ClaimRelation,
    GovernanceClaim,
    GovernanceEvent,
    GovernanceEventType,
    KnowledgeOverlaySnapshot,
    KnowledgeRelease,
    KnowledgeReleaseRequest,
    MandatoryCheck,
    OverlayEvidenceUnit,
    PatchOperation,
    PatchRiskLevel,
    PatchStatus,
    PolicyCICheckResult,
    PolicyCIPhase,
    PolicyCIReport,
    PolicyCIStatus,
    RegressionGateResult,
    ReleaseStatus,
    Scope,
)


def test_m5b_enum_vocabulary_is_closed() -> None:
    assert [item.value for item in PolicyCIPhase] == [
        "PRE_APPROVAL",
        "ACTIVATION",
        "CURRENT_STATE",
    ]
    assert [item.value for item in PatchOperation] == ["ADD", "UPDATE", "DEPRECATE"]
    assert PatchRiskLevel.CRITICAL.value == "CRITICAL"
    assert ApprovalDecision.APPROVE.value == "APPROVE"
    assert ActorType.HUMAN_ROLE.value == "HUMAN_ROLE"
    assert ReleaseStatus.ACTIVE.value == "ACTIVE"
    assert len(MANDATORY_CHECK_ORDER) == 11


def test_scope_dimensions_preserve_contract_order_and_are_frozen() -> None:
    scope = Scope(regions=["REGION_BETA"], systems=["SYSTEM_X"])
    assert list(scope.dimensions()) == [
        "regions",
        "jurisdictions",
        "service_models",
        "solicitation_types",
        "workflow_stages",
        "client_classifications",
        "systems",
    ]
    assert scope.dimensions()["regions"] == ["REGION_BETA"]
    with pytest.raises(ValidationError):
        scope.regions = ["REGION_ALPHA"]


def test_claim_and_relation_models_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        GovernanceClaim(claim_id="x", text="claim", unexpected=True)
    relation = ClaimRelation(
        left_claim_id="left",
        right_claim_id="right",
        relation="SUPPORTS",
    )
    assert relation.relation == "SUPPORTS"
    with pytest.raises(ValidationError):
        ClaimRelation(left_claim_id="l", right_claim_id="r", relation="UNKNOWN")


def test_resolution_patch_and_approval_timestamps_normalize_to_utc() -> None:
    plus_two = datetime.fromisoformat("2026-08-27T14:00:00+02:00")
    resolution = valid_resolution(effective_from=plus_two)
    patch = valid_patch(resolution, effective_from=plus_two)
    approval = valid_approval(patch, resolution)
    assert resolution.effective_from == REFERENCE_TIME
    assert patch.effective_from == REFERENCE_TIME
    assert approval.timestamp_utc == REFERENCE_TIME


def test_naive_and_reversed_periods_are_rejected() -> None:
    with pytest.raises(ValidationError):
        valid_resolution(effective_from=datetime(2026, 8, 27))
    with pytest.raises(ValidationError):
        valid_patch(effective_from=datetime(2026, 8, 27))
    with pytest.raises(ValidationError):
        valid_resolution(
            effective_from=REFERENCE_TIME,
            effective_to=REFERENCE_TIME - timedelta(minutes=1),
        )


def test_optional_review_and_effective_periods_are_supported() -> None:
    resolution = valid_resolution()
    bounded = valid_patch(
        effective_from=REFERENCE_TIME - timedelta(days=1),
        effective_to=REFERENCE_TIME + timedelta(days=1),
    )
    assert resolution.effective_to is None
    assert bounded.effective_to == REFERENCE_TIME + timedelta(days=1)


def test_policy_report_derives_failed_checks_and_exposes_aliases() -> None:
    report = PolicyCIReport(
        phase=PolicyCIPhase.PRE_APPROVAL,
        patch_id="p",
        resolution_id="r",
        reference_time_utc=REFERENCE_TIME,
        overall_status=PolicyCIStatus.AWAITING_HUMAN,
        checks=[
            PolicyCICheckResult(check_id=MandatoryCheck.CLAIM_SUBSET, status=CheckStatus.FAIL),
            PolicyCICheckResult(
                check_id=MandatoryCheck.EVIDENCE_COMPLETENESS,
                status=CheckStatus.PASS,
            ),
        ],
    )
    assert report.failed_check_ids == [MandatoryCheck.CLAIM_SUBSET]
    assert report.check_results == report.checks
    assert report.status_for("CLAIM_SUBSET") is CheckStatus.FAIL
    with pytest.raises(KeyError):
        report.status_for(MandatoryCheck.SCOPE_CONTAINMENT)
    assert report.all_mandatory_checks_pass is False


def test_complete_policy_report_passes_all_mandatory_checks() -> None:
    report = PolicyCIReport(
        phase=PolicyCIPhase.ACTIVATION,
        patch_id="p",
        resolution_id="r",
        reference_time_utc=REFERENCE_TIME,
        overall_status=PolicyCIStatus.APPROVED,
        checks=[
            PolicyCICheckResult(check_id=check, status=CheckStatus.PASS)
            for check in MANDATORY_CHECK_ORDER
        ],
    )
    assert report.failed_check_ids == []
    assert report.all_mandatory_checks_pass is True


def test_release_request_release_and_overlay_models_normalize_time() -> None:
    request = KnowledgeReleaseRequest(
        request_id="request",
        case_id="case",
        patch_id="patch",
        release_id="release",
        requested_by_role_id="owner",
        requested_at_utc=REFERENCE_TIME,
        expected_outcome="ACTIVE",
    )
    release = KnowledgeRelease(
        release_id="release",
        version="2.0.0",
        patch_ids=["patch"],
        created_at_utc=REFERENCE_TIME,
        activated_at_utc=REFERENCE_TIME,
        activated_by_role_id="owner",
        status=ReleaseStatus.ACTIVE,
    )
    unit = OverlayEvidenceUnit(
        overlay_ref="local://knowledge-overlay/release/patch#claim-claim-1",
        release_id="release",
        patch_id="patch",
        claim_id="claim-1",
        text="claim",
        scope=Scope(),
        source_resolution_id="resolution",
        approval_id="approval",
        effective_from=REFERENCE_TIME,
    )
    snapshot = KnowledgeOverlaySnapshot(
        release_id=release.release_id,
        release_version=release.release_version,
        reference_time_utc=REFERENCE_TIME,
        active_patch_ids=["patch"],
        evidence_units=[unit],
    )
    assert request.requested_at_utc == REFERENCE_TIME
    assert release.release_version == "2.0.0"
    assert snapshot.evidence_units[0].overlay_ref.endswith("#claim-claim-1")


def test_overlay_unit_rejects_bad_reference_and_period() -> None:
    with pytest.raises(ValidationError):
        OverlayEvidenceUnit(
            overlay_ref="local://wrong/patch#claim-id",
            release_id="release",
            patch_id="patch",
            claim_id="id",
            text="claim",
            scope=Scope(),
            source_resolution_id="resolution",
            approval_id="approval",
            effective_from=REFERENCE_TIME,
        )
    with pytest.raises(ValidationError):
        OverlayEvidenceUnit(
            overlay_ref="local://knowledge-overlay/release/patch#claim-id",
            release_id="release",
            patch_id="patch",
            claim_id="id",
            text="claim",
            scope=Scope(),
            source_resolution_id="resolution",
            approval_id="approval",
            effective_from=REFERENCE_TIME,
            effective_to=REFERENCE_TIME,
        )


def test_event_and_regression_result_contracts() -> None:
    event = GovernanceEvent(
        event_id="event",
        event_type=GovernanceEventType.PATCH_PROPOSED,
        timestamp_utc=REFERENCE_TIME,
        patch_id="patch",
        new_status=PatchStatus.PROPOSED,
    )
    passed = RegressionGateResult(expected=45, matched=45)
    failed = RegressionGateResult(expected=45, matched=44)
    network = RegressionGateResult(expected=45, matched=45, network_enabled=True)
    assert event.timestamp_utc == REFERENCE_TIME
    assert passed.passed is True
    assert failed.passed is False
    assert network.passed is False


def test_patch_and_governed_patch_ids_are_exposed() -> None:
    resolution = valid_resolution()
    patch = valid_patch(resolution)
    assert patch.status is PatchStatus.PROPOSED
    assert patch.risk_level is PatchRiskLevel.NORMAL
