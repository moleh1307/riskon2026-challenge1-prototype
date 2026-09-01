"""End-to-end service gates for governed M5B patch evolution."""

import pytest
from m5b_helpers import (
    REFERENCE_TIME,
    StubCounterfactualGate,
    StubRegressionGate,
    case_inputs,
    config,
    loaded_candidate,
    service,
    valid_approval,
)
from test_m5b_release_activation import passing_report

from riskon.governance.errors import (
    ExpiredPatchError,
    GovernanceError,
    MandatoryPolicyChecksFailedError,
    OfficialCorpusMutationError,
    ReleaseActivationError,
    SelfApprovalError,
)
from riskon.governance.models import (
    ApprovalDecision,
    EvaluatedPatch,
    GovernanceEventType,
    KnowledgeRelease,
    PatchStatus,
    PolicyCICheckResult,
    PolicyCIPhase,
    ReleaseStatus,
)


def test_service_loads_all_frozen_case_inputs_and_release_requests(tmp_path) -> None:
    instance = service(tmp_path)
    for case_id in ("M5A-046", "M5A-047", "M5A-048", "M5A-049", "M5A-050"):
        capsule, resolution, patch, approval = case_inputs(instance, case_id)
        assert capsule.capsule_id.endswith(case_id)
        assert resolution.resolution_id.endswith("RESOLUTION")
        assert patch.patch_id.endswith("PATCH")
        assert approval is None or approval.patch_id == patch.patch_id
        assert instance.load_release_request(case_id).case_id == case_id


def test_unknown_case_and_unknown_release_request_fail_clearly(tmp_path) -> None:
    instance = service(tmp_path)
    with pytest.raises(KeyError):
        instance.load_case_inputs("M5A-999")
    with pytest.raises(StopIteration):
        instance.load_release_request("M5A-999")


def test_reference_resolver_is_local_and_traversal_safe(tmp_path) -> None:
    instance = service(tmp_path)
    assert (
        instance.resolve_reference("local://synthetic-m5a/evaluation_cases.json#case") is not None
    )
    assert instance.resolve_reference("local://synthetic-m5a/evaluation-cases.json#case") is None
    assert instance.resolve_reference("local://synthetic-m5a/../secret.json") is None
    assert instance.resolve_reference("https://example.com/evidence") is None
    with pytest.raises(FileNotFoundError):
        instance._read_ref("local://synthetic-m5a/missing.json")


def test_policy_ci_caches_regression_and_uses_injected_counterfactual(tmp_path) -> None:
    regression = StubRegressionGate()
    counterfactual = StubCounterfactualGate(count=4)
    instance = service(tmp_path, regression=regression, counterfactual=counterfactual)
    capsule, resolution, patch, approval = loaded_candidate(instance)
    first = instance.run_policy_ci(
        capsule, resolution, patch, approval, REFERENCE_TIME, PolicyCIPhase.ACTIVATION
    )
    second = instance.run_policy_ci(
        capsule, resolution, patch, approval, REFERENCE_TIME, PolicyCIPhase.ACTIVATION
    )
    assert first.regression == second.regression
    assert regression.calls == 1
    assert counterfactual.calls == 2
    assert len(instance.event_store.events) == 2


@pytest.mark.parametrize(
    "field",
    ["recursive_policy_ci_enabled", "counterfactual_routing_enabled"],
)
def test_disabled_recursive_governance_features_raise(tmp_path, field: str) -> None:
    base = config()
    policy_ci = base.governance.policy_ci.model_copy(update={field: True})
    bad_config = base.model_copy(
        update={"governance": base.governance.model_copy(update={"policy_ci": policy_ci})}
    )
    instance = service(tmp_path)
    instance.config = bad_config
    capsule, resolution, patch, approval = loaded_candidate(instance)
    with pytest.raises(GovernanceError, match="disabled"):
        instance.run_policy_ci(
            capsule, resolution, patch, approval, REFERENCE_TIME, PolicyCIPhase.ACTIVATION
        )


def test_official_corpus_mutation_is_rejected_at_service_creation(tmp_path) -> None:
    base = config()
    governance = base.governance.model_copy(update={"official_corpus_mutation_enabled": True})
    bad_config = base.model_copy(update={"governance": governance})
    with pytest.raises(OfficialCorpusMutationError):
        service(tmp_path).__class__(bad_config)  # type: ignore[attr-defined]


