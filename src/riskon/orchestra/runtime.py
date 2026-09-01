"""M4A zero-worker orchestration runtime."""

from collections.abc import Callable
from typing import Protocol

from riskon.models import Decision, PlannedVerifiedRun, RoutedRun, RoutingContext
from riskon.orchestra.activation import M4A_SUPPORTED_PROFILES, validate_m4a_activation
from riskon.orchestra.case_capsule import build_case_capsule
from riskon.orchestra.errors import OrchestraWorkersNotImplementedError
from riskon.orchestra.models import (
    ActivationProfile,
    InvestigationPlan,
    OrchestraContext,
    OrchestraMetrics,
    OrchestraRun,
)
from riskon.orchestra.policy import ActivationPolicy


class OrchestraAuditSink(Protocol):
    """Small audit boundary used by the runtime without importing audit code."""

    def append(self, run: OrchestraRun) -> None:
        """Append one successful orchestration run."""


RoutePlanned = Callable[[PlannedVerifiedRun, RoutingContext, str], RoutedRun]


class M4AOrchestrator:
    """Execute only M4A's FAST, clarification, and human-first paths."""

    def __init__(
        self,
        policy: ActivationPolicy,
        route_planned: RoutePlanned,
        *,
        audit_sink: OrchestraAuditSink | None = None,
        network_enabled: bool = False,
    ) -> None:
        self.policy = policy
        self.route_planned = route_planned
        self.audit_sink = audit_sink
        self.network_enabled = network_enabled

    def orchestrate_planned(
        self,
        planned_verified_run: PlannedVerifiedRun,
        orchestration_context: OrchestraContext,
        orchestration_profile: str,
    ) -> OrchestraRun:
        """Run one zero-worker path over a semantically frozen planned run."""

        if self.network_enabled:
            raise ValueError("M4A requires network_enabled = false")
        before = planned_verified_run.model_dump(mode="json")
        profile = self.policy.coerce_profile(orchestration_profile)
        validated_signals = self.policy.validate_risk_signals(orchestration_context.risk_signals)
        profile_spec = self.policy.profile(profile)

        if profile not in M4A_SUPPORTED_PROFILES:
            raise OrchestraWorkersNotImplementedError(
                profile.value,
                [str(role) for role in profile_spec.available_worker_roles],
            )

        baseline_result = planned_verified_run.verified_run.result
        validate_m4a_activation(
            self.policy,
            profile,
            baseline_result.decision,
            orchestration_context,
        )
        baseline_run = PlannedVerifiedRun.model_validate(before)
        routed_run: RoutedRun | None = None
        case_capsule = None

        if profile is ActivationProfile.HUMAN_FIRST:
            routing_context = orchestration_context.routing_context
            if routing_context is None:  # Defensive; activation validation also enforces this.
                raise ValueError("HUMAN_FIRST requires routing_context")
            routed = self.route_planned(
                planned_verified_run,
                routing_context,
                orchestration_context.routing_profile,
            )
            if routed.expert_route is None:
                raise ValueError("HUMAN_FIRST route_planned returned no expert route")
            routed_run = routed.model_copy(deep=True)
            routed_run.planned_verified_run = baseline_run.model_copy(deep=True)
            case_capsule = build_case_capsule(baseline_run, routed_run)

        after = planned_verified_run.model_dump(mode="json")
        if after != before:
            raise RuntimeError("M4A orchestration mutated the PlannedVerifiedRun baseline")

        run = OrchestraRun(
            baseline_run=baseline_run,
            activation_profile=profile,
            risk_signals=validated_signals,
            investigation_plan=InvestigationPlan(
                activation_profile=profile,
                required_agent_roles=[],
                task_ids=[],
                worker_execution_required=False,
            ),
            agent_tasks=[],
            findings=[],
            candidate_claims=[],
            material_objections=[],
            counterfactual_results=[],
            final_verified_run=baseline_run.verified_run.model_copy(deep=True),
            routed_run=routed_run,
            case_capsule=case_capsule,
            orchestra_metrics=OrchestraMetrics(
                active_agent_count=0,
                task_count=0,
                finding_count=0,
                candidate_claim_count=0,
                material_objection_count=0,
                counterfactual_count=0,
                worker_execution_count=0,
            ),
        )
        if run.final_verified_run.model_dump(mode="json") != baseline_run.verified_run.model_dump(
            mode="json"
        ):
            raise RuntimeError("M4A final_verified_run diverged from the baseline")
        if (
            profile is ActivationProfile.FAST_PATH
            and baseline_result.decision is not Decision.ANSWER
        ):
            raise ValueError("FAST_PATH produced an unexpected final decision")
        if self.audit_sink is not None:
            self.audit_sink.append(run)
        return run
