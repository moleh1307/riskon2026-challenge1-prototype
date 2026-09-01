"""Tests for FAST_PATH and SHORT_CIRCUIT_CLARIFY."""

import json
from pathlib import Path

import pytest

from riskon.config import load_milestone3_config, load_milestone4a_config
from riskon.models import PlannedVerifiedRun
from riskon.orchestra.models import OrchestraContext, RiskSignal
from riskon.pipeline import RiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"


def planned(case_id: str) -> PlannedVerifiedRun:
    """Load a frozen M4 planned fixture."""

    raw = json.loads((M4_ROOT / "upstream_runs" / f"{case_id}.planned.json").read_text())
    return PlannedVerifiedRun.model_validate(raw["planned_verified_run"])


def m4a_pipeline(tmp_path: Path) -> RiskonPipeline:
    """Build M4A with isolated generated output."""

    config = load_milestone4a_config(PROJECT_ROOT / "config" / "milestone4a.toml")
    orchestra = config.orchestra.model_copy(update={"generated_root": tmp_path / "m4a"})
    return RiskonPipeline.from_milestone4a_config(
        config.model_copy(update={"orchestra": orchestra})
    )


def test_fast_path_preserves_answer_baseline_and_has_no_workers(tmp_path: Path) -> None:
    pipeline = m4a_pipeline(tmp_path)
    baseline = planned("M4-029")
    before = baseline.model_dump(mode="json")
    run = pipeline.orchestrate_planned(
        baseline,
        OrchestraContext(risk_signals=(), routing_context=None, routing_profile="default"),
        "FAST_PATH",
    )
    assert run.activation_profile.value == "FAST_PATH"
    assert run.final_verified_run.model_dump(mode="json") == before["verified_run"]
    assert run.baseline_run.model_dump(mode="json") == before
    assert run.routed_run is None
    assert run.case_capsule is None
    assert run.agent_tasks == []
    assert run.findings == []
    assert run.candidate_claims == []
    assert run.material_objections == []
    assert run.counterfactual_results == []
    assert run.orchestra_metrics.active_agent_count == 0
    assert baseline.model_dump(mode="json") == before


def test_short_circuit_preserves_exact_clarification(tmp_path: Path) -> None:
    pipeline = m4a_pipeline(tmp_path)
    baseline = planned("M4-033")
    run = pipeline.orchestrate_planned(
        baseline,
        OrchestraContext(
            risk_signals=(RiskSignal("BASELINE_CLARIFY"), RiskSignal("AMBIGUOUS_ACRONYM")),
            routing_context=None,
            routing_profile="default",
        ),
        "SHORT_CIRCUIT_CLARIFY",
    )
    assert run.final_verified_run.result.decision.value == "CLARIFY"
    assert run.final_verified_run.result.answer is None
    assert run.final_verified_run.result.clarifying_question == (
        "Do you mean Advisory Review Code or Account Routing Console?"
    )
    assert run.routed_run is None
    assert run.case_capsule is None
    assert run.orchestra_metrics.worker_execution_count == 0


def test_m3_pipeline_does_not_gain_the_m4a_method() -> None:
    pipeline = RiskonPipeline.from_milestone3_config(
        load_milestone3_config(PROJECT_ROOT / "config" / "milestone3.toml")
    )
    assert not hasattr(pipeline, "run_orchestrated")
    with pytest.raises(ValueError, match="milestone4a"):
        pipeline.orchestrate_planned(
            planned("M4-029"),
            OrchestraContext(risk_signals=(), routing_context=None, routing_profile="default"),
            "FAST_PATH",
        )
