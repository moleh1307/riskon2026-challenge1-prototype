"""M4D unified deterministic orchestra runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from riskon.models import (
    AnswerClaim,
    Decision,
    DetectedContext,
    PipelineResult,
    PlannedVerifiedRun,
    QueryInput,
    ReasonCode,
    Route,
    RoutedRun,
    RoutingContext,
    VerificationReport,
    VerificationStatus,
    VerifiedRun,
)
from riskon.orchestra.adjudication import (
    ExistingM1Adjudicator,
    MaterialObjectionGate,
    adjudicate,
)
from riskon.orchestra.case_capsule import build_case_capsule
from riskon.orchestra.claim_builder import DeterministicClaimBuilder
from riskon.orchestra.counterfactual_models import (
    CounterfactualExecutionResult,
    CounterfactualPlan,
    CounterfactualSummary,
    CounterfactualVariant,
)
from riskon.orchestra.counterfactual_planner import CounterfactualPlanner
from riskon.orchestra.counterfactual_policy import CounterfactualExecutionPolicy
from riskon.orchestra.counterfactual_runner import (
    CounterfactualRunner,
    LocalPlannedPipelineCounterfactualRunner,
)
from riskon.orchestra.errors import (
    OrchestraConfigurationError,
    OrchestraExecutionBudgetExceededError,
    OrchestraFailClosedError,
    OrchestraWorkerExecutionError,
)
from riskon.orchestra.executor import BoundedWorkerExecutor
from riskon.orchestra.failure_policy import FailurePolicy
from riskon.orchestra.ledger import EvidenceLedger
from riskon.orchestra.models import (
    ActivationProfile,
    AgentFinding,
    AgentTask,
    CaseCapsule,
    ExecutionWave,
    InvestigationPlan,
    MaterialObjection,
    OrchestraContext,
    OrchestraMetrics,
    OrchestraRun,
    RiskAssessment,
    RiskSignal,
    WorkerDiagnostic,
    WorkerResult,
)
from riskon.orchestra.policy import WorkerSelectionPolicy
from riskon.orchestra.risk_signals import OrchestraRiskSignalDetector
from riskon.orchestra.runtime_diagnostics import build_runtime_diagnostics
from riskon.orchestra.runtime_policy import RuntimePolicy
from riskon.orchestra.source_safety import (
    LocalCorpus,
    SourceSafetyContext,
    SourceSafetyPolicy,
    SourceSafetyReport,
)
from riskon.orchestra.tasks import AgentCatalog
from riskon.orchestra.worker_selection import WorkerSelector
from riskon.orchestra.workers import (
    CounterfactualSentinel,
    EvidenceScout,
    ProcessTableScout,
    ScopeSentinel,
    Skeptic,
)
from riskon.verification import VerificationEngine

RunPlanned = Callable[[QueryInput], PlannedVerifiedRun]
RoutePlanned = Callable[[PlannedVerifiedRun, RoutingContext, str], RoutedRun]
LegacyRoute = Callable[[DetectedContext, list[ReasonCode]], Route]


class RuntimeAuditSink(Protocol):
    """Audit boundary used by the unified runtime."""

    def append_success(
        self,
        run: OrchestraRun,
        *,
        request: QueryInput | None = None,
        assessment: RiskAssessment | None = None,
    ) -> None:
        """Append a successful or safely completed run."""

    def append_failure(
        self,
        *,
        trace_id: str,
        baseline_trace_id: str,
        baseline_decision: str,
        activation_profile: str,
        failed_stage: str,
        failed_task_ids: list[str],
        cause_types: list[str],
        fallback_action: str,
        answer_returned: bool = False,
        route_returned: bool = False,
    ) -> None:
        """Append a failure row without answer content."""


class UnifiedOrchestraRuntime:
    """Run M4D activation, bounded workers, and local counterfactual checks."""

    def __init__(
        self,
        runtime_policy: RuntimePolicy,
        failure_policy: FailurePolicy,
        worker_policy: WorkerSelectionPolicy,
        catalog: AgentCatalog,
        corpus: LocalCorpus,
        source_safety_policy: SourceSafetyPolicy,
        m1_verifier: VerificationEngine,
        route_planned: RoutePlanned,
        legacy_route: LegacyRoute,
        counterfactual_policy: CounterfactualExecutionPolicy,
        run_planned: RunPlanned,
        *,
        private_run_planned: RunPlanned | None = None,
        audit_sink: RuntimeAuditSink | None = None,
        network_enabled: bool = False,
        external_api_enabled: bool = False,
        recursive_orchestration_enabled: bool = False,
        counterfactual_routing_enabled: bool = False,
        agent_to_agent_citation_enabled: bool = False,
    ) -> None:
        self.runtime_policy = runtime_policy
        self.failure_policy = failure_policy
        self.worker_policy = worker_policy
        self.catalog = catalog
        self.selector = WorkerSelector(worker_policy, catalog)
        self.corpus = corpus
        self.source_safety_policy = source_safety_policy
        self.m1_adjudicator = ExistingM1Adjudicator(corpus, m1_verifier)
        self.route_planned = route_planned
        self.legacy_route = legacy_route
        self.counterfactual_policy = counterfactual_policy
        self.counterfactual_planner = CounterfactualPlanner(counterfactual_policy)
        self.run_planned = run_planned
        self.private_run_planned = private_run_planned or run_planned
        self.audit_sink = audit_sink
        self.network_enabled = network_enabled
        self.external_api_enabled = external_api_enabled
        self.default_routing_profile = "default"
        self.recursive_orchestration_enabled = recursive_orchestration_enabled
        self.counterfactual_routing_enabled = counterfactual_routing_enabled
        self.agent_to_agent_citation_enabled = agent_to_agent_citation_enabled
        self.detector = OrchestraRiskSignalDetector(
            runtime_policy,
            implemented_dimensions=counterfactual_policy.implemented_dimensions,
        )
        self.local_runner = LocalPlannedPipelineCounterfactualRunner(
            self.private_run_planned,
            maximum_depth=runtime_policy.execution_budget.maximum_counterfactual_depth,
        )
        max_parallel = runtime_policy.execution_budget.maximum_parallel_discovery_workers
        self.executor = BoundedWorkerExecutor(
            {
                "EVIDENCE_SCOUT": EvidenceScout(),
                "SCOPE_SENTINEL": ScopeSentinel(),
                "PROCESS_TABLE_SCOUT": ProcessTableScout(),
                "SKEPTIC": Skeptic(),
                "COUNTERFACTUAL_SENTINEL": CounterfactualSentinel(),
            },
            max_parallel,
        )
        self.last_worker_diagnostics: list[WorkerDiagnostic] = []
        self.last_counterfactual_summary = CounterfactualSummary(
            variant_count=0,
            passed_count=0,
            failed_count=0,
            scope_leak_count=0,
            routing_execution_count=0,
        )
        self._current_run_planned_call_count = 0

    def run_orchestrated(self, request: QueryInput) -> OrchestraRun:
        """Run the exact M4D public flow with one normal planned-pipeline call."""

        self._validate_security()
        if not self.runtime_policy.auto_activation_enabled:
            raise OrchestraConfigurationError("M4D automatic activation is disabled")
        self._current_run_planned_call_count = 0
        baseline = self.run_planned(request)
        self._current_run_planned_call_count = 1
        safety = self._source_safety()
        assessment = self.detector.assess(request, baseline, safety.report)
        context = self._context(request, baseline, assessment)
        return self.orchestrate_planned(
            baseline,
            context,
            assessment.selected_activation_profile.value,
            risk_assessment=assessment,
            source_safety_report=safety.report,
            request=request,
            run_planned_call_count=1,
        )

    def run_orchestrated_with_planned(
        self,
        request: QueryInput,
        baseline: PlannedVerifiedRun,
    ) -> OrchestraRun:
        """Run the M4D activation path over one caller-supplied planned result.

        M5B uses this additive seam to preserve the exact M4D activation and
        worker fan-out logic after its overlay-enabled planning call.  The
        existing ``run_orchestrated`` method remains the normal M4D entrypoint.
        """

        self._validate_security()
        if not self.runtime_policy.auto_activation_enabled:
            raise OrchestraConfigurationError("M4D automatic activation is disabled")
        self._current_run_planned_call_count = 1
        safety = self._source_safety()
        assessment = self.detector.assess(request, baseline, safety.report)
        context = self._context(request, baseline, assessment)
        return self.orchestrate_planned(
            baseline,
            context,
            assessment.selected_activation_profile.value,
            risk_assessment=assessment,
            source_safety_report=safety.report,
            request=request,
            run_planned_call_count=1,
        )

    def orchestrate_planned(
        self,
        planned_verified_run: PlannedVerifiedRun,
        orchestration_context: OrchestraContext,
        orchestration_profile: str,
        *,
        risk_assessment: RiskAssessment | None = None,
        source_safety_report: SourceSafetyReport | None = None,
        request: QueryInput | None = None,
        run_planned_call_count: int = 0,
        counterfactual_plan: CounterfactualPlan | None = None,
        counterfactual_runner: CounterfactualRunner | None = None,
        requested_variants: list[CounterfactualVariant] | None = None,
    ) -> OrchestraRun:
        """Execute one direct or automatically assessed M4D orchestration."""

        self._validate_security()
        self._reset_run_state()
        baseline_before = planned_verified_run.model_dump(mode="json")
        baseline = PlannedVerifiedRun.model_validate(baseline_before)
        signals = self.runtime_policy.validate_signals(orchestration_context.risk_signals)
        try:
            profile = ActivationProfile(orchestration_profile)
        except ValueError as exc:
            raise OrchestraConfigurationError(
                f"Unknown M4D activation profile: {orchestration_profile!r}"
            ) from exc
        assessment = risk_assessment or self._direct_assessment(profile, signals)
        if assessment.selected_activation_profile is not profile:
            raise OrchestraConfigurationError("M4D activation assessment/profile mismatch")
        if assessment.risk_signals != signals:
            raise OrchestraConfigurationError("M4D activation assessment/signal mismatch")
        source_safety = self._source_safety(source_safety_report)
        baseline_result = baseline.verified_run.result

        # A fully validated structural matrix lookup is already a deterministic
        # answer.  It must not be sent through the generic worker fan-out, where
        # a second claim builder or skeptic could reinterpret the source rows.
        if self._is_structural_fast_path(baseline):
            return self._zero_worker_run(
                baseline,
                orchestration_context,
                profile,
                assessment,
                source_safety,
                request=request,
                run_planned_call_count=run_planned_call_count,
                candidate_claim_count=len(baseline.verified_run.verification.supported_claim_ids),
            )

        if profile is ActivationProfile.SHORT_CIRCUIT_CLARIFY:
            if baseline_result.decision is not Decision.CLARIFY:
                raise OrchestraConfigurationError(
                    "SHORT_CIRCUIT_CLARIFY requires a baseline CLARIFY"
                )
            return self._zero_worker_run(
                baseline,
                orchestration_context,
                profile,
                assessment,
                source_safety,
                request=request,
                run_planned_call_count=run_planned_call_count,
            )
        if profile is ActivationProfile.FAST_PATH:
            if baseline_result.decision is not Decision.ANSWER or signals:
                raise OrchestraConfigurationError("FAST_PATH requires an ANSWER with no signals")
            return self._zero_worker_run(
                baseline,
                orchestration_context,
                profile,
                assessment,
                source_safety,
                request=request,
                run_planned_call_count=run_planned_call_count,
            )
        if profile is ActivationProfile.HUMAN_FIRST:
            if baseline_result.decision is not Decision.ABSTAIN:
                raise OrchestraConfigurationError("HUMAN_FIRST requires a baseline ABSTAIN")
            return self._human_first_run(
                baseline,
                orchestration_context,
                profile,
                assessment,
                source_safety,
                request=request,
                run_planned_call_count=run_planned_call_count,
            )
        if profile not in {ActivationProfile.DUAL_CHECK, ActivationProfile.FULL_ORCHESTRA}:
            raise OrchestraConfigurationError(f"M4D does not implement profile {profile.value}")
        if baseline_result.decision is Decision.CLARIFY:
            raise OrchestraConfigurationError("M4D must not execute workers for a CLARIFY baseline")

        effective_context = orchestration_context.model_copy(
            update={
                "structured_context": self.counterfactual_planner.context_for(
                    baseline, orchestration_context.structured_context
                )
            }
        )
        roles = self._roles(profile, signals, effective_context)
        initial_roles = [role for role in roles if role != "COUNTERFACTUAL_SENTINEL"]
        input_refs = self._input_refs(baseline)
        tasks = self.selector.build_tasks(
            baseline.query_plan.plan_id,
            signals,
            input_refs=input_refs,
            requested_roles=initial_roles,
            allow_counterfactual=True,
        )
        try:
            self._check_task_budget(len(tasks))
            discovery_tasks = [
                task for task in tasks if task.execution_wave is ExecutionWave.DISCOVERY
            ]
            challenge_tasks = [
                task for task in tasks if task.execution_wave is ExecutionWave.CHALLENGE
            ]
            safety_context = SourceSafetyContext(
                policy=self.source_safety_policy,
                report=source_safety.report,
            )
            discovery_results = self._execute_wave(
                discovery_tasks,
                baseline,
                effective_context,
                safety_context,
                stage="DISCOVERY",
            )
            ledger = EvidenceLedger(set(self.corpus.provenance.local_refs()))
            discovery_findings = self._findings(discovery_results)
            ledger.append_many(discovery_findings)
            preliminary_claims = (
                DeterministicClaimBuilder(self.corpus, safety_context).build(ledger.findings).claims
            )
            challenge_results = self._execute_wave(
                challenge_tasks,
                baseline,
                effective_context,
                safety_context,
                prior_findings=ledger.findings,
                candidate_claims=list(preliminary_claims),
                stage="CHALLENGE",
            )
            all_worker_results = [*discovery_results, *challenge_results]
            self.last_worker_diagnostics = self._diagnostics(all_worker_results)
            ledger.append_many(self._findings(challenge_results))
            all_objections = self._objections(all_worker_results)
            claim_build = DeterministicClaimBuilder(self.corpus, safety_context).build(
                ledger.findings
            )
            evidence_refs = (
                sorted({ref for claim in claim_build.claims for ref in claim.evidence_refs})
                if claim_build.claims
                else ledger.evidence_refs()
            )
            initial = adjudicate(
                baseline,
                claim_build,
                evidence_refs,
                self.corpus,
                self.m1_adjudicator,
                MaterialObjectionGate().evaluate(all_objections),
            )

            counterfactual_results: list[CounterfactualExecutionResult] = []
            sentinel_results: list[WorkerResult] = []
            if (
                profile is ActivationProfile.FULL_ORCHESTRA
                and baseline_result.decision is Decision.ANSWER
                and initial.result.decision is Decision.ANSWER
                and (
                    "COUNTERFACTUAL_REQUIRED" in {str(signal) for signal in signals}
                    or counterfactual_plan is not None
                    or requested_variants is not None
                )
            ):
                plan = counterfactual_plan or self.counterfactual_planner.plan(
                    baseline,
                    effective_context.structured_context,
                    requested_variants=requested_variants,
                )
                if (
                    len(plan.variants)
                    > self.runtime_policy.execution_budget.maximum_counterfactual_variants
                ):
                    raise OrchestraExecutionBudgetExceededError(
                        "M4D maximum counterfactual variants exceeded"
                    )
                if plan.baseline_plan_id != baseline.query_plan.plan_id:
                    raise OrchestraConfigurationError("M4D counterfactual plan lineage mismatch")
                sentinel_tasks = self.selector.build_tasks(
                    baseline.query_plan.plan_id,
                    signals,
                    input_refs=input_refs,
                    requested_roles=["COUNTERFACTUAL_SENTINEL"],
                    allow_counterfactual=True,
                )
                self._check_task_budget(len(tasks) + len(sentinel_tasks))
                tasks.extend(sentinel_tasks)
                sentinel_results = self._execute_wave(
                    sentinel_tasks,
                    baseline,
                    effective_context,
                    safety_context,
                    counterfactual_plan=plan,
                    counterfactual_runner=counterfactual_runner or self.local_runner,
                    stage="COUNTERFACTUAL",
                )
                counterfactual_results = [
                    item for result in sentinel_results for item in result.counterfactual_results
                ]
                self.last_counterfactual_summary = self._summary(counterfactual_results)
                all_worker_results.extend(sentinel_results)
                self.last_worker_diagnostics.extend(self._diagnostics(sentinel_results))
                all_objections.extend(self._objections(sentinel_results))
            final = self._final_verified_run(
                baseline,
                initial,
                all_objections,
                self.last_counterfactual_summary,
            )
            final_planned = PlannedVerifiedRun(
                query_plan=baseline.query_plan.model_copy(deep=True),
                retrieval_diagnostics=baseline.retrieval_diagnostics.model_copy(deep=True),
                verified_run=final,
            )
            routed_run, case_capsule = self._route_if_needed(
                final_planned,
                effective_context,
                namespace="m4d",
            )
            findings = [
                *ledger.findings,
                *[finding for result in sentinel_results for finding in result.findings],
            ]
            metrics = OrchestraMetrics(
                active_agent_count=len({task.agent_id for task in tasks}),
                task_count=len(tasks),
                finding_count=len(findings),
                candidate_claim_count=len(claim_build.claims),
                material_objection_count=sum(
                    objection.materiality == "MATERIAL" for objection in all_objections
                ),
                counterfactual_count=len(counterfactual_results),
                worker_execution_count=len(all_worker_results),
            )
            if planned_verified_run.model_dump(mode="json") != baseline_before:
                raise RuntimeError("M4D orchestration mutated the PlannedVerifiedRun baseline")
            run = OrchestraRun(
                baseline_run=baseline,
                activation_profile=profile,
                risk_signals=signals,
                investigation_plan=InvestigationPlan(
                    activation_profile=profile,
                    required_agent_roles=roles,
                    task_ids=[task.task_id for task in tasks],
                    worker_execution_required=True,
                ),
                agent_tasks=tasks,
                findings=findings,
                candidate_claims=list(claim_build.claims),
                material_objections=sorted(all_objections, key=lambda item: item.objection_id),
                counterfactual_results=counterfactual_results,
                final_verified_run=final,
                routed_run=routed_run,
                case_capsule=case_capsule,
                orchestra_metrics=metrics,
                risk_assessment=assessment,
                runtime_diagnostics=build_runtime_diagnostics(
                    source_safety.report,
                    run_planned_call_count=run_planned_call_count,
                ),
            )
            self._append_success(run, request, assessment)
            return run
        except (OrchestraFailClosedError, OrchestraConfigurationError):
            raise
        except Exception as exc:
            return self._handle_worker_failure(
                baseline,
                effective_context,
                profile,
                assessment,
                source_safety,
                exc,
                tasks,
                request=request,
                run_planned_call_count=run_planned_call_count,
            )

    def _zero_worker_run(
        self,
        baseline: PlannedVerifiedRun,
        context: OrchestraContext,
        profile: ActivationProfile,
        assessment: RiskAssessment,
        source_safety: SourceSafetyContext,
        *,
        request: QueryInput | None,
        run_planned_call_count: int,
        candidate_claim_count: int = 0,
    ) -> OrchestraRun:
        """Return a zero-worker path without altering the baseline."""

        run = OrchestraRun(
            baseline_run=baseline,
            activation_profile=profile,
            risk_signals=assessment.risk_signals,
            investigation_plan=InvestigationPlan(
                activation_profile=profile,
                required_agent_roles=[],
                task_ids=[],
                worker_execution_required=False,
            ),
            final_verified_run=baseline.verified_run.model_copy(deep=True),
            orchestra_metrics=OrchestraMetrics(
                active_agent_count=0,
                task_count=0,
                finding_count=0,
                candidate_claim_count=candidate_claim_count,
                material_objection_count=0,
                counterfactual_count=0,
                worker_execution_count=0,
            ),
            risk_assessment=assessment,
            runtime_diagnostics=build_runtime_diagnostics(
                source_safety.report,
                run_planned_call_count=run_planned_call_count,
            ),
        )
        self._append_success(run, request, assessment)
        return run

    def _is_structural_fast_path(self, baseline: PlannedVerifiedRun) -> bool:
        """Recognise an event answer whose every cited unit is structural evidence."""

        if baseline.verified_run.result.decision is not Decision.ANSWER:
            return False
        refs = baseline.verified_run.verification.evidence_refs
        if not refs:
            return False
        return all(
            (unit := self.corpus.resolve(reference)) is not None
            and unit.structured
            and unit.kind == "table_row"
            for reference in refs
        )

    def _human_first_run(
        self,
        baseline: PlannedVerifiedRun,
        context: OrchestraContext,
        profile: ActivationProfile,
        assessment: RiskAssessment,
        source_safety: SourceSafetyContext,
        *,
        request: QueryInput | None,
        run_planned_call_count: int,
    ) -> OrchestraRun:
        """Route a baseline abstention and build its structured case capsule."""

        routed_run, case_capsule = self._route_if_needed(baseline, context, namespace="m4d")
        if routed_run is None or case_capsule is None:
            raise OrchestraConfigurationError("HUMAN_FIRST requires a successful M3 route")
        run = OrchestraRun(
            baseline_run=baseline,
            activation_profile=profile,
            risk_signals=assessment.risk_signals,
            investigation_plan=InvestigationPlan(
                activation_profile=profile,
                required_agent_roles=[],
                task_ids=[],
                worker_execution_required=False,
            ),
            final_verified_run=baseline.verified_run.model_copy(deep=True),
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
            risk_assessment=assessment,
            runtime_diagnostics=build_runtime_diagnostics(
                source_safety.report,
                run_planned_call_count=run_planned_call_count,
            ),
        )
        self._append_success(run, request, assessment)
        return run

    def _roles(
        self,
        profile: ActivationProfile,
        signals: tuple[RiskSignal, ...],
        context: OrchestraContext,
    ) -> list[str]:
        """Choose bounded roles from signals, with no case-ID dispatch."""

        if context.requested_agent_roles:
            roles = list(context.requested_agent_roles)
        else:
            values = {str(signal) for signal in signals}
            if profile is ActivationProfile.DUAL_CHECK:
                roles = (
                    ["PROCESS_TABLE_SCOUT", "SKEPTIC"]
                    if "TABLE_DEPENDENT" in values
                    else ["EVIDENCE_SCOUT", "SKEPTIC"]
                )
            else:
                roles = []
                if values & {
                    "SCOPE_SENSITIVE",
                    "JURISDICTION_SENSITIVE",
                    "SERVICE_MODEL_SENSITIVE",
                }:
                    roles.extend(["EVIDENCE_SCOUT", "SCOPE_SENTINEL"])
                elif "TABLE_DEPENDENT" in values:
                    roles.append("PROCESS_TABLE_SCOUT")
                else:
                    roles.append("EVIDENCE_SCOUT")
                if values & {"CONTRADICTORY_SOURCES", "LOW_RETRIEVAL_MARGIN"}:
                    roles.append("SKEPTIC")
                if "COUNTERFACTUAL_REQUIRED" in values:
                    roles.append("COUNTERFACTUAL_SENTINEL")
        if len(roles) != len(set(roles)):
            raise OrchestraConfigurationError("M4D worker roles must be unique")
        return roles

    def _execute_wave(
        self,
        tasks: list[AgentTask],
        baseline: PlannedVerifiedRun,
        context: OrchestraContext,
        safety: SourceSafetyContext,
        *,
        prior_findings: list[AgentFinding] | None = None,
        candidate_claims: list[AnswerClaim] | None = None,
        counterfactual_plan: CounterfactualPlan | None = None,
        counterfactual_runner: CounterfactualRunner | None = None,
        stage: str,
    ) -> list[WorkerResult]:
        """Bridge the synchronous runtime API to the bounded async executor."""

        del stage
        if not tasks:
            return []
        try:
            return asyncio.run(
                self.executor.execute_wave(
                    tasks,
                    baseline,
                    context,
                    self.corpus,
                    safety,
                    prior_findings=prior_findings,
                    candidate_claims=candidate_claims,
                    counterfactual_plan=counterfactual_plan,
                    counterfactual_runner=counterfactual_runner,
                )
            )
        except OrchestraWorkerExecutionError:
            raise

    def _handle_worker_failure(
        self,
        baseline: PlannedVerifiedRun,
        context: OrchestraContext,
        profile: ActivationProfile,
        assessment: RiskAssessment,
        source_safety: SourceSafetyContext,
        exc: Exception,
        tasks: list[AgentTask],
        *,
        request: QueryInput | None,
        run_planned_call_count: int,
    ) -> OrchestraRun:
        """Apply the exact ANSWER fail-closed or ABSTAIN safe-fallback rule."""

        failed_task_ids = [exc.task_id] if isinstance(exc, OrchestraWorkerExecutionError) else []
        cause_types = [
            exc.cause_type if isinstance(exc, OrchestraWorkerExecutionError) else type(exc).__name__
        ]
        stage = self._failure_stage(exc)
        baseline_result = baseline.verified_run.result
        if baseline_result.decision is Decision.ANSWER:
            self._append_failure(
                baseline,
                profile,
                stage,
                failed_task_ids,
                cause_types,
                fallback_action="FAIL_CLOSED",
            )
            raise OrchestraFailClosedError(
                stage=stage,
                activation_profile=profile.value,
                baseline_decision=baseline_result.decision.value,
                failed_task_ids=failed_task_ids,
                cause_types=cause_types,
            ) from None
        if baseline_result.decision is not Decision.ABSTAIN:
            raise OrchestraConfigurationError(
                "M4D worker failure has no safe baseline fallback for this decision"
            ) from exc

        try:
            routed_run, capsule = self._route_if_needed(baseline, context, namespace="m4d")
            if routed_run is None or capsule is None:
                raise ValueError("M4D abstain fallback did not produce a route and capsule")
        except Exception as route_exc:
            self._append_failure(
                baseline,
                profile,
                stage,
                failed_task_ids,
                [*cause_types, type(route_exc).__name__],
                fallback_action="FAIL_CLOSED",
            )
            raise OrchestraFailClosedError(
                stage="ABSTAIN_FALLBACK_ROUTE",
                activation_profile=profile.value,
                baseline_decision=baseline_result.decision.value,
                failed_task_ids=failed_task_ids,
                cause_types=[*cause_types, type(route_exc).__name__],
            ) from None

        incomplete = MaterialObjection(
            objection_id="objection:runtime:orchestration-incomplete",
            agent_id="ORCHESTRA-RUNTIME",
            target_claim_id="ORCHESTRA_FINAL_ANSWER",
            reason_code="ORCHESTRATION_INCOMPLETE",
            materiality="MATERIAL",
            evidence_refs=self._input_refs(baseline),
            status="OPEN",
            resolvable_by="HUMAN_REVIEW",
        )
        run = OrchestraRun(
            baseline_run=baseline,
            activation_profile=profile,
            risk_signals=assessment.risk_signals,
            investigation_plan=InvestigationPlan(
                activation_profile=profile,
                required_agent_roles=self._roles(profile, assessment.risk_signals, context),
                task_ids=[task.task_id for task in tasks],
                worker_execution_required=True,
            ),
            agent_tasks=tasks,
            findings=[],
            candidate_claims=[],
            material_objections=[incomplete],
            counterfactual_results=[],
            final_verified_run=baseline.verified_run.model_copy(deep=True),
            routed_run=routed_run,
            case_capsule=capsule,
            orchestra_metrics=OrchestraMetrics(
                active_agent_count=len({task.agent_id for task in tasks}),
                task_count=len(tasks),
                finding_count=0,
                candidate_claim_count=0,
                material_objection_count=1,
                counterfactual_count=0,
                worker_execution_count=0,
            ),
            risk_assessment=assessment,
            runtime_diagnostics=build_runtime_diagnostics(
                source_safety.report,
                failure_stage=stage,
                failed_task_ids=failed_task_ids,
                cause_types=cause_types,
                fallback_action="PRESERVE_ABSTAIN_AND_ROUTE",
                run_planned_call_count=run_planned_call_count,
            ),
        )
        self._append_failure(
            baseline,
            profile,
            stage,
            failed_task_ids,
            cause_types,
            fallback_action="PRESERVE_ABSTAIN_AND_ROUTE",
            route_returned=True,
        )
        return run

    def _final_verified_run(
        self,
        baseline: PlannedVerifiedRun,
        initial: VerifiedRun,
        objections: list[MaterialObjection],
        summary: CounterfactualSummary,
    ) -> VerifiedRun:
        """Apply the material-objection gate after optional local transitions."""

        open_scope_leaks = [
            item
            for item in objections
            if item.reason_code == "COUNTERFACTUAL_SCOPE_LEAK"
            and item.materiality == "MATERIAL"
            and item.status == "OPEN"
        ]
        if summary.scope_leak_count and open_scope_leaks:
            result_data = baseline.verified_run.result.model_dump(mode="python")
            route = self.legacy_route(
                baseline.verified_run.result.detected_context,
                [ReasonCode.SCOPE_MISMATCH],
            )
            result_data.update(
                decision=Decision.ABSTAIN,
                answer=None,
                clarifying_question=None,
                reason_codes=[ReasonCode.SCOPE_MISMATCH],
                route=route,
                answer_confidence=0.0,
                routing_confidence=route.routing_confidence,
            )
            result = PipelineResult.model_validate(result_data)
            report_data = baseline.verified_run.verification.model_dump(mode="python")
            report_data.update(
                status=VerificationStatus.INSUFFICIENT,
                reason_codes=[ReasonCode.SCOPE_MISMATCH],
                supported_claim_ids=[],
                unsupported_claim_ids=list(baseline.verified_run.verification.supported_claim_ids),
                missing_required_claim_ids=[],
                scope_mismatches=list(baseline.verified_run.verification.supported_claim_ids),
                evidence_refs=list(baseline.verified_run.verification.evidence_refs),
                explanation="An open material counterfactual scope objection blocks the answer.",
            )
            return VerifiedRun(
                result=result,
                verification=VerificationReport.model_validate(report_data),
            )
        if summary.variant_count and summary.failed_count == 0:
            return baseline.verified_run.model_copy(deep=True)
        return initial.model_copy(deep=True)

    def _route_if_needed(
        self,
        planned: PlannedVerifiedRun,
        context: OrchestraContext,
        *,
        namespace: str,
    ) -> tuple[RoutedRun | None, CaseCapsule | None]:
        if planned.verified_run.result.decision is not Decision.ABSTAIN:
            return None, None
        routing_context = context.routing_context or RoutingContext(
            need_type=planned.verified_run.result.detected_context.need_type,
            reason_codes=list(planned.verified_run.result.reason_codes),
            region=planned.verified_run.result.detected_context.region,
        )
        if routing_context.reason_codes != list(planned.verified_run.result.reason_codes):
            routing_context = routing_context.model_copy(
                update={"reason_codes": list(planned.verified_run.result.reason_codes)}
            )
        routed = self.route_planned(planned, routing_context, context.routing_profile)
        if routed.expert_route is None:
            raise OrchestraConfigurationError("M4D ABSTAIN route_planned returned no expert route")
        return routed, build_case_capsule(planned, routed, namespace=namespace)

    def _direct_assessment(
        self,
        profile: ActivationProfile,
        signals: tuple[RiskSignal, ...],
    ) -> RiskAssessment:
        return RiskAssessment(
            risk_signals=signals,
            signal_sources={
                str(signal): (self.runtime_policy.rule(str(signal)).source,) for signal in signals
            },
            selected_activation_profile=profile,
            profile_reason="direct orchestration context",
        )

    def _context(
        self,
        request: QueryInput,
        baseline: PlannedVerifiedRun,
        assessment: RiskAssessment,
    ) -> OrchestraContext:
        from riskon.orchestra.context_builder import build_orchestra_context

        return build_orchestra_context(
            request,
            baseline,
            assessment,
            default_routing_profile=self.default_routing_profile,
        )

    def _source_safety(self, report: SourceSafetyReport | None = None) -> SourceSafetyContext:
        if report is None:
            return SourceSafetyContext(
                policy=self.source_safety_policy,
                report=self.source_safety_policy.inspect(self.corpus),
            )
        return SourceSafetyContext(policy=self.source_safety_policy, report=report)

    def _validate_security(self) -> None:
        if self.network_enabled:
            raise OrchestraConfigurationError("M4D requires network_enabled = false")
        if self.external_api_enabled:
            raise OrchestraConfigurationError("M4D requires external_api_enabled = false")
        if self.recursive_orchestration_enabled:
            raise OrchestraConfigurationError("M4D requires recursive orchestration to be disabled")
        if self.counterfactual_routing_enabled:
            raise OrchestraConfigurationError("M4D requires counterfactual routing to be disabled")
        if self.agent_to_agent_citation_enabled:
            raise OrchestraConfigurationError(
                "M4D requires agent-to-agent citations to be disabled"
            )

    def _reset_run_state(self) -> None:
        """Clear per-run diagnostics before a new orchestration starts."""

        self.last_worker_diagnostics = []
        self.last_counterfactual_summary = CounterfactualSummary(
            variant_count=0,
            passed_count=0,
            failed_count=0,
            scope_leak_count=0,
            routing_execution_count=0,
        )

    def _check_task_budget(self, task_count: int) -> None:
        if task_count > self.runtime_policy.execution_budget.maximum_total_worker_tasks:
            raise OrchestraExecutionBudgetExceededError("M4D maximum worker tasks exceeded")

    @staticmethod
    def _input_refs(baseline: PlannedVerifiedRun) -> list[str]:
        return sorted(
            {
                *(item.source_ref for item in baseline.verified_run.result.evidence),
                *(item.source_ref for item in baseline.verified_run.result.retrieved_sections),
                *baseline.verified_run.verification.evidence_refs,
            }
        )

    @staticmethod
    def _findings(results: list[WorkerResult]) -> list[AgentFinding]:
        return [
            finding
            for result in results
            for finding in sorted(result.findings, key=lambda item: item.finding_id)
        ]

    @staticmethod
    def _objections(results: list[WorkerResult]) -> list[MaterialObjection]:
        return [objection for result in results for objection in result.material_objections]

    @staticmethod
    def _diagnostics(results: list[WorkerResult]) -> list[WorkerDiagnostic]:
        return [diagnostic for result in results for diagnostic in result.diagnostics]

    @staticmethod
    def _summary(results: list[CounterfactualExecutionResult]) -> CounterfactualSummary:
        passed = sum(item.passed for item in results)
        return CounterfactualSummary(
            variant_count=len(results),
            passed_count=passed,
            failed_count=len(results) - passed,
            scope_leak_count=sum(not item.passed for item in results),
            routing_execution_count=0,
        )

    @staticmethod
    def _failure_stage(exc: Exception) -> str:
        if isinstance(exc, OrchestraWorkerExecutionError):
            if exc.agent_role == "COUNTERFACTUAL_SENTINEL":
                return "COUNTERFACTUAL"
            return "WORKER_EXECUTION"
        if isinstance(exc, OrchestraExecutionBudgetExceededError):
            return "EXECUTION_BUDGET"
        return "ORCHESTRATION"

    def _append_success(
        self,
        run: OrchestraRun,
        request: QueryInput | None,
        assessment: RiskAssessment,
    ) -> None:
        if self.audit_sink is not None:
            self.audit_sink.append_success(run, request=request, assessment=assessment)

    def _append_failure(
        self,
        baseline: PlannedVerifiedRun,
        profile: ActivationProfile,
        stage: str,
        failed_task_ids: list[str],
        cause_types: list[str],
        *,
        fallback_action: str,
        route_returned: bool = False,
    ) -> None:
        if self.audit_sink is None:
            return
        trace_id = baseline.verified_run.result.trace_id
        self.audit_sink.append_failure(
            trace_id=trace_id,
            baseline_trace_id=trace_id,
            baseline_decision=baseline.verified_run.result.decision.value,
            activation_profile=profile.value,
            failed_stage=stage,
            failed_task_ids=failed_task_ids,
            cause_types=cause_types,
            fallback_action=fallback_action,
            answer_returned=False,
            route_returned=route_returned,
        )
