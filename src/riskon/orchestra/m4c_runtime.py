"""M4C runtime: bounded workers plus counterfactual transition adjudication."""

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
    ReasonCode,
    Route,
    RoutedRun,
    RoutingContext,
    VerificationReport,
    VerificationStatus,
    VerifiedRun,
)
from riskon.orchestra.activation import validate_m4c_activation
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
    RunPlanned,
)
from riskon.orchestra.errors import OrchestraWorkerExecutionError
from riskon.orchestra.executor import BoundedWorkerExecutor
from riskon.orchestra.ledger import EvidenceLedger
from riskon.orchestra.models import (
    AgentFinding,
    AgentTask,
    InvestigationPlan,
    MaterialObjection,
    OrchestraContext,
    OrchestraMetrics,
    OrchestraRun,
    RiskSignal,
    WorkerDiagnostic,
    WorkerResult,
)
from riskon.orchestra.policy import ActivationPolicy, WorkerSelectionPolicy
from riskon.orchestra.source_safety import LocalCorpus, SourceSafetyContext, SourceSafetyPolicy
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


class OrchestraAuditSink(Protocol):
    """Small audit boundary used by the M4C runtime."""

    def append(self, run: OrchestraRun) -> None:
        """Append one successful orchestration run."""


RoutePlanned = Callable[[PlannedVerifiedRun, RoutingContext, str], RoutedRun]
LegacyRoute = Callable[[DetectedContext, list[ReasonCode]], Route]


