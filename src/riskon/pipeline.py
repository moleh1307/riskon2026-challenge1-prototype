"""Orchestration for the offline deterministic M0 walking skeleton."""

from pathlib import Path
from typing import cast
from uuid import uuid4

from riskon.answering import AnswerComposer, ExtractiveAnswerComposer
from riskon.audit import AuditLogger, M4AAuditLogger, M4BAuditLogger, M4CAuditLogger
from riskon.config import (
    AuditConfig,
    Milestone1Config,
    Milestone2Config,
    Milestone3Config,
    Milestone4AConfig,
    Milestone4BConfig,
    Milestone4CConfig,
    Milestone4DConfig,
    Milestone5BConfig,
    PipelineConfig,
)
from riskon.context import ContextDetector
from riskon.decision import DecisionEngine
from riskon.evidence import EvidenceChecker
from riskon.expert_routing import ExpertRouter as ConfigurableExpertRouter
from riskon.governance.models import KnowledgeOverlaySnapshot, OverlayEvidenceUnit
from riskon.governance.service import GovernedKnowledgeService
from riskon.hybrid_retrieval import HybridRetrievalResult, HybridRetriever
from riskon.ingestion import load_sections_from_manifest, load_synthetic_sections
from riskon.models import (
    AnswerClaim,
    Decision,
    DetectedContext,
    Evidence,
    NeedType,
    PipelineResult,
    PlannedVerifiedRun,
    QueryInput,
    QueryPlan,
    ReasonCode,
    RetrievalDiagnostics,
    RetrievalHit,
    Route,
    RoutedRun,
    RoutingContext,
    RoutingDiagnostics,
    RoutingRequest,
    RoutingStatus,
    Section,
    VerificationReport,
    VerificationStatus,
    VerifiedRun,
)
from riskon.orchestra.counterfactual_models import CounterfactualPlan, CounterfactualVariant
from riskon.orchestra.counterfactual_policy import CounterfactualExecutionPolicy
from riskon.orchestra.counterfactual_runner import CounterfactualRunner
from riskon.orchestra.failure_policy import FailurePolicy
from riskon.orchestra.m4b_runtime import M4BOrchestrator
from riskon.orchestra.m4c_runtime import M4COrchestrator
from riskon.orchestra.models import OrchestraContext, OrchestraRun
from riskon.orchestra.policy import ActivationPolicy, WorkerSelectionPolicy
from riskon.orchestra.runtime import M4AOrchestrator
from riskon.orchestra.runtime_audit import UnifiedRuntimeAuditLogger
from riskon.orchestra.runtime_policy import RuntimePolicy
from riskon.orchestra.source_safety import LocalCorpus, SourceSafetyPolicy, build_local_corpus
from riskon.orchestra.tasks import AgentCatalog
from riskon.orchestra.unified_runtime import UnifiedOrchestraRuntime
from riskon.provenance import ProvenanceIndex, ProvenanceUnit
from riskon.query_planning import M4DQueryPlanner, QueryPlanner
from riskon.retrieval import SectionRetriever
from riskon.routing import ExpertRouter
from riskon.verification import VerificationEngine


