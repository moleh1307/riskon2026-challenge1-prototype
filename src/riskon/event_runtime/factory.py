"""Factory that swaps only the M4D corpus while preserving the frozen stack."""

from __future__ import annotations

from riskon.config import load_milestone5b_config
from riskon.event_intake import CorpusIntakeRequest, EventCorpusAdapter
from riskon.event_intake.preparation import prepare_corpus
from riskon.event_runtime.config import EventRuntimeConfig
from riskon.event_runtime.corpus_loader import load_event_corpus
from riskon.event_runtime.reporting import write_intake_artifacts
from riskon.hybrid_retrieval import HybridRetriever
from riskon.orchestra.counterfactual_runner import LocalPlannedPipelineCounterfactualRunner
from riskon.orchestra.runtime_audit import UnifiedRuntimeAuditLogger
from riskon.pipeline import M4DRiskonPipeline, M5BRiskonPipeline
from riskon.verification import VerificationEngine


class EventRuntimeFactory:
    """Build an event-backed M4D pipeline without a parallel answer engine."""

    @staticmethod
    def build(event_config: EventRuntimeConfig) -> M4DRiskonPipeline:
        """Validate event input and replace only the M4D corpus-dependent components."""

        base_config = load_milestone5b_config(event_config.pipeline_config)
        pipeline = M5BRiskonPipeline.from_milestone5b_config(base_config)
        adapter = EventCorpusAdapter.from_project_root(event_config.project_root)
        corpus, report = load_event_corpus(event_config, adapter)
        request = CorpusIntakeRequest(
            source_root=event_config.source_root,
            manifest_path=event_config.manifest,
            column_mapping=event_config.column_mapping,
            output_root=event_config.generated_root / "intake",
        )
        prepared = prepare_corpus(report, request)
        write_intake_artifacts(report, prepared, request, request.output_root)

        m4d_config = base_config.base
        m2_config = m4d_config.base.base.base.base.base
        m1_config = m4d_config.base.base.base.base.base.base
        pipeline._m4d_corpus = corpus
        pipeline._m4d_provenance = corpus.provenance
        pipeline._m4d_retriever = HybridRetriever(
            list(corpus.sections), corpus.provenance, m2_config.retrieval
        )
        pipeline._verification_engine = VerificationEngine(
            corpus.provenance,
            pipeline.router,
            m1_config.verification,
        )
        runtime = pipeline._m4d_runtime
        if runtime is None:
            raise ValueError("M4D base runtime was not constructed")
        runtime.corpus = corpus
        runtime.m1_adjudicator = runtime.m1_adjudicator.__class__(
            corpus, pipeline._verification_engine
        )
        runtime.run_planned = lambda query: pipeline.run_planned(query)
        runtime.private_run_planned = pipeline._run_m4d_planned
        runtime.local_runner = LocalPlannedPipelineCounterfactualRunner(
            runtime.private_run_planned,
            maximum_depth=runtime.runtime_policy.execution_budget.maximum_counterfactual_depth,
        )
        runtime.default_routing_profile = event_config.routing_profile
        audit_logger = UnifiedRuntimeAuditLogger(
            event_config.generated_root / "audit.jsonl",
            network_enabled=event_config.network_enabled,
        )
        runtime.audit_sink = audit_logger
        pipeline._m4d_audit_logger = audit_logger
        return pipeline