class M4COrchestrator:
    """Execute discovery, one initial M1 gate, and bounded transitions."""

    def __init__(
        self,
        activation_policy: ActivationPolicy,
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
        implemented_roles: list[str],
        audit_sink: OrchestraAuditSink | None = None,
        network_enabled: bool = False,
        counterfactual_routing_enabled: bool = False,
        recursive_orchestration_enabled: bool = False,
        agent_to_agent_citation_enabled: bool = False,
    ) -> None:
        self.activation_policy = activation_policy
        self.worker_policy = worker_policy
        self.selector = WorkerSelector(worker_policy, catalog)
        self.catalog = catalog
        self.corpus = corpus
        self.source_safety_policy = source_safety_policy
        self.m1_adjudicator = ExistingM1Adjudicator(corpus, m1_verifier)
        self.route_planned = route_planned
        self.legacy_route = legacy_route
        self.counterfactual_policy = counterfactual_policy
        self.planner = CounterfactualPlanner(counterfactual_policy)
        self.local_runner = LocalPlannedPipelineCounterfactualRunner(run_planned)
        self.implemented_roles = frozenset(implemented_roles)
        self.audit_sink = audit_sink
        self.network_enabled = network_enabled
        self.counterfactual_routing_enabled = counterfactual_routing_enabled
        self.recursive_orchestration_enabled = recursive_orchestration_enabled
        self.agent_to_agent_citation_enabled = agent_to_agent_citation_enabled
        self.executor = BoundedWorkerExecutor(
            {
                "EVIDENCE_SCOUT": EvidenceScout(),
                "SCOPE_SENTINEL": ScopeSentinel(),
                "PROCESS_TABLE_SCOUT": ProcessTableScout(),
                "SKEPTIC": Skeptic(),
                "COUNTERFACTUAL_SENTINEL": CounterfactualSentinel(),
            },
            worker_policy.maximum_parallel_discovery_workers,
        )
        self.last_worker_diagnostics: list[WorkerDiagnostic] = []
        self.last_counterfactual_summary = CounterfactualSummary(
            variant_count=0,
            passed_count=0,
            failed_count=0,
            scope_leak_count=0,
            routing_execution_count=0,
        )

    def orchestrate_planned(
        self,
        planned_verified_run: PlannedVerifiedRun,
        orchestration_context: OrchestraContext,
        orchestration_profile: str,
        *,
        counterfactual_plan: CounterfactualPlan | None = None,
        counterfactual_runner: CounterfactualRunner | None = None,
        requested_variants: list[CounterfactualVariant] | None = None,
    ) -> OrchestraRun:
        """Run the exact M4C sequence over a frozen planned baseline."""

        self._validate_security()
        self.last_worker_diagnostics = []
        self.last_counterfactual_summary = CounterfactualSummary(
            variant_count=0,
            passed_count=0,
            failed_count=0,
            scope_leak_count=0,
            routing_execution_count=0,
        )
        before = planned_verified_run.model_dump(mode="json")
        baseline = PlannedVerifiedRun.model_validate(before)
        baseline_result = baseline.verified_run.result
        signals = self.activation_policy.validate_risk_signals(orchestration_context.risk_signals)
        profile = validate_m4c_activation(
            self.activation_policy,
            orchestration_profile,
            baseline_result.decision,
            orchestration_context,
        )
        effective_context = orchestration_context.model_copy(
            update={
                "structured_context": self.planner.context_for(
                    baseline, orchestration_context.structured_context
                )
            }
        )
        roles = self._roles(effective_context, signals)
        initial_roles = [role for role in roles if role != "COUNTERFACTUAL_SENTINEL"]
        input_refs = sorted(
            {
                *(item.source_ref for item in baseline_result.evidence),
                *(item.source_ref for item in baseline_result.retrieved_sections),
                *baseline.verified_run.verification.evidence_refs,
            }
        )
        tasks = self.selector.build_tasks(
            baseline.query_plan.plan_id,
            signals,
            input_refs=input_refs,
            requested_roles=initial_roles,
            allow_counterfactual=True,
        )
        safety = SourceSafetyContext(
            policy=self.source_safety_policy,
            report=self.source_safety_policy.inspect(self.corpus),
        )
        discovery_tasks = [task for task in tasks if task.execution_wave.value == "DISCOVERY"]
        challenge_tasks = [task for task in tasks if task.execution_wave.value == "CHALLENGE"]
        discovery_results = self._execute_wave(
            discovery_tasks,
            baseline,
            effective_context,
            safety,
        )
        ledger = EvidenceLedger(set(self.corpus.provenance.local_refs()))
        discovery_findings = [
            finding
            for result in discovery_results
            for finding in sorted(result.findings, key=lambda item: item.finding_id)
        ]
        ledger.append_many(discovery_findings)
        preliminary_claims = (
            DeterministicClaimBuilder(self.corpus, safety).build(ledger.findings).claims
        )
        challenge_results = self._execute_wave(
            challenge_tasks,
            baseline,
            effective_context,
            safety,
            prior_findings=ledger.findings,
            candidate_claims=list(preliminary_claims),
        )
        self.last_worker_diagnostics = [
            diagnostic
            for result in [*discovery_results, *challenge_results]
            for diagnostic in result.diagnostics
        ]
        challenge_findings = [
            finding
            for result in challenge_results
            for finding in sorted(result.findings, key=lambda item: item.finding_id)
        ]
        ledger.append_many(challenge_findings)
        all_worker_results = [*discovery_results, *challenge_results]
        all_objections = [
            objection for result in all_worker_results for objection in result.material_objections
        ]
        claim_build = DeterministicClaimBuilder(self.corpus, safety).build(ledger.findings)
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
            baseline_result.decision is Decision.ANSWER
            and initial.result.decision is Decision.ANSWER
        ):
            plan = counterfactual_plan or self.planner.plan(
                baseline,
                effective_context.structured_context,
                requested_variants=requested_variants,
            )
            if plan.baseline_plan_id != baseline.query_plan.plan_id:
                raise ValueError("Counterfactual plan baseline lineage mismatch")
            sentinel_task = self.selector.build_tasks(
                baseline.query_plan.plan_id,
                signals,
                input_refs=input_refs,
                requested_roles=["COUNTERFACTUAL_SENTINEL"],
                allow_counterfactual=True,
            )
            sentinel_results = self._execute_wave(
                sentinel_task,
                baseline,
                effective_context,
                safety,
                counterfactual_plan=plan,
                counterfactual_runner=counterfactual_runner or self.local_runner,
            )
            if sentinel_results:
                counterfactual_results = list(sentinel_results[0].counterfactual_results)
                all_objections.extend(sentinel_results[0].material_objections)
                self.last_worker_diagnostics.extend(sentinel_results[0].diagnostics)
                self.last_counterfactual_summary = self._summary(counterfactual_results)
            tasks.extend(sentinel_task)

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
        routed_run: RoutedRun | None = None
        case_capsule = None
        if final.result.decision is Decision.ABSTAIN:
            routing_context = effective_context.routing_context or RoutingContext(
                need_type=final.result.detected_context.need_type,
                reason_codes=list(final.result.reason_codes),
                region=(
                    None
                    if ReasonCode.SCOPE_MISMATCH in final.result.reason_codes
                    else final.result.detected_context.region
                ),
            )
            if routing_context.reason_codes != list(final.result.reason_codes):
                routing_context = routing_context.model_copy(
                    update={"reason_codes": list(final.result.reason_codes)}
                )
            routed_run = self.route_planned(
                final_planned,
                routing_context,
                effective_context.routing_profile,
            )
            if routed_run.expert_route is None:
                raise ValueError("M4C final ABSTAIN route_planned returned no expert route")
            case_capsule = build_case_capsule(final_planned, routed_run, namespace="m4c")

        sentinel_findings = [finding for result in sentinel_results for finding in result.findings]
        findings = [*ledger.findings, *sentinel_findings]
        all_results = [*all_worker_results, *sentinel_results]
        metrics = OrchestraMetrics(
            active_agent_count=len({task.agent_id for task in tasks}),
            task_count=len(tasks),
            finding_count=len(findings),
            candidate_claim_count=len(claim_build.claims),
            material_objection_count=sum(
                objection.materiality == "MATERIAL" for objection in all_objections
            ),
            counterfactual_count=len(counterfactual_results),
            worker_execution_count=len(all_results),
        )
        if planned_verified_run.model_dump(mode="json") != before:
            raise RuntimeError("M4C orchestration mutated the PlannedVerifiedRun baseline")
        run = OrchestraRun(
            baseline_run=baseline,
            activation_profile=profile,
            risk_signals=signals,
            investigation_plan=InvestigationPlan(
                activation_profile=profile,
                required_agent_roles=roles if sentinel_results else initial_roles,
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
        )
        if self.audit_sink is not None:
            self.audit_sink.append(run)
        return run

    def _roles(
        self,
        context: OrchestraContext,
        signals: tuple[RiskSignal, ...],
    ) -> list[str]:
        roles = list(context.requested_agent_roles)
        if not roles:
            roles = self.selector.select_roles(signals)
            if "COUNTERFACTUAL_REQUIRED" in {str(signal) for signal in signals}:
                if "COUNTERFACTUAL_SENTINEL" not in roles:
                    roles.append("COUNTERFACTUAL_SENTINEL")
        if len(roles) != len(set(roles)):
            raise ValueError("M4C worker roles must be unique")
        if any(role not in self.implemented_roles for role in roles):
            raise ValueError("M4C requested role is not implemented")
        if "COUNTERFACTUAL_SENTINEL" not in roles:
            raise ValueError("M4C worker graph requires COUNTERFACTUAL_SENTINEL")
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
    ) -> list[WorkerResult]:
        """Bridge the synchronous orchestration API to bounded async workers."""

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

    def _final_verified_run(
        self,
        baseline: PlannedVerifiedRun,
        initial: VerifiedRun,
        objections: list[MaterialObjection],
        summary: CounterfactualSummary,
    ) -> VerifiedRun:
        """Apply the material-objection gate while preserving safe baselines."""

        open_scope_leaks = [
            item
            for item in objections
            if item.reason_code == "COUNTERFACTUAL_SCOPE_LEAK"
            and item.materiality == "MATERIAL"
            and item.status == "OPEN"
        ]
        if summary.scope_leak_count and open_scope_leaks:
            result_data = baseline.verified_run.result.model_dump(mode="python")
            legacy_route = self.legacy_route(
                baseline.verified_run.result.detected_context,
                [ReasonCode.SCOPE_MISMATCH],
            )
            result_data.update(
                decision=Decision.ABSTAIN,
                answer=None,
                clarifying_question=None,
                reason_codes=[ReasonCode.SCOPE_MISMATCH],
                route=legacy_route,
                answer_confidence=0.0,
                routing_confidence=legacy_route.routing_confidence,
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

    def _validate_security(self) -> None:
        if self.network_enabled:
            raise ValueError("M4C requires network_enabled = false")
        if self.counterfactual_routing_enabled:
            raise ValueError("M4C requires counterfactual_routing_enabled = false")
        if self.recursive_orchestration_enabled:
            raise ValueError("M4C requires recursive_orchestration_enabled = false")
        if self.agent_to_agent_citation_enabled:
            raise ValueError("M4C requires agent_to_agent_citation_enabled = false")
