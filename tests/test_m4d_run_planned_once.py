"""M4D normal-flow call-count and input-preservation tests."""

from __future__ import annotations

import inspect
from pathlib import Path

from m4d_helpers import pipeline, request

from riskon.models import QueryInput


def test_normal_flow_calls_run_planned_exactly_once(tmp_path: Path, monkeypatch: object) -> None:
    runtime_pipeline = pipeline(tmp_path)
    req = request("M4D-045", trace_id="once-test")
    original = runtime_pipeline.run_planned
    seen: list[QueryInput] = []

    def counted(value: QueryInput):
        seen.append(value)
        return original(value)

    monkeypatch.setattr(runtime_pipeline, "run_planned", counted)  # type: ignore[attr-defined]
    run = runtime_pipeline.run_orchestrated(req)
    assert len(seen) == 1
    assert seen[0] is req
    assert seen[0].query == req.query
    assert seen[0].context == req.context
    assert run.runtime_diagnostics is not None
    assert run.runtime_diagnostics.run_planned_call_count == 1


def test_normal_flow_never_calls_legacy_pipeline_methods(
    tmp_path: Path, monkeypatch: object
) -> None:
    runtime_pipeline = pipeline(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("legacy pipeline method was called")

    for name in ("run", "run_verified", "run_routed"):
        monkeypatch.setattr(runtime_pipeline, name, forbidden)  # type: ignore[attr-defined]
    run = runtime_pipeline.run_orchestrated(request("M4D-041"))
    assert run.final_verified_run.result.answer


def test_public_method_accepts_only_query_input(tmp_path: Path) -> None:
    method = pipeline(tmp_path).run_orchestrated
    parameters = list(inspect.signature(method).parameters.values())
    assert len(parameters) == 1
    assert parameters[0].name == "request"
    assert parameters[0].annotation in (QueryInput, "QueryInput")