def test_proposal_and_awaiting_events_are_append_only(tmp_path) -> None:
    instance = service(tmp_path)
    instance.set_event_clock(REFERENCE_TIME)
    capsule, resolution, patch, _ = loaded_candidate(instance)
    del capsule
    instance.record_proposal(resolution, patch)
    instance.record_awaiting_approval(resolution, patch)
    assert [item.event_type for item in instance.event_store.events] == [
        GovernanceEventType.PATCH_PROPOSED,
        GovernanceEventType.PATCH_AWAITING_APPROVAL,
    ]
    assert [item.event_id for item in instance.event_store.events] == [
        "m5b-event-0001",
        "m5b-event-0002",
    ]
    assert all(item.timestamp_utc == REFERENCE_TIME for item in instance.event_store.events)


def test_apply_independent_approval_keeps_patch_nonactive(tmp_path) -> None:
    instance = service(tmp_path)
    capsule, resolution, patch, approval = loaded_candidate(instance)
    report = instance.run_policy_ci(
        capsule, resolution, patch, approval, REFERENCE_TIME, PolicyCIPhase.ACTIVATION
    )
    evaluated = EvaluatedPatch(
        case_capsule=capsule,
        expert_resolution=resolution,
        knowledge_patch=patch,
        policy_ci_report=report,
    )
    governed = instance.apply_human_decision(evaluated, approval)
    assert governed.status is PatchStatus.APPROVED
    assert governed.patch_id == patch.patch_id


def test_apply_rejection_records_rejected_patch(tmp_path) -> None:
    instance = service(tmp_path)
    capsule, resolution, patch, approval = loaded_candidate(instance, "M5A-048")
    assert approval is not None
    report = instance.run_policy_ci(
        capsule, resolution, patch, approval, REFERENCE_TIME, PolicyCIPhase.PRE_APPROVAL
    )
    governed = instance.apply_human_decision(
        EvaluatedPatch(
            case_capsule=capsule,
            expert_resolution=resolution,
            knowledge_patch=patch,
            policy_ci_report=report,
        ),
        approval,
    )
    assert governed.status is PatchStatus.REJECTED
    assert instance.event_store.events[-1].event_type is GovernanceEventType.PATCH_REJECTED


def test_apply_human_decision_rejects_mismatch_selfapproval_and_failed_report(tmp_path) -> None:
    instance = service(tmp_path)
    capsule, resolution, patch, approval = loaded_candidate(instance)
    assert approval is not None
    report = instance.run_policy_ci(
        capsule, resolution, patch, approval, REFERENCE_TIME, PolicyCIPhase.ACTIVATION
    )
    evaluated = EvaluatedPatch(
        case_capsule=capsule,
        expert_resolution=resolution,
        knowledge_patch=patch,
        policy_ci_report=report,
    )
    with pytest.raises(ReleaseActivationError, match="does not match"):
        instance.apply_human_decision(
            evaluated,
            valid_approval(patch, resolution, patch_id="other"),
        )
    with pytest.raises(SelfApprovalError):
        instance.apply_human_decision(
            evaluated,
            valid_approval(patch, resolution, actor=resolution.resolution_author_role_id),
        )
    failed = report.model_copy(
        update={
            "checks": [
                PolicyCICheckResult(
                    check_id=report.checks[0].check_id,
                    status="FAIL",
                    details="forced test failure",
                )
            ]
        }
    )
    with pytest.raises(MandatoryPolicyChecksFailedError):
        instance.apply_human_decision(
            evaluated.model_copy(update={"policy_ci_report": failed}), approval
        )


def approved_governed(instance, case_id: str = "M5A-046"):
    capsule, resolution, patch, approval = loaded_candidate(instance, case_id)
    assert approval is not None
    report = instance.run_policy_ci(
        capsule, resolution, patch, approval, REFERENCE_TIME, PolicyCIPhase.ACTIVATION
    )
    return instance.apply_human_decision(
        EvaluatedPatch(
            case_capsule=capsule,
            expert_resolution=resolution,
            knowledge_patch=patch,
            policy_ci_report=report,
        ),
        approval,
    )


def test_activate_release_moves_approved_patch_to_active_and_versions_from_fixture(
    tmp_path,
) -> None:
    instance = service(tmp_path)
    instance.set_event_clock(REFERENCE_TIME)
    governed = approved_governed(instance)
    release = instance.activate_release(
        (governed,), instance.load_release_request("M5A-046"), REFERENCE_TIME
    )
    assert release.release_id == "KB-SYN-V2"
    assert release.version == "2.0.0"
    assert release.previous_release_id == "KB-SYN-V1"
    assert instance.event_store.events[-1].event_type is GovernanceEventType.RELEASE_ACTIVATED
    assert instance._governed_patches[governed.patch_id].status is PatchStatus.ACTIVE


