"""Policy CI coordinator, phases, and mandatory-check ordering."""

from datetime import timedelta

import pytest
from m5b_helpers import (
    LOCAL_REF,
    REFERENCE_TIME,
    StubCounterfactualGate,
    StubRegressionGate,
    valid_approval,
    valid_claim,
    valid_patch,
    valid_resolution,
    valid_scope,
)

from riskon.governance.models import (
    ActorType,
    ApprovalDecision,
    CheckStatus,
    ClaimRelation,
    MandatoryCheck,
    PolicyCIPhase,
    PolicyCIStatus,
)
from riskon.governance.policy_ci import PolicyCIExecutor, expected_check_ids


def executor(
    *,
    regression: StubRegressionGate | None = None,
    counterfactual: StubCounterfactualGate | None = None,
    relations: list[ClaimRelation] | None = None,
    resolver: object | None = None,
) -> PolicyCIExecutor:
    regression_gate = regression or StubRegressionGate()
    counterfactual_gate = counterfactual or StubCounterfactualGate()

    def regression_result():
        result = regression_gate.run()
        return result.passed, f"stub regression {result.matched}/{result.expected}", result.suites

    def counterfactual_result(patch):
        return counterfactual_gate.evaluate(patch, [])

    return PolicyCIExecutor(
        relations or [],
        (lambda _reference: object()) if resolver is None else resolver,  # type: ignore[arg-type]
        regression_result,
        counterfactual_result,
    )


def run_valid(phase: PolicyCIPhase, approval: object | None = None):
    resolution = valid_resolution()
    patch = valid_patch(resolution)
    return executor().run(resolution, patch, approval, REFERENCE_TIME, phase)


@pytest.mark.parametrize(
    ("phase", "approval", "overall"),
    [
        (PolicyCIPhase.PRE_APPROVAL, None, PolicyCIStatus.AWAITING_HUMAN),
        (
            PolicyCIPhase.ACTIVATION,
            valid_approval(),
            PolicyCIStatus.APPROVED,
        ),
        (PolicyCIPhase.CURRENT_STATE, None, PolicyCIStatus.CURRENT_OR_EXPIRED),
    ],
)
def test_policy_ci_phase_outcomes_and_exact_order(
    phase: PolicyCIPhase,
    approval: object | None,
    overall: PolicyCIStatus,
) -> None:
    report = run_valid(phase, approval)
    assert report.overall_status is overall
    assert [item.check_id for item in report.checks] == list(expected_check_ids())
    assert len(report.checks) == 11
    human = report.status_for(MandatoryCheck.HUMAN_APPROVAL_PRESENT)
    assert human is (
        CheckStatus.NOT_RUN
        if approval is None and phase is PolicyCIPhase.PRE_APPROVAL
        else CheckStatus.PASS
    )


@pytest.mark.parametrize(
    "mutator,check",
    [
        (
            lambda resolution, patch: (
                valid_resolution(claims=[valid_claim(evidence_refs=[])]),
                patch,
            ),
            MandatoryCheck.EVIDENCE_COMPLETENESS,
        ),
        (
            lambda resolution, patch: (
                resolution,
                valid_patch(resolution, claims=[valid_claim("foreign")]),
            ),
            MandatoryCheck.CLAIM_SUBSET,
        ),
        (
            lambda resolution, patch: (
                resolution,
                valid_patch(resolution, scope=valid_scope(regions=["REGION_ALPHA"])),
            ),
            MandatoryCheck.SCOPE_CONTAINMENT,
        ),
        (
            lambda resolution, patch: (
                resolution,
                valid_patch(resolution, claims=[valid_claim("contradiction")]),
            ),
            MandatoryCheck.CONTRADICTION_DETECTION,
        ),
        (
            lambda resolution, patch: (
                resolution,
                valid_patch(resolution, refs=["local://synthetic-m5a/missing.json"]),
            ),
            MandatoryCheck.REFERENCE_RESOLUTION,
        ),
    ],
)
def test_policy_ci_reports_input_check_failures(mutator: object, check: MandatoryCheck) -> None:
    resolution = valid_resolution()
    patch = valid_patch(resolution)
    changed_resolution, changed_patch = mutator(resolution, patch)  # type: ignore[operator]
    relations = (
        [
            ClaimRelation(
                left_claim_id="contradiction",
                right_claim_id="authoritative",
                relation="CONTRADICTS",
                evidence_refs=[LOCAL_REF],
            )
        ]
        if check is MandatoryCheck.CONTRADICTION_DETECTION
        else []
    )
    resolver = (lambda _reference: None) if check is MandatoryCheck.REFERENCE_RESOLUTION else None
    report = executor(relations=relations, resolver=resolver).run(
        changed_resolution,
        changed_patch,
        None,
        REFERENCE_TIME,
        PolicyCIPhase.PRE_APPROVAL,
    )
    assert report.status_for(check) is CheckStatus.FAIL
    assert report.overall_status is PolicyCIStatus.FAIL
    assert check in report.failed_check_ids


