"""Factory that swaps only the M4D corpus while preserving the frozen stack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from riskon.config import load_milestone5b_config
from riskon.event_intake import (
    CorpusIntakeReport,
    CorpusIntakeRequest,
    EventCorpusAdapter,
)
from riskon.event_intake.preparation import prepare_corpus
from riskon.event_runtime.aliases import (
    EventAliasRegistry,
    build_event_alias_registry,
    merge_verified_glossary_aliases,
    write_event_alias_registry,
)
from riskon.event_runtime.config import EventRuntimeConfig
from riskon.event_runtime.corpus_loader import load_event_corpus
from riskon.event_runtime.query_planner import EventQueryPlanner
from riskon.event_runtime.reporting import write_intake_artifacts
from riskon.event_runtime.retrieval import EventHybridRetriever
from riskon.orchestra.counterfactual_runner import LocalPlannedPipelineCounterfactualRunner
from riskon.orchestra.runtime_audit import UnifiedRuntimeAuditLogger
from riskon.orchestra.source_safety import LocalCorpus
from riskon.pipeline import M4DRiskonPipeline, M5BRiskonPipeline
from riskon.query_planning import M4DQueryPlanner
from riskon.verification import VerificationEngine


@dataclass(frozen=True)
class EventRetrievalComponents:
    """Read-only event corpus, planner, and retriever assembled without orchestration."""

    corpus: LocalCorpus
    report: CorpusIntakeReport
    aliases: EventAliasRegistry
    planner: EventQueryPlanner
    retriever: EventHybridRetriever


def build_event_retrieval_components(
    event_config: EventRuntimeConfig,
) -> EventRetrievalComponents:
    """Build only the event retrieval stack, without invoking M4D runtime execution."""

    base_config = load_milestone5b_config(event_config.pipeline_config)
    adapter = EventCorpusAdapter.from_project_root(event_config.project_root)
    corpus, report = load_event_corpus(event_config, adapter)
    aliases = build_event_alias_registry(corpus.sections)
    if corpus.structural is not None:
        source_refs_by_page = {
            section.filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]: section.source_ref
            for section in corpus.sections
        }
        aliases = merge_verified_glossary_aliases(
            aliases,
            corpus.structural.glossary,
            source_refs_by_page,
        )
    write_event_alias_registry(aliases, event_config.alias_registry)

    m2_config = base_config.base.base.base.base.base.base
    planner = EventQueryPlanner.from_aliases(
        aliases.aliases,
        page_titles=[section.title for section in corpus.sections],
        config=m2_config.query_planning,
    )
    retriever = EventHybridRetriever(
        list(corpus.sections),
        corpus.provenance,
        m2_config.retrieval,
        aliases=aliases.aliases,
        reference_graph=(corpus.structural.reference_graph if corpus.structural else None),
        title_boost_enabled=True,
    )
    return EventRetrievalComponents(
        corpus=corpus,
        report=report,
        aliases=aliases,
        planner=planner,
        retriever=retriever,
    )


class EventRuntimeFactory:
    """Build an event-backed M4D pipeline without a parallel answer engine."""

    @staticmethod
    def build(event_config: EventRuntimeConfig) -> M4DRiskonPipeline:
        """Validate event input and replace only the M4D corpus-dependent components."""

        base_config = load_milestone5b_config(event_config.pipeline_config)
        pipeline = M5BRiskonPipeline.from_milestone5b_config(base_config)
        components = build_event_retrieval_components(event_config)
        corpus = components.corpus
        report = components.report
        request = CorpusIntakeRequest(
            source_root=event_config.source_root,
            manifest_path=event_config.manifest,
            column_mapping=event_config.column_mapping,
            output_root=event_config.generated_root / "intake",
        )
        prepared = prepare_corpus(report, request)
        write_intake_artifacts(report, prepared, request, request.output_root)

        m4d_config = base_config.base
        m1_config = m4d_config.base.base.base.base.base.base
        pipeline._m4d_corpus = corpus
        pipeline._m4d_provenance = corpus.provenance
        pipeline._m4d_planner = cast(M4DQueryPlanner, components.planner)
        pipeline._m4d_retriever = components.retriever
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
