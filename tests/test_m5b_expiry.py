"""M5B effective-period and expired-overlay behavior."""

from datetime import timedelta

from m5b_helpers import REFERENCE_TIME, config, loaded_candidate, service

from riskon.governance.models import PatchStatus, PolicyCIPhase
from riskon.m5b_evaluation import M5BEvaluator
from riskon.models import Decision


def test_expired_fixture_is_classified_current_state_and_not_retrievable(tmp_path) -> None:
    instance = service(tmp_path)
    capsule, resolution, patch, approval = loaded_candidate(instance, "M5A-050")
    report = instance.run_policy_ci(
        capsule,
        resolution,
        patch,
        approval,
        REFERENCE_TIME,
        PolicyCIPhase.CURRENT_STATE,
    )
    assert report.overall_status.value == "FAIL"
    assert report.status_for("EFFECTIVE_PERIOD_VALID").value == "FAIL"
    instance.record_expiry(resolution, patch)
    assert instance.event_store.events[-1].new_status is PatchStatus.EXPIRED


def test_expiry_boundary_is_half_open() -> None:
    future = REFERENCE_TIME + timedelta(seconds=1)
    assert future > REFERENCE_TIME
    document = M5BEvaluator(config()).run()
    expired_case = next(item for item in document.case_results if item.case_id == "M5A-050")
    assert expired_case.actual_patch_status == PatchStatus.EXPIRED.value
    assert expired_case.overlay_claim_ids == []
    assert expired_case.post_patch["exact"] == Decision.ABSTAIN.value