def test_policy_ci_reports_critical_control_failure() -> None:
    claim = valid_claim("critical", critical=True)
    resolution = valid_resolution(claims=[claim])
    patch = valid_patch(resolution, claims=[claim])
    relation = ClaimRelation(
        left_claim_id="critical",
        right_claim_id="old",
        relation="CONTRADICTS",
        critical=True,
        evidence_refs=[LOCAL_REF],
    )
    report = executor(relations=[relation]).run(
        resolution, patch, None, REFERENCE_TIME, PolicyCIPhase.PRE_APPROVAL
    )
    assert report.status_for(MandatoryCheck.CRITICAL_CONTROL_PRESERVATION) is CheckStatus.FAIL


def test_policy_ci_reports_regression_failure() -> None:
    gate = StubRegressionGate(passed=False)
    report = executor(regression=gate).run(
        valid_resolution(), valid_patch(), None, REFERENCE_TIME, PolicyCIPhase.PRE_APPROVAL
    )
    assert report.status_for(MandatoryCheck.M0_M4D_REGRESSION) is CheckStatus.FAIL
    assert gate.calls == 1


def test_policy_ci_reports_counterfactual_failure() -> None:
    gate = StubCounterfactualGate(passed=False)
    report = executor(counterfactual=gate).run(
        valid_resolution(), valid_patch(), None, REFERENCE_TIME, PolicyCIPhase.PRE_APPROVAL
    )
    assert report.status_for(MandatoryCheck.COUNTERFACTUAL_CONTAINMENT) is CheckStatus.FAIL
    assert report.counterfactual_transitions == 0


def test_policy_ci_reports_separation_failure_from_knowledge_owner() -> None:
    resolution = valid_resolution(author="same-role", owner="same-role")
    report = executor().run(
        resolution,
        valid_patch(resolution),
        None,
        REFERENCE_TIME,
        PolicyCIPhase.PRE_APPROVAL,
    )
    assert report.status_for(MandatoryCheck.SEPARATION_OF_DUTIES) is CheckStatus.FAIL


def test_policy_ci_reports_human_actor_failure_when_present() -> None:
    resolution = valid_resolution()
    patch = valid_patch(resolution)
    approval = valid_approval(patch, resolution, actor_type=ActorType.AGENT_ROLE)
    report = executor().run(
        resolution,
        patch,
        approval,
        REFERENCE_TIME,
        PolicyCIPhase.ACTIVATION,
    )
    assert report.status_for(MandatoryCheck.HUMAN_APPROVAL_PRESENT) is CheckStatus.FAIL


@pytest.mark.parametrize(
    "effective_from,effective_to",
    [
        (REFERENCE_TIME + timedelta(days=1), None),
        (REFERENCE_TIME - timedelta(days=2), REFERENCE_TIME - timedelta(days=1)),
    ],
)
def test_policy_ci_effective_period_gate(effective_from, effective_to) -> None:
    resolution = valid_resolution(effective_from=effective_from, effective_to=effective_to)
    patch = valid_patch(
        resolution,
        effective_from=effective_from,
        effective_to=effective_to,
    )
    report = executor().run(resolution, patch, None, REFERENCE_TIME, PolicyCIPhase.CURRENT_STATE)
    assert report.status_for(MandatoryCheck.EFFECTIVE_PERIOD_VALID) is CheckStatus.FAIL


def test_policy_ci_passes_rejected_human_decision_as_a_recorded_decision() -> None:
    resolution = valid_resolution()
    patch = valid_patch(resolution)
    approval = valid_approval(patch, resolution, decision=ApprovalDecision.REJECT)
    report = executor().run(resolution, patch, approval, REFERENCE_TIME, PolicyCIPhase.PRE_APPROVAL)
    assert report.status_for(MandatoryCheck.HUMAN_APPROVAL_PRESENT) is CheckStatus.PASS
    assert report.overall_status is PolicyCIStatus.AWAITING_HUMAN


def test_policy_ci_rejects_non_local_authoritative_reference() -> None:
    resolution = valid_resolution(
        refs=["file:///tmp/evidence"],
        claims=[valid_claim(evidence_refs=["file:///tmp/evidence"])],
    )
    patch = valid_patch(
        resolution,
        refs=["file:///tmp/evidence"],
        claims=[valid_claim(evidence_refs=["file:///tmp/evidence"])],
    )
    report = executor().run(resolution, patch, None, REFERENCE_TIME, PolicyCIPhase.PRE_APPROVAL)
    assert report.status_for(MandatoryCheck.REFERENCE_RESOLUTION) is CheckStatus.FAIL