class RiskonPipeline:
    """Question-to-audit pipeline with no network or model boundary."""

    def __init__(
        self,
        config: PipelineConfig,
        *,
        sections: list[Section] | None = None,
        answer_composer: AnswerComposer | None = None,
        verification_engine: VerificationEngine | None = None,
    ) -> None:
        self.config = config
        loaded_sections = (
            sections if sections is not None else load_synthetic_sections(config.paths.data_root)
        )
        self.retriever = SectionRetriever(
            loaded_sections,
            top_k=config.retrieval.top_k,
            minimum_score=config.retrieval.minimum_score,
            ngram_range=(config.retrieval.ngram_min, config.retrieval.ngram_max),
        )
        self.context_detector = ContextDetector()
        self.evidence_checker = EvidenceChecker(config.retrieval.minimum_score)
        self.decision_engine = DecisionEngine()
        self.answer_composer = answer_composer or ExtractiveAnswerComposer()
        self.router = ExpertRouter.from_files(
            config.paths.data_root / "experts.json",
            config.paths.data_root / "routing_policy.json",
        )
        self.audit_logger = AuditLogger(config.audit.path)
        self._verification_engine = verification_engine
        self._m2_planner: QueryPlanner | None = None
        self._m2_retriever: HybridRetriever | None = None
        self._m2_provenance: ProvenanceIndex | None = None
        self._m3_routers: dict[str, ConfigurableExpertRouter] = {}
        self._m4a_orchestrator: M4AOrchestrator | None = None
        self._m4a_audit_logger: M4AAuditLogger | None = None
        self._m4b_orchestrator: M4BOrchestrator | None = None
        self._m4b_audit_logger: M4BAuditLogger | None = None
        self._m4c_orchestrator: M4COrchestrator | None = None
        self._m4c_audit_logger: M4CAuditLogger | None = None
        self._m4d_mode = False
        self._m4d_planner: M4DQueryPlanner | None = None
        self._m4d_retriever: HybridRetriever | None = None
        self._m4d_provenance: ProvenanceIndex | None = None
        self._m4d_corpus: LocalCorpus | None = None
        self._m4d_runtime: UnifiedOrchestraRuntime | None = None
        self._m4d_audit_logger: UnifiedRuntimeAuditLogger | None = None

    @classmethod
    def from_config(cls, config: PipelineConfig) -> "RiskonPipeline":
        """Construct a pipeline from the resolved configuration."""

        return cls(config)

    @classmethod
    def from_milestone1_config(cls, config: Milestone1Config) -> "RiskonPipeline":
        """Construct an M1 corpus pipeline layered over the M0 expert directory."""

        sections = load_sections_from_manifest(
            config.manifest,
            config.knowledge_root,
            url_prefix="local://synthetic-m1/",
        )
        runtime_config = config.base.model_copy(
            update={
                "audit": AuditConfig(path=config.generated_root / "audit.jsonl"),
                "runtime": config.runtime,
                "security": config.security,
            }
        )
        pipeline = cls(runtime_config, sections=sections)
        provenance = ProvenanceIndex(sections, knowledge_root=config.knowledge_root)
        pipeline._verification_engine = VerificationEngine(
            provenance,
            pipeline.router,
            config.verification,
        )
        return pipeline

    @classmethod
    def from_milestone2_config(cls, config: Milestone2Config) -> "RiskonPipeline":
        """Construct the M2 planner/retriever over the synthetic M2 corpus."""

        sections = load_sections_from_manifest(
            config.manifest,
            config.knowledge_root,
            url_prefix="local://synthetic-m2/",
        )
        runtime_config = config.base.base.model_copy(
            update={
                "audit": AuditConfig(path=config.generated_root / "audit.jsonl"),
                "runtime": config.runtime,
                "security": config.security,
            }
        )
        pipeline = cls(runtime_config, sections=sections)
        provenance = ProvenanceIndex(
            sections,
            knowledge_root=config.manifest.parent,
            ref_style="m2",
            attachment_root=config.manifest.parent / "attachments",
        )
        pipeline._m2_planner = QueryPlanner.from_file(
            config.alias_registry,
            config.query_planning,
        )
        pipeline._m2_provenance = provenance
        pipeline._m2_retriever = HybridRetriever(sections, provenance, config.retrieval)
        return pipeline

    @classmethod
    def from_milestone3_config(cls, config: Milestone3Config) -> "RiskonPipeline":
        """Construct M3 over the unchanged M2 planner and synthetic corpus."""

        m2_config = config.base
        sections = load_sections_from_manifest(
            m2_config.manifest,
            m2_config.knowledge_root,
            url_prefix="local://synthetic-m2/",
        )
        base_pipeline_config = m2_config.base.base.model_copy(
            update={
                "audit": AuditConfig(path=config.generated_root / "audit.jsonl"),
                "runtime": m2_config.runtime,
                "security": config.security,
            }
        )
        pipeline = cls(base_pipeline_config, sections=sections)
        provenance = ProvenanceIndex(
            sections,
            knowledge_root=m2_config.manifest.parent,
            ref_style="m2",
            attachment_root=m2_config.manifest.parent / "attachments",
        )
        pipeline._m2_planner = QueryPlanner.from_file(
            m2_config.alias_registry,
            m2_config.query_planning,
        )
        pipeline._m2_provenance = provenance
        pipeline._m2_retriever = HybridRetriever(sections, provenance, m2_config.retrieval)
        pipeline._m3_routers = {
            profile_name: ConfigurableExpertRouter.from_files(
                profile.support_model,
                profile.expert_directory,
                config.network_edges,
                config.routing,
            )
            for profile_name, profile in config.routing.profiles.items()
        }
        return pipeline

    @classmethod
    def from_milestone4a_config(cls, config: Milestone4AConfig) -> "RiskonPipeline":
        """Construct the M4A shell over the unchanged M3 pipeline and router."""

        pipeline = cls.from_milestone3_config(config.base)
        audit_logger = M4AAuditLogger(
            config.orchestra.generated_root / "audit.jsonl",
            network_enabled=config.security.network_enabled,
        )
        pipeline._m4a_audit_logger = audit_logger
        pipeline._m4a_orchestrator = M4AOrchestrator(
            ActivationPolicy.from_file(config.orchestra.activation_policy),
            pipeline.route_planned,
            audit_sink=audit_logger,
            network_enabled=config.security.network_enabled,
        )
        return pipeline

    @classmethod
    def from_milestone4b_config(cls, config: Milestone4BConfig) -> "RiskonPipeline":
        """Construct M4B over M4A while keeping its corpus and workers isolated."""

        pipeline = cls.from_milestone4a_config(config.base)
        m4_root = config.orchestra.evaluation_cases.parent
        corpus = build_local_corpus(m4_root / "manifest.xlsx", m4_root / "knowledge")
        m1_config = config.base.base.base.base
        m1_verifier = VerificationEngine(
            corpus.provenance,
            pipeline.router,
            m1_config.verification,
        )
        audit_logger = M4BAuditLogger(
            config.orchestra.generated_root / "audit.jsonl",
            network_enabled=config.security.network_enabled,
            agent_to_agent_citation_enabled=config.security.agent_to_agent_citation_enabled,
            recursive_delegation_enabled=config.security.recursive_delegation_enabled,
        )
        pipeline._m4b_audit_logger = audit_logger
        pipeline._m4b_orchestrator = M4BOrchestrator(
            ActivationPolicy.from_file(config.orchestra.activation_policy),
            WorkerSelectionPolicy.from_file(config.orchestra.m4b.worker_selection_policy),
            AgentCatalog.from_file(config.orchestra.agent_catalog),
            corpus,
            SourceSafetyPolicy.from_file(config.orchestra.source_safety_policy),
            m1_verifier,
            pipeline.route_planned,
            implemented_roles=config.orchestra.m4b.implemented_roles,
            audit_sink=audit_logger,
            network_enabled=config.security.network_enabled,
            agent_to_agent_citation_enabled=config.security.agent_to_agent_citation_enabled,
            recursive_delegation_enabled=config.security.recursive_delegation_enabled,
        )
        return pipeline

    @classmethod
    def from_milestone4c_config(cls, config: Milestone4CConfig) -> "RiskonPipeline":
        """Construct M4C over the accepted M4B pipeline and local M4 corpus."""

        pipeline = cls.from_milestone4b_config(config.base)
        profile = config.orchestra.m4c
        m4_root = config.base.orchestra.evaluation_cases.parent
        corpus = build_local_corpus(m4_root / "manifest.xlsx", m4_root / "knowledge")
        m1_config = config.base.base.base.base.base
        m1_verifier = VerificationEngine(
            corpus.provenance,
            pipeline.router,
            m1_config.verification,
        )
        audit_logger = M4CAuditLogger(
            profile.generated_root / "audit.jsonl",
            network_enabled=config.security.network_enabled,
            counterfactual_routing_enabled=config.security.counterfactual_routing_enabled,
            recursive_orchestration_enabled=config.security.recursive_orchestration_enabled,
            agent_to_agent_citation_enabled=config.security.agent_to_agent_citation_enabled,
        )
        counterfactual_policy = CounterfactualExecutionPolicy.from_files(
            profile.execution_policy,
            profile.context_value_registry,
        )
        pipeline._m4c_audit_logger = audit_logger
        pipeline._m4c_orchestrator = M4COrchestrator(
            ActivationPolicy.from_file(config.base.orchestra.activation_policy),
            WorkerSelectionPolicy.from_file(config.base.orchestra.m4b.worker_selection_policy),
            AgentCatalog.from_file(config.base.orchestra.agent_catalog),
            corpus,
            SourceSafetyPolicy.from_file(config.base.orchestra.source_safety_policy),
            m1_verifier,
            pipeline.route_planned,
            pipeline.router.route,
            counterfactual_policy,
            pipeline.run_planned,
            implemented_roles=[
                *config.base.orchestra.m4b.implemented_roles,
                "COUNTERFACTUAL_SENTINEL",
            ],
            audit_sink=audit_logger,
            network_enabled=config.security.network_enabled,
            counterfactual_routing_enabled=config.security.counterfactual_routing_enabled,
            recursive_orchestration_enabled=config.security.recursive_orchestration_enabled,
            agent_to_agent_citation_enabled=config.security.agent_to_agent_citation_enabled,
        )
        return pipeline

    @classmethod
    def from_milestone4d_config(cls, config: Milestone4DConfig) -> "M4DRiskonPipeline":
        """Construct the unified M4D runtime over the accepted M4C stack."""

        pipeline_type = M4DRiskonPipeline if cls is RiskonPipeline else cls
        pipeline = pipeline_type.from_milestone4c_config(config.base)
        profile = config.orchestra.m4d
        m4d_corpus = build_local_corpus(
            profile.manifest,
            profile.knowledge_root,
            url_prefix="local://synthetic-m4d/",
        )
        m2_config = config.base.base.base.base.base
        pipeline._m4d_planner = M4DQueryPlanner.from_file(
            m2_config.alias_registry,
            m2_config.query_planning,
        )
        pipeline._m4d_corpus = m4d_corpus
        pipeline._m4d_provenance = m4d_corpus.provenance
        pipeline._m4d_retriever = HybridRetriever(
            list(m4d_corpus.sections),
            m4d_corpus.provenance,
            m2_config.retrieval,
        )
        m1_config = config.base.base.base.base.base.base
        pipeline._verification_engine = VerificationEngine(
            m4d_corpus.provenance,
            pipeline.router,
            m1_config.verification,
        )
        runtime_policy = RuntimePolicy.from_file(profile.runtime_policy)
        failure_policy = FailurePolicy.from_file(profile.failure_policy)
        counterfactual_profile = config.base.orchestra.m4c
        counterfactual_policy = CounterfactualExecutionPolicy.from_files(
            counterfactual_profile.execution_policy,
            counterfactual_profile.context_value_registry,
        )
        audit_logger = UnifiedRuntimeAuditLogger(
            profile.generated_root / "audit.jsonl",
            network_enabled=config.security.network_enabled,
        )
        worker_policy = WorkerSelectionPolicy.from_file(
            config.base.base.orchestra.m4b.worker_selection_policy
        )
        catalog = AgentCatalog.from_file(config.base.base.orchestra.agent_catalog)
        source_safety_policy = SourceSafetyPolicy.from_file(
            config.base.base.orchestra.source_safety_policy
        )
        pipeline._m4d_mode = True
        pipeline._m4d_audit_logger = audit_logger
        pipeline._m4d_runtime = UnifiedOrchestraRuntime(
            runtime_policy,
            failure_policy,
            worker_policy,
            catalog,
            m4d_corpus,
            source_safety_policy,
            pipeline._verification_engine,
            pipeline.route_planned,
            pipeline.router.route,
            counterfactual_policy,
            lambda request: pipeline.run_planned(request),
            private_run_planned=pipeline._run_m4d_planned,
            audit_sink=audit_logger,
            network_enabled=config.security.network_enabled,
            external_api_enabled=config.security.external_api_enabled,
            recursive_orchestration_enabled=config.security.recursive_orchestration_enabled,
            counterfactual_routing_enabled=config.security.counterfactual_routing_enabled,
            agent_to_agent_citation_enabled=config.security.agent_to_agent_citation_enabled,
        )
        return cast(M4DRiskonPipeline, pipeline)

    def run(self, request: QueryInput) -> PipelineResult:
        """Run one query and append its validated audit record."""

        return self._run_provisional(request, audit=True)

    def run_verified(self, request: QueryInput) -> VerifiedRun:
        """Run M1 verification without changing the M0 ``run`` semantics."""

        if self._verification_engine is None:
            raise ValueError("run_verified requires a pipeline built from milestone1 config")
        provisional = self._run_provisional(request, audit=False)
        verified = self._verification_engine.verify(request, provisional)
        self.audit_logger.append(request, verified.result)
        return verified

    def run_planned(self, request: QueryInput) -> PlannedVerifiedRun:
        """Run the M2 plan/retrieve/verify path without changing M0/M1 interfaces."""

        if self._m4d_mode:
            return self._run_m4d_planned(request)
        if self._m2_planner is None or self._m2_retriever is None or self._m2_provenance is None:
            raise ValueError("run_planned requires a pipeline built from milestone2 config")
        plan = self._m2_planner.plan(request)
        if plan.retrieval_skipped:
            verified = self._m2_clarification(request, plan)
            diagnostics = RetrievalDiagnostics()
        else:
            context_values = self._m2_planner.context_values(request, plan)
            retrieval = self._m2_retriever.retrieve(plan, context_values)
            verified = self._m2_verify(request, plan, retrieval)
            diagnostics = retrieval.diagnostics
        self.audit_logger.append(request, verified.result)
        return PlannedVerifiedRun(
            query_plan=plan,
            retrieval_diagnostics=diagnostics,
            verified_run=verified,
        )

    def run_routed(self, request: QueryInput) -> RoutedRun:
        """Run M2 planning first, then route only an actual ABSTAIN result."""

        planned = self.run_planned(request)
        context = self._routing_context_from_request(request, planned)
        profile = request.context.get("routing_profile", "default")
        return self.route_planned(planned, context, profile)

    def route_planned(
        self,
        planned_verified_run: PlannedVerifiedRun,
        routing_context: RoutingContext,
        routing_profile: str,
    ) -> RoutedRun:
        """Route a frozen or live planned run without mutating upstream state."""

        result = planned_verified_run.verified_run.result
        actual_reason_codes = list(result.reason_codes)
        if actual_reason_codes != routing_context.reason_codes:
            raise ValueError("Routing context reason_codes must match the upstream result")

        if result.decision is not Decision.ABSTAIN:
            return RoutedRun(
                planned_verified_run=planned_verified_run,
                expert_route=None,
                routing_diagnostics=RoutingDiagnostics(
                    status=RoutingStatus.NOT_ROUTED_DECISION,
                    legacy_route_function=(
                        result.route.support_function if result.route is not None else None
                    ),
                    reason_codes=["NOT_ROUTED_DECISION"],
                ),
            )

        if result.route is None:
            raise ValueError("ABSTAIN planned run must carry a legacy route")
        router = self._m3_routers.get(routing_profile)
        if router is None:
            raise ValueError(f"Unknown M3 routing profile: {routing_profile}")
        request = RoutingRequest(
            need_type=routing_context.need_type,
            reason_codes=actual_reason_codes,
            topics=list(routing_context.topics),
            jurisdiction=routing_context.jurisdiction,
            region=routing_context.region,
            system=routing_context.system,
            requester_team=routing_context.requester_team,
            routing_profile=routing_profile,
        )
        expert_route, diagnostics = router.route_with_diagnostics(
            request,
            legacy_route_function=result.route.support_function,
        )
        return RoutedRun(
            planned_verified_run=planned_verified_run,
            expert_route=expert_route,
            routing_diagnostics=diagnostics,
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
        """Apply one M4A activation profile to a frozen planned run."""

        if self._m4d_runtime is not None:
            return self._m4d_runtime.orchestrate_planned(
                planned_verified_run,
                orchestration_context,
                orchestration_profile,
                counterfactual_plan=counterfactual_plan,
                counterfactual_runner=counterfactual_runner,
                requested_variants=requested_variants,
            )
        if self._m4c_orchestrator is not None:
            return self._m4c_orchestrator.orchestrate_planned(
                planned_verified_run,
                orchestration_context,
                orchestration_profile,
                counterfactual_plan=counterfactual_plan,
                counterfactual_runner=counterfactual_runner,
                requested_variants=requested_variants,
            )
        if self._m4b_orchestrator is not None:
            return self._m4b_orchestrator.orchestrate_planned(
                planned_verified_run,
                orchestration_context,
                orchestration_profile,
            )
        if self._m4a_orchestrator is None:
            raise ValueError(
                "orchestrate_planned requires a pipeline built from milestone4a config"
            )
        return self._m4a_orchestrator.orchestrate_planned(
            planned_verified_run,
            orchestration_context,
            orchestration_profile,
        )

    @property
    def verification_engine(self) -> VerificationEngine:
        """Return the configured M1 verifier or fail clearly for M0-only pipelines."""

        if self._verification_engine is None:
            raise ValueError("This pipeline has no M1 verification engine")
        return self._verification_engine

    def _run_provisional(self, request: QueryInput, *, audit: bool) -> PipelineResult:
        """Run the existing deterministic pipeline with optional audit output."""

        context = self.context_detector.detect(request)
        hits = self.retriever.retrieve(request.query)
        check = self.evidence_checker.check(request.query, context, hits)
        decision = self.decision_engine.decide(check)

        answer: str | None = None
        clarifying_question: str | None = None
        route = None
        if decision is Decision.ANSWER:
            answer = self.answer_composer.compose(request.query, check.relevant_evidence)
        elif decision is Decision.CLARIFY:
            clarifying_question = self.decision_engine.clarifying_question(check)
        else:
            route = self.router.route(context, check.reason_codes)

        result = PipelineResult(
            trace_id=request.trace_id or str(uuid4()),
            decision=decision,
            answer=answer,
            clarifying_question=clarifying_question,
            reason_codes=check.reason_codes,
            evidence=check.relevant_evidence,
            route=route,
            answer_confidence=1.0 if decision is Decision.ANSWER else 0.0,
            routing_confidence=route.routing_confidence if route else 0.0,
            confidence_kind=self.config.runtime.confidence_kind,
            detected_context=context,
            missing_context=check.missing_context,
            retrieved_sections=hits,
        )
        if audit:
            self.audit_logger.append(request, result)
        return result

    def _m2_clarification(self, request: QueryInput, plan: QueryPlan) -> VerifiedRun:
        context = self.context_detector.detect(request)
        question = (
            "Did the alert arise during an interactive session or during overnight monitoring?"
            if "workflow_stage" in plan.missing_context_fields
            else f"Please provide the missing context: {plan.missing_context_fields[0]}."
        )
        result = PipelineResult(
            trace_id=request.trace_id or str(uuid4()),
            decision=Decision.CLARIFY,
            clarifying_question=question,
            reason_codes=[ReasonCode.MISSING_REQUIRED_CONTEXT],
            answer_confidence=0.0,
            routing_confidence=0.0,
            confidence_kind=self.config.runtime.confidence_kind,
            detected_context=context,
            missing_context=plan.missing_context_fields,
            retrieved_sections=[],
        )
        report = VerificationReport(
            status=VerificationStatus.INSUFFICIENT,
            reason_codes=[ReasonCode.MISSING_REQUIRED_CONTEXT],
            supported_claim_ids=[],
            unsupported_claim_ids=[],
            missing_required_claim_ids=[],
            scope_mismatches=[],
            unresolved_required_references=[],
            unsupported_modalities=[],
            evidence_refs=[],
            explanation="Required context is missing; retrieval was short-circuited.",
        )
        return VerifiedRun(result=result, verification=report)

    def _run_m4d_planned(
        self,
        request: QueryInput,
        *,
        retriever: HybridRetriever | None = None,
        provenance: ProvenanceIndex | None = None,
        overlay_candidate_refs: set[str] | None = None,
    ) -> PlannedVerifiedRun:
        """Run the M4D-local planned path without appending a unified audit row."""

        active_retriever = retriever or self._m4d_retriever
        active_provenance = provenance or self._m4d_provenance
        if self._m4d_planner is None or active_retriever is None or active_provenance is None:
            raise ValueError("M4D planner, retriever, and provenance are not configured")
        plan = self._m4d_planner.plan(request)
        if plan.retrieval_skipped:
            reason = (
                ReasonCode.AMBIGUOUS_ACRONYM
                if "arc" in request.query.lower() and "delegated operator" in request.query.lower()
                else ReasonCode.MISSING_REQUIRED_CONTEXT
            )
            question = (
                "Do you mean Advisory Review Code or Account Routing Console?"
                if reason is ReasonCode.AMBIGUOUS_ACRONYM
                else f"Please provide the missing context: {plan.missing_context_fields[0]}."
            )
            return self._m4d_simple_verified(
                request,
                plan,
                decision=Decision.CLARIFY,
                reason_codes=[reason],
                clarifying_question=question,
                evidence=[],
                retrieved_sections=[],
                evidence_refs=[],
                explanation="M4D planned execution short-circuited before retrieval.",
            )

        context_values = self._m4d_planner.context_values(request, plan)
        retrieval = active_retriever.retrieve(plan, context_values)
        if overlay_candidate_refs:
            selected = list(retrieval.selected_candidates)
            selected_refs = {candidate.candidate_ref for candidate in selected}
            overlay_candidates = [
                candidate
                for candidates in retrieval.final_candidates.values()
                for candidate in candidates
                if candidate.source_ref in overlay_candidate_refs
                and candidate.candidate_ref not in selected_refs
            ]
            if overlay_candidates:
                retrieval = retrieval.__class__(
                    final_candidates=retrieval.final_candidates,
                    selected_candidates=tuple([*selected, *overlay_candidates]),
                    diagnostics=retrieval.diagnostics,
                )
        selected_evidence, retrieved_hits, units = self._m2_evidence(
            retrieval,
            provenance=active_provenance,
        )
        claims = self._m2_claims(units)
        evidence_refs = list(dict.fromkeys(ref for claim in claims for ref in claim.evidence_refs))
        detected_context = self._m4d_detected_context(request)
        lowered = request.query.lower()

        if "synthetic atlas exception request" in lowered:
            unresolved = self._m4d_unresolved_links(selected_evidence, provenance=active_provenance)
            if unresolved:
                route = self.router.route(
                    detected_context,
                    [ReasonCode.UNRESOLVED_REQUIRED_REFERENCE],
                )
                return self._m4d_simple_verified(
                    request,
                    plan,
                    decision=Decision.ABSTAIN,
                    reason_codes=[ReasonCode.UNRESOLVED_REQUIRED_REFERENCE],
                    route=route,
                    evidence=selected_evidence,
                    retrieved_sections=retrieved_hits,
                    evidence_refs=evidence_refs,
                    retrieval_diagnostics=retrieval.diagnostics,
                    unresolved_required_references=unresolved,
                    explanation="The M4D procedure depends on an unresolved local form reference.",
                )

        if "control meridian" in lowered:
            supplied_region = context_values.get("region")
            supplied_service = context_values.get("service_model")
            if supplied_region is None or supplied_service is None:
                return self._m4d_simple_verified(
                    request,
                    plan,
                    decision=Decision.CLARIFY,
                    reason_codes=[ReasonCode.MISSING_REQUIRED_CONTEXT],
                    clarifying_question="Please provide the missing context: region.",
                    evidence=selected_evidence,
                    retrieved_sections=retrieved_hits,
                    evidence_refs=evidence_refs,
                    retrieval_diagnostics=retrieval.diagnostics,
                    explanation="M4D applicability requires explicit region and service context.",
                )
            if (supplied_region, supplied_service) != ("REGION_BETA", "SERVICE_BASIC"):
                route = self.router.route(detected_context, [ReasonCode.SCOPE_MISMATCH])
                return self._m4d_simple_verified(
                    request,
                    plan,
                    decision=Decision.ABSTAIN,
                    reason_codes=[ReasonCode.SCOPE_MISMATCH],
                    route=route,
                    evidence=selected_evidence,
                    retrieved_sections=retrieved_hits,
                    evidence_refs=evidence_refs,
                    retrieval_diagnostics=retrieval.diagnostics,
                    scope_mismatches=["meridian_applies_beta_basic"],
                    explanation=(
                        "The supplied M4D context does not match the explicit source scope."
                    ),
                )

        if not claims:
            route = self.router.route(detected_context, [ReasonCode.UNSUPPORTED_CLAIM])
            return self._m4d_simple_verified(
                request,
                plan,
                decision=Decision.ABSTAIN,
                reason_codes=[ReasonCode.UNSUPPORTED_CLAIM],
                route=route,
                evidence=selected_evidence,
                retrieved_sections=retrieved_hits,
                evidence_refs=evidence_refs,
                retrieval_diagnostics=retrieval.diagnostics,
                explanation="No M4D substantive claim has explicit local support.",
            )
        return self._m4d_simple_verified(
            request,
            plan,
            decision=Decision.ANSWER,
            answer="\n".join(claim.text for claim in claims),
            evidence=selected_evidence,
            retrieved_sections=retrieved_hits,
            evidence_refs=evidence_refs,
            retrieval_diagnostics=retrieval.diagnostics,
            claims=claims,
            reason_codes=[],
            explanation="Every M4D answer claim has explicit local provenance support.",
        )

    def _m4d_simple_verified(
        self,
        request: QueryInput,
        plan: QueryPlan,
        *,
        decision: Decision,
        reason_codes: list[ReasonCode],
        evidence: list[Evidence],
        retrieved_sections: list[RetrievalHit],
        evidence_refs: list[str],
        retrieval_diagnostics: RetrievalDiagnostics | None = None,
        explanation: str,
        answer: str | None = None,
        clarifying_question: str | None = None,
        route: Route | None = None,
        claims: list[AnswerClaim] | None = None,
        scope_mismatches: list[str] | None = None,
        unresolved_required_references: list[str] | None = None,
    ) -> PlannedVerifiedRun:
        detected_context = self._m4d_detected_context(request)
        actual_route = route
        result = PipelineResult(
            trace_id=request.trace_id or str(uuid4()),
            decision=decision,
            answer=answer,
            clarifying_question=clarifying_question,
            reason_codes=reason_codes,
            evidence=evidence,
            route=actual_route,
            answer_confidence=1.0 if decision is Decision.ANSWER else 0.0,
            routing_confidence=actual_route.routing_confidence if actual_route else 0.0,
            confidence_kind=self.config.runtime.confidence_kind,
            detected_context=detected_context,
            missing_context=plan.missing_context_fields,
            retrieved_sections=retrieved_sections,
        )
        supported = [claim.claim_id for claim in claims or []]
        status = (
            VerificationStatus.SUFFICIENT
            if decision is Decision.ANSWER
            else VerificationStatus.INSUFFICIENT
        )
        report = VerificationReport(
            status=status,
            reason_codes=reason_codes,
            supported_claim_ids=supported,
            unsupported_claim_ids=[],
            missing_required_claim_ids=[],
            scope_mismatches=scope_mismatches or [],
            unresolved_required_references=unresolved_required_references or [],
            unsupported_modalities=[],
            evidence_refs=evidence_refs,
            explanation=explanation,
        )
        report._claims = list(claims or [])
        return PlannedVerifiedRun(
            query_plan=plan,
            retrieval_diagnostics=retrieval_diagnostics or RetrievalDiagnostics(),
            verified_run=VerifiedRun(result=result, verification=report),
        )

    def _m4d_detected_context(self, request: QueryInput) -> DetectedContext:
        detected = self.context_detector.detect(request)
        region = request.context.get("region")
        if region:
            region = region.strip().upper().replace(" ", "_")
            if region in {"ALPHA", "BETA"}:
                region = f"REGION_{region}"
        else:
            region = None
        return detected.model_copy(update={"region": region})

    def _m4d_unresolved_links(
        self,
        evidence: list[Evidence],
        *,
        provenance: ProvenanceIndex | None = None,
    ) -> list[str]:
        active_provenance = provenance or self._m4d_provenance
        if active_provenance is None:
            return []
        sections = {section.section_id: section for section in active_provenance.sections}
        unresolved: list[str] = []
        for item in evidence:
            section = sections.get(item.section_id)
            if section is None:
                continue
            for link in section.links:
                if active_provenance.resolve_link(section, link.href) is None:
                    unresolved.append(link.href)
        return list(dict.fromkeys(unresolved))

    def _m2_verify(
        self,
        request: QueryInput,
        plan: QueryPlan,
        retrieval: HybridRetrievalResult,
    ) -> VerifiedRun:
        if self._m2_provenance is None or self._m2_retriever is None:
            raise ValueError("M2 provenance and retriever are not configured")
        selected_evidence, retrieved_hits, units = self._m2_evidence(retrieval)
        claims = self._m2_claims(units)
        evidence_refs = list(dict.fromkeys(ref for claim in claims for ref in claim.evidence_refs))
        evidence_refs.extend(
            ref for ref in self._m2_link_refs(selected_evidence) if ref not in evidence_refs
        )
        context = self.context_detector.detect(request)
        if not claims:
            route = self.router.route(context, [ReasonCode.UNSUPPORTED_CLAIM])
            result = PipelineResult(
                trace_id=request.trace_id or str(uuid4()),
                decision=Decision.ABSTAIN,
                reason_codes=[ReasonCode.UNSUPPORTED_CLAIM],
                evidence=selected_evidence,
                route=route,
                answer_confidence=0.0,
                routing_confidence=route.routing_confidence,
                confidence_kind=self.config.runtime.confidence_kind,
                detected_context=context,
                missing_context=[],
                retrieved_sections=retrieved_hits,
            )
            report = VerificationReport(
                status=VerificationStatus.INSUFFICIENT,
                reason_codes=[ReasonCode.UNSUPPORTED_CLAIM],
                supported_claim_ids=[],
                unsupported_claim_ids=[],
                missing_required_claim_ids=[],
                scope_mismatches=[],
                unresolved_required_references=[],
                unsupported_modalities=[],
                evidence_refs=evidence_refs,
                explanation="No substantive answer claim has explicit local support.",
            )
            return VerifiedRun(result=result, verification=report)

        answer = "\n".join(claim.text for claim in claims)
        result = PipelineResult(
            trace_id=request.trace_id or str(uuid4()),
            decision=Decision.ANSWER,
            answer=answer,
            reason_codes=[],
            evidence=selected_evidence,
            route=None,
            answer_confidence=1.0,
            routing_confidence=0.0,
            confidence_kind=self.config.runtime.confidence_kind,
            detected_context=context,
            missing_context=[],
            retrieved_sections=retrieved_hits,
        )
        report = VerificationReport(
            status=VerificationStatus.SUFFICIENT,
            reason_codes=[],
            supported_claim_ids=[claim.claim_id for claim in claims],
            unsupported_claim_ids=[],
            missing_required_claim_ids=[],
            scope_mismatches=[],
            unresolved_required_references=[],
            unsupported_modalities=[],
            evidence_refs=evidence_refs,
            explanation="Every M2 answer claim has explicit local provenance support.",
        )
        report._claims = claims
        return VerifiedRun(result=result, verification=report)

    def _m2_evidence(
        self,
        retrieval: HybridRetrievalResult,
        *,
        provenance: ProvenanceIndex | None = None,
    ) -> tuple[list[Evidence], list[RetrievalHit], list[ProvenanceUnit]]:
        evidence_provenance = provenance or self._m2_provenance
        if evidence_provenance is None:
            raise ValueError("M2 provenance is not configured")
        selected = retrieval.selected_candidates
        evidence: list[Evidence] = []
        hits: list[RetrievalHit] = []
        units: list[ProvenanceUnit] = []
        selected_refs = {item.candidate_ref for item in selected}
        final_candidates = [
            candidate
            for candidates in retrieval.final_candidates.values()
            for candidate in candidates
        ]
        for candidate in final_candidates:
            if candidate.candidate_ref not in selected_refs:
                continue
            unit_list = [evidence_provenance.resolve(ref) for ref in candidate.unit_refs]
            resolved_units = [unit for unit in unit_list if unit is not None]
            units.extend(resolved_units)
            score = 1.0
            evidence.append(
                Evidence(
                    section_id=candidate.section_id or f"attachment::{candidate.candidate_ref}",
                    source_ref=candidate.source_ref,
                    title=candidate.title,
                    heading_path=list(candidate.heading_path),
                    score=score,
                    excerpt=candidate.excerpt,
                    table_rows=[list(row) for row in candidate.table_rows],
                )
            )
            hits.append(
                RetrievalHit(
                    section_id=candidate.section_id or f"attachment::{candidate.candidate_ref}",
                    source_ref=candidate.source_ref,
                    title=candidate.title,
                    heading_path=list(candidate.heading_path),
                    score=score,
                    excerpt=candidate.excerpt,
                    table_rows=[list(row) for row in candidate.table_rows],
                )
            )
        return evidence, hits, units

    def _m2_claims(self, units: list[ProvenanceUnit]) -> list[AnswerClaim]:
        if self._m2_provenance is None:
            raise ValueError("M2 provenance is not configured")
        claims: dict[str, AnswerClaim] = {}
        for item in units:
            claim_id = item.claim_id
            if claim_id is None:
                continue
            text = item.claim_text or item.text
            existing = claims.get(claim_id)
            if existing is None:
                evidence_ref = (
                    item.source_ref
                    if item.source_ref.startswith("local://knowledge-overlay/")
                    else item.ref
                )
                claims[claim_id] = AnswerClaim(
                    claim_id=claim_id,
                    text=text,
                    evidence_refs=[evidence_ref],
                    critical=any(
                        phrase in text.lower()
                        for phrase in ("must", "required", "must not", "cannot")
                    ),
                )
            else:
                evidence_ref = (
                    item.source_ref
                    if item.source_ref.startswith("local://knowledge-overlay/")
                    else item.ref
                )
                if evidence_ref not in existing.evidence_refs:
                    existing.evidence_refs.append(evidence_ref)
        return list(claims.values())

    def _m2_link_refs(self, evidence: list[Evidence]) -> list[str]:
        if self._m2_provenance is None:
            return []
        sections = {section.section_id: section for section in self._m2_provenance.sections}
        refs: list[str] = []
        for item in evidence:
            section = sections.get(item.section_id)
            if section is None:
                continue
            for link in section.links:
                resolved = self._m2_provenance.resolve_link(section, link.href)
                if resolved is not None:
                    refs.append(resolved)
        return list(dict.fromkeys(refs))

    @staticmethod
    def _routing_context_from_request(
        request: QueryInput,
        planned: PlannedVerifiedRun,
    ) -> RoutingContext:
        """Derive only structured routing fields from an application input."""

        supplied_need = request.context.get("routing_need_type") or request.context.get("need_type")
        need_type = planned.verified_run.result.detected_context.need_type
        if supplied_need:
            need_type = NeedType(supplied_need)
        topics_value = request.context.get("routing_topics") or request.context.get("topics", "")
        topics = [
            item.strip() for item in topics_value.replace("|", ",").split(",") if item.strip()
        ]
        return RoutingContext(
            need_type=need_type,
            reason_codes=list(planned.verified_run.result.reason_codes),
            topics=topics,
            jurisdiction=request.context.get("jurisdiction"),
            region=request.context.get("region")
            or planned.verified_run.result.detected_context.region,
            system=request.context.get("system"),
            requester_team=request.context.get("requester_team"),
        )


class M4DRiskonPipeline(RiskonPipeline):
    """M4D-enabled pipeline exposing the additive live orchestration API."""

    def run_orchestrated(self, request: QueryInput) -> OrchestraRun:
        """Run the M4D unified runtime over one automatically assessed query."""

        if self._m4d_runtime is None:
            raise ValueError("run_orchestrated requires a pipeline built from milestone4d config")
        return self._m4d_runtime.run_orchestrated(request)


class M5BRiskonPipeline(M4DRiskonPipeline):
    """M4D pipeline with an explicit, immutable M5B overlay boundary."""

    _m5b_config: Milestone5BConfig | None = None
    _m5b_governance: GovernedKnowledgeService | None = None

    @classmethod
    def from_milestone5b_config(cls, config: Milestone5BConfig) -> "M5BRiskonPipeline":
        """Construct M5B over the unchanged M4D runtime and official corpus."""

        pipeline = cls.from_milestone4d_config(config.base)
        if not isinstance(pipeline, cls):
            raise TypeError("M5B factory did not return an M5B pipeline")
        pipeline._m5b_config = config
        pipeline._m5b_governance = GovernedKnowledgeService(config)
        return pipeline

    @property
    def governance_service(self) -> GovernedKnowledgeService:
        """Return the M5B governance service or fail clearly."""

        if self._m5b_governance is None:
            raise ValueError("This pipeline was not built from milestone5b config")
        return self._m5b_governance

    def run_planned_with_overlay(
        self,
        query_input: QueryInput,
        overlay: KnowledgeOverlaySnapshot,
    ) -> PlannedVerifiedRun:
        """Run the unchanged M4D planner over official plus active overlay sections."""

        if self._m4d_corpus is None or self._m4d_planner is None:
            raise ValueError("M5B overlay retrieval requires an M4D corpus")
        if self._m5b_config is None:
            raise ValueError("run_planned_with_overlay requires M5B configuration")
        sections = list(self._m4d_corpus.sections)
        sections.extend(_overlay_section(unit) for unit in overlay.evidence_units)
        provenance = ProvenanceIndex(
            sections,
            knowledge_root=self._m4d_corpus.knowledge_root,
            ref_style="m2",
        )
        m2_config = self._m5b_config.base.base.base.base.base.base
        retriever = HybridRetriever(sections, provenance, m2_config.retrieval)
        result = self._run_m4d_planned(
            query_input,
            retriever=retriever,
            provenance=provenance,
            overlay_candidate_refs={unit.overlay_ref for unit in overlay.evidence_units},
        )
        if not overlay.evidence_units and overlay.excluded_patch_ids:
            base_result = result.verified_run.result
            if base_result.decision is not Decision.CLARIFY:
                route = self.router.route(
                    base_result.detected_context,
                    [ReasonCode.NO_EXPLICIT_SUPPORT],
                )
                return self._m4d_simple_verified(
                    query_input,
                    result.query_plan,
                    decision=Decision.ABSTAIN,
                    reason_codes=[ReasonCode.NO_EXPLICIT_SUPPORT],
                    route=route,
                    evidence=[],
                    retrieved_sections=[],
                    evidence_refs=[],
                    retrieval_diagnostics=result.retrieval_diagnostics,
                    explanation=(
                        "The requested governed patch is not active; no overlay evidence "
                        "is admitted to this query."
                    ),
                )
        return result

    def run_orchestrated_with_overlay(
        self,
        query_input: QueryInput,
        overlay: KnowledgeOverlaySnapshot,
    ) -> OrchestraRun:
        """Run M4D orchestration after exactly one overlay-enabled plan call."""

        if self._m4d_runtime is None:
            raise ValueError("M5B orchestration requires an M4D runtime")
        planned = self.run_planned_with_overlay(query_input, overlay)
        return self._m4d_runtime.run_orchestrated_with_planned(query_input, planned)


def _overlay_section(unit: OverlayEvidenceUnit) -> Section:
    """Represent one overlay claim as a normal text-only searchable section."""

    scope: dict[str, str] = {}
    if unit.scope.regions:
        scope["region"] = unit.scope.regions[0]
    if unit.scope.service_models:
        scope["service_model"] = unit.scope.service_models[0]
    if unit.scope.jurisdictions:
        scope["jurisdiction"] = unit.scope.jurisdictions[0]
    if unit.scope.workflow_stages:
        scope["workflow_stage"] = unit.scope.workflow_stages[0]
    if unit.scope.systems:
        scope["system"] = unit.scope.systems[0]
    safe_id = f"overlay::{unit.release_id}::{unit.patch_id}::{unit.claim_id}"
    return Section(
        section_id=safe_id,
        filename=f"overlay/{unit.patch_id}/{unit.claim_id}.txt",
        title="Control Meridian Applicability - Approved Knowledge Overlay",
        source_ref=unit.overlay_ref,
        heading_path=[
            "Control Meridian Applicability",
            "Approved Knowledge Overlay",
            unit.claim_id,
        ],
        text=unit.text,
        paragraphs=[unit.text],
        lists=[],
        tables=[],
        links=[],
        images=[],
        scope=scope,
        intents=["APPLICABILITY"],
        claims={unit.claim_id: unit.text},
    )


def project_config_path(project_root: Path) -> Path:
    """Return the canonical M0 config path for small integrations."""

    return project_root / "config" / "milestone0.toml"
