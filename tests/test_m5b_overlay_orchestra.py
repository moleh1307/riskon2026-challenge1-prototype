"""M5B overlay integration with the unified M4D orchestra."""

import pytest
from m5b_helpers import config

from riskon.governance.models import KnowledgeOverlaySnapshot
from riskon.m5b_evaluation import M5BEvaluator
from riskon.models import Decision, QueryInput
from riskon.pipeline import M5BRiskonPipeline


@pytest.fixture(scope="module")
def pipeline_and_overlay():
    document = M5BEvaluator(config()).run()
    return (
        M5BRiskonPipeline.from_milestone5b_config(config()),
        KnowledgeOverlaySnapshot.model_validate(document.overlay_snapshot),
    )


def test_overlay_orchestration_calls_planned_path_once_and_answers(pipeline_and_overlay) -> None:
    pipeline, overlay = pipeline_and_overlay
    run = pipeline.run_orchestrated_with_overlay(
        QueryInput(
            query="Does Control Meridian apply to Service Basic in Region Beta?",
            context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
            trace_id="m5b-overlay-orchestra",
        ),
        overlay,
    )
    assert run.final_verified_run.result.decision is Decision.ANSWER
    assert run.runtime_diagnostics.run_planned_call_count == 1
    assert run.final_verified_run.verification.evidence_refs


def test_overlay_orchestration_preserves_clarification_short_circuit(pipeline_and_overlay) -> None:
    pipeline, overlay = pipeline_and_overlay
    run = pipeline.run_orchestrated_with_overlay(
        QueryInput(
            query="Does Control Meridian apply to the basic service?",
            context={"service_model": "SERVICE_BASIC"},
            trace_id="m5b-overlay-clarify",
        ),
        overlay,
    )
    assert run.final_verified_run.result.decision is Decision.CLARIFY
    assert run.activation_profile.value == "SHORT_CIRCUIT_CLARIFY"
    assert run.orchestra_metrics.worker_execution_count == 0


def test_m5b_pipeline_factory_requires_runtime_for_overlay_methods() -> None:
    pipeline = object.__new__(M5BRiskonPipeline)
    pipeline._m4d_corpus = None
    pipeline._m4d_planner = None
    pipeline._m4d_runtime = None
    pipeline._m5b_config = None
    snapshot = KnowledgeOverlaySnapshot(
        release_id="release",
        release_version="1.0.0",
        reference_time_utc="2026-08-27T12:00:00Z",
    )
    with pytest.raises(ValueError, match="M5B overlay retrieval"):
        pipeline.run_planned_with_overlay(QueryInput(query="query", context={}), snapshot)
    with pytest.raises(ValueError, match="M5B orchestration"):
        pipeline.run_orchestrated_with_overlay(QueryInput(query="query", context={}), snapshot)
