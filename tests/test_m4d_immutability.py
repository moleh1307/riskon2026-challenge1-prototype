"""M4D baseline and input immutability tests."""

from __future__ import annotations

from pathlib import Path

from m4d_helpers import baseline, pipeline, request, semantic_run


def test_orchestration_does_not_mutate_the_planned_baseline(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path)
    runtime = runtime_pipeline._m4d_runtime
    assert runtime is not None
    req = request("M4D-045")
    planned = runtime_pipeline.run_planned(req)
    before = planned.model_dump(mode="json")
    assessment = runtime.detector.assess(req, planned, runtime._source_safety().report)
    context = runtime._context(req, planned, assessment)
    runtime.orchestrate_planned(
        planned,
        context,
        assessment.selected_activation_profile.value,
        risk_assessment=assessment,
        source_safety_report=runtime._source_safety().report,
        request=req,
        run_planned_call_count=1,
    )
    assert planned.model_dump(mode="json") == before
    assert req.model_dump(mode="json") == request("M4D-045", trace_id=req.trace_id).model_dump(
        mode="json"
    )


def test_frozen_runtime_diagnostics_cannot_be_mutated(tmp_path: Path) -> None:
    run = pipeline(tmp_path).run_orchestrated(request("M4D-041"))
    assert run.runtime_diagnostics is not None
    from pydantic import ValidationError

    try:
        run.runtime_diagnostics.run_planned_call_count = 2  # type: ignore[misc]
    except ValidationError:
        pass
    else:
        raise AssertionError("RuntimeDiagnostics must be frozen")


def test_baseline_fixture_is_not_reused_by_reference_in_the_output(tmp_path: Path) -> None:
    run = pipeline(tmp_path).run_orchestrated(request("M4D-044"))
    frozen = baseline("M4D-044")
    assert run.baseline_run is not frozen
    assert semantic_run(run.baseline_run) == semantic_run(frozen)
