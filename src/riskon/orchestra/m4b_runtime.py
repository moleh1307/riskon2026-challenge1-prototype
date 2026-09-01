"""M4B bounded deterministic worker orchestration runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from riskon.models import AnswerClaim, Decision, PlannedVerifiedRun, RoutedRun, RoutingContext
from riskon.orchestra.activation import M4B_SUPPORTED_PROFILES, validate_m4b_activation
from riskon.orchestra.adjudication import (
    ExistingM1Adjudicator,
    MaterialObjectionGate,
    adjudicate,
)
from riskon.orchestra.case_capsule import build_case_capsule
from riskon.orchestra.claim_builder import DeterministicClaimBuilder
from riskon.orchestra.errors import (
    OrchestraWorkerExecutionError,
    OrchestraWorkersNotImplementedError,
)
from riskon.orchestra.executor import BoundedWorkerExecutor
from riskon.orchestra.ledger import EvidenceLedger
from riskon.orchestra.models import (
    AgentFinding,
    AgentTask,
    InvestigationPlan,
    OrchestraContext,
    OrchestraMetrics,
    OrchestraRun,
    WorkerDiagnostic,
    WorkerResult,
)
from riskon.orchestra.policy import ActivationPolicy, WorkerSelectionPolicy
from riskon.orchestra.source_safety import LocalCorpus, SourceSafetyContext, SourceSafetyPolicy
from riskon.orchestra.tasks import AgentCatalog
from riskon.orchestra.worker_selection import WorkerSelector
from riskon.orchestra.workers import EvidenceScout, ProcessTableScout, ScopeSentinel, Skeptic
from riskon.verification import VerificationEngine


class OrchestraAuditSink(Protocol):
    """Small audit boundary used by M4B without importing audit code."""

    def append(self, run: OrchestraRun) -> None:
        """Append one successful orchestration run."""


RoutePlanned = Callable[[PlannedVerifiedRun, RoutingContext, str], RoutedRun]


class M4BOrchestrator:
    """Execute one bounded deterministic discovery/challenge orchestra."""

    def __init__(
        self,
        policy: ActivationPolicy,
        worker_policy: WorkerSelectionPolicy,
        catalog: AgentCatalog,
        corpus: LocalCorpus,
        source_safety_policy: SourceSafetyPolicy,
        m1_verifier: VerificationEngine,
        route_planned: RoutePlanned,
        *,
        implemented_roles: list[str],
        audit_sink: OrchestraAuditSink | None = None,
        network_enabled: bool = False,
        agent_to_agent_citation_enabled: bool = False,
        recursive_delegation_enabled: bool = False,
    ) -> None:
        self.policy = policy
        self.worker_policy = worker_policy
        self.selector = WorkerSelector(worker_policy, catalog)
        self.corpus = corpus
        self.source_safety_policy = source_safety_policy
        self.m1_adjudicator = ExistingM1Adjudicator(corpus, m1_verifier)
        self.route_planned = route_planned
        self.implemented_roles = frozenset(implemented_roles)
        self.audit_sink = audit_sink
        self.network_enabled = network_enabled
        self.agent_to_agent_citation_enabled = agent_to_agent_citation_enabled
        self.recursive_delegation_enabled = recursive_delegation_enabled
        self.executor = BoundedWorkerExecutor(
            {
                "EVIDENCE_SCOUT": EvidenceScout(),
                "SCOPE_SENTINEL": ScopeSentinel(),
                "PROCESS_TABLE_SCOUT": ProcessTableScout(),
                "SKEPTIC": Skeptic(),
            },
            worker_policy.maximum_parallel_discovery_workers,
        )
        self.last_worker_diagnostics: list[WorkerDiagnostic] = []

    def orchestrate_planned(
        self,
        planned_verified_run: PlannedVerifiedRun,
        orchestration_context: OrchestraContext,
        orchestration_profile: str,
    ) -> OrchestraRun:
        """Run discovery, fan-in, challenge, adjudication, and optional routing."""

        if self.network_enabled:
            raise ValueError("M4B requires network_enabled = false")
        if self.agent_to_agent_citation_enabled:
            raise ValueError("M4B requires agent_to_agent_citation_enabled = false")
        if self.recursive_delegation_enabled:
            raise ValueError("M4B requires recursive_delegation_enabled = false")

        self.last_worker_diagnostics = []
        before = planned_verified_run.model_dump(mode="json")
        baseline_result = planned_verified_run.verified_run.result
        validated_signals = self.policy.validate_risk_signals(orchestration_context.risk_signals)
        profile = validate_m4b_activation(
            self.policy,
            orchestration_profile,
            baseline_result.decision,
            orchestration_context,
        )
        if "COUNTERFACTUAL_REQUIRED" in {str(signal) for signal in validated_signals}:
            required_roles = ["COUNTERFACTUAL_SENTINEL"]
            raise OrchestraWorkersNotImplementedError(
                profile.value,
                required_roles,
                "Orchestration requires COUNTERFACTUAL_SENTINEL, which is reserved for M4C.",
            )
        required_roles = self.selector.select_roles(validated_signals)
        if profile not in M4B_SUPPORTED_PROFILES or any(
            role not in self.implemented_roles for role in required_roles
        ):
            raise OrchestraWorkersNotImplementedError(profile.value, required_roles)

        baseline_run = PlannedVerifiedRun.model_validate(before)
        input_refs = sorted(
            {
                *(item.source_ref for item in baseline_result.evidence),
                *(item.source_ref for item in baseline_result.retrieved_sections),
                *planned_verified_run.verified_run.verification.evidence_refs,
            }
        )
        tasks = self.selector.build_tasks(
            planned_verified_run.query_plan.plan_id,
            validated_signals,
            input_refs=input_refs,
        )
        safety_context = SourceSafetyContext(
            policy=self.source_safety_policy,
            report=self.source_safety_policy.inspect(self.corpus),
        )
        discovery_tasks = [task for task in tasks if task.execution_wave.value == "DISCOVERY"]
        challenge_tasks = [task for task in tasks if task.execution_wave.value == "CHALLENGE"]
        discovery_results = self._execute_wave(
            discovery_tasks,
            baseline_run,
            orchestration_context,
            safety_context,
        )
        discovery_findings = [
            finding
            for result in discovery_results
            for finding in sorted(result.findings, key=lambda item: item.finding_id)
        ]
        ledger = EvidenceLedger(set(self.corpus.provenance.local_refs()))
        ledger.append_many(discovery_findings)
        discovery_objections = [
            objection for result in discovery_results for objection in result.material_objections
        ]
        preliminary_claims = (
            DeterministicClaimBuilder(self.corpus, safety_context).build(ledger.findings).claims
        )
        challenge_results = self._execute_wave(
            challenge_tasks,
            baseline_run,
            orchestration_context,
            safety_context,
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
        all_objections = discovery_objections + [
            objection for result in challenge_results for objection in result.material_objections
        ]
        claim_build = DeterministicClaimBuilder(self.corpus, safety_context).build(ledger.findings)
        if claim_build.claims:
            final_evidence_refs = sorted(
                {reference for claim in claim_build.claims for reference in claim.evidence_refs}
            )
        else:
            final_evidence_refs = ledger.evidence_refs()
        objection_decision = MaterialObjectionGate().evaluate(all_objections)
        final_verified_run = adjudicate(
            baseline_run,
            claim_build,
            final_evidence_refs,
            self.corpus,
            self.m1_adjudicator,
            objection_decision,
        )

        final_planned = PlannedVerifiedRun(
            query_plan=baseline_run.query_plan.model_copy(deep=True),
            retrieval_diagnostics=baseline_run.retrieval_diagnostics.model_copy(deep=True),
            verified_run=final_verified_run,
        )
        routed_run: RoutedRun | None = None
        case_capsule = None
        if final_verified_run.result.decision is Decision.ABSTAIN:
            routing_context = orchestration_context.routing_context
            if routing_context is None:
                routing_context = RoutingContext(
                    need_type=final_verified_run.result.detected_context.need_type,
                    reason_codes=list(final_verified_run.result.reason_codes),
                    region=final_verified_run.result.detected_context.region,
                )
            elif routing_context.reason_codes != list(final_verified_run.result.reason_codes):
                routing_context = routing_context.model_copy(
                    update={"reason_codes": list(final_verified_run.result.reason_codes)}
                )
            routed_run = self.route_planned(
                final_planned,
                routing_context,
                orchestration_context.routing_profile,
            )
            if routed_run.expert_route is None:
                raise ValueError("M4B final ABSTAIN route_planned returned no expert route")
            case_capsule = build_case_capsule(final_planned, routed_run, namespace="m4b")

        all_results = [*discovery_results, *challenge_results]
        metrics = OrchestraMetrics(
            active_agent_count=len({task.agent_id for task in tasks}),
            task_count=len(tasks),
            finding_count=len(ledger.findings),
            candidate_claim_count=len(claim_build.claims),
            material_objection_count=sum(
                objection.materiality == "MATERIAL" for objection in all_objections
            ),
            counterfactual_count=0,
            worker_execution_count=len(all_results),
        )
        after = planned_verified_run.model_dump(mode="json")
        if after != before:
            raise RuntimeError("M4B orchestration mutated the PlannedVerifiedRun baseline")
        run = OrchestraRun(
            baseline_run=baseline_run,
            activation_profile=profile,
            risk_signals=validated_signals,
            investigation_plan=InvestigationPlan(
                activation_profile=profile,
                required_agent_roles=required_roles,
                task_ids=[task.task_id for task in tasks],
                worker_execution_required=True,
            ),
            agent_tasks=tasks,
            findings=ledger.findings,
            candidate_claims=list(claim_build.claims),
            material_objections=sorted(all_objections, key=lambda item: item.objection_id),
            counterfactual_results=[],
            final_verified_run=final_verified_run,
            routed_run=routed_run,
            case_capsule=case_capsule,
            orchestra_metrics=metrics,
        )
        if self.audit_sink is not None:
            self.audit_sink.append(run)
        return run

    def _execute_wave(
        self,
        tasks: list[AgentTask],
        baseline_run: PlannedVerifiedRun,
        orchestra_context: OrchestraContext,
        source_safety: SourceSafetyContext,
        *,
        prior_findings: list[AgentFinding] | None = None,
        candidate_claims: list[AnswerClaim] | None = None,
    ) -> list[WorkerResult]:
        """Bridge the synchronous public API to the bounded async executor."""

        try:
            return asyncio.run(
                self.executor.execute_wave(
                    tasks,
                    baseline_run,
                    orchestra_context,
                    self.corpus,
                    source_safety,
                    prior_findings=prior_findings,
                    candidate_claims=candidate_claims,
                )
            )
        except OrchestraWorkerExecutionError:
            raise
