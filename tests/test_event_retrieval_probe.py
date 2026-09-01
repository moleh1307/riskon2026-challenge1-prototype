"""Contracts for the retrieval-only event probe boundary."""

import inspect

from riskon.event_eval import retrieval_probe


def test_probe_does_not_call_orchestrated_runtime() -> None:
    source = inspect.getsource(retrieval_probe)

    assert "run_orchestrated" not in source
    assert "run_planned" not in source


def test_probe_diagnostics_are_bounded_and_retrieval_only() -> None:
    assert hasattr(retrieval_probe, "run_retrieval_probe")
    assert hasattr(retrieval_probe, "RetrievalProbeDocument")