def test_activate_release_rejects_invalid_approval_and_statuses(tmp_path) -> None:
    instance = service(tmp_path)
    governed = approved_governed(instance)
    with pytest.raises(ReleaseActivationError, match="reached APPROVED"):
        instance.activate_release(
            (governed.model_copy(update={"status": PatchStatus.TESTED}),),
            instance.load_release_request("M5A-046"),
            REFERENCE_TIME,
        )
    with pytest.raises(ExpiredPatchError):
        instance.activate_release(
            (governed.model_copy(update={"status": PatchStatus.EXPIRED}),),
            instance.load_release_request("M5A-046"),
            REFERENCE_TIME,
        )
    rejected_approval = valid_approval(
        governed.knowledge_patch,
        governed.expert_resolution,
        decision=ApprovalDecision.REJECT,
    )
    with pytest.raises(ReleaseActivationError, match="APPROVE"):
        instance.activate_release(
            (governed.model_copy(update={"approval": rejected_approval}),),
            instance.load_release_request("M5A-046"),
            REFERENCE_TIME,
        )


def test_activate_release_rejects_selfapproval_and_failed_ci(tmp_path) -> None:
    instance = service(tmp_path)
    governed = approved_governed(instance)
    self_approval = valid_approval(
        governed.knowledge_patch,
        governed.expert_resolution,
        actor=governed.expert_resolution.resolution_author_role_id,
    )
    with pytest.raises(ReleaseActivationError, match="Self-approved"):
        instance.activate_release(
            (governed.model_copy(update={"approval": self_approval}),),
            instance.load_release_request("M5A-046"),
            REFERENCE_TIME,
        )
    failed_report = passing_report(
        governed.patch_id, governed.expert_resolution.resolution_id
    ).__class__(
        phase=PolicyCIPhase.ACTIVATION,
        patch_id=governed.patch_id,
        resolution_id=governed.expert_resolution.resolution_id,
        reference_time_utc=REFERENCE_TIME,
        overall_status="FAIL",
        checks=[PolicyCICheckResult(check_id="CLAIM_SUBSET", status="FAIL")],
    )
    with pytest.raises(MandatoryPolicyChecksFailedError):
        instance.activate_release(
            (governed.model_copy(update={"policy_ci_report": failed_report}),),
            instance.load_release_request("M5A-046"),
            REFERENCE_TIME,
        )


def test_compile_overlay_returns_snapshot_and_excludes_expired_stored_patch(tmp_path) -> None:
    instance = service(tmp_path)
    governed = approved_governed(instance)
    release = instance.activate_release(
        (governed,), instance.load_release_request("M5A-046"), REFERENCE_TIME
    )
    snapshot = instance.compile_overlay(release, REFERENCE_TIME)
    assert snapshot.active_patch_ids == [governed.patch_id]
    assert len(snapshot.evidence_units) == 1
    expired = instance._governed_patches[governed.patch_id].model_copy(
        update={
            "knowledge_patch": governed.knowledge_patch.model_copy(
                update={"effective_to": REFERENCE_TIME}
            )
        }
    )
    instance._governed_patches[governed.patch_id] = expired
    excluded = instance.compile_overlay(release, REFERENCE_TIME)
    assert excluded.active_patch_ids == []
    assert excluded.excluded_patch_ids == [governed.patch_id]


def test_compile_overlay_rejects_nonactive_release_and_unsafe_config(tmp_path) -> None:
    instance = service(tmp_path)
    nonactive = KnowledgeRelease(
        release_id="release",
        version="1.0.0",
        patch_ids=[],
        created_at_utc=REFERENCE_TIME,
        activated_at_utc=REFERENCE_TIME,
        activated_by_role_id="owner",
        status=ReleaseStatus.SUPERSEDED,
    )
    with pytest.raises(ReleaseActivationError):
        instance.compile_overlay(nonactive, REFERENCE_TIME)
    governed = approved_governed(instance)
    release = instance.activate_release(
        (governed,), instance.load_release_request("M5A-046"), REFERENCE_TIME
    )
    for field in ("special_ranking_boost", "include_expired_patches"):
        overlay = instance.config.governance.overlay.model_copy(update={field: True})
        instance.config = instance.config.model_copy(
            update={
                "governance": instance.config.governance.model_copy(update={"overlay": overlay})
            }
        )
        with pytest.raises(GovernanceError, match="disabled"):
            instance.compile_overlay(release, REFERENCE_TIME)
        instance.config = config()


def test_counterfactual_runner_can_be_installed(tmp_path) -> None:
    instance = service(tmp_path)

    def runner(snapshot, query):
        del snapshot, query
        return object()

    instance.set_counterfactual_runner(runner)
    assert instance._counterfactual_runner is runner
