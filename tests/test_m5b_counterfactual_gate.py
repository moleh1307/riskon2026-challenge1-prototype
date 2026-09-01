"""Sandboxed M5B counterfactual containment checks."""

from dataclasses import dataclass

import pytest
from m5b_helpers import valid_patch, valid_scope

from riskon.governance.counterfactual_gate import (
    CounterfactualExpectation,
    CounterfactualGate,
    scope_for_context,
)
from riskon.models import Decision, QueryInput


def expectation(
    decision: Decision, *, context: dict[str, str] | None = None
) -> CounterfactualExpectation:
    return CounterfactualExpectation(
        query_input=QueryInput(query="synthetic query", context=context or {}),
        decision=decision,
    )


def test_empty_expectations_fail_closed() -> None:
    assert CounterfactualGate().evaluate(valid_patch(), []) == (
        False,
        0,
        "counterfactual expectation set is empty",
    )


def test_structural_single_abstain_probe_passes_for_narrow_scope() -> None:
    patch = valid_patch(
        scope=valid_scope(regions=["REGION_BETA"], service_models=["SERVICE_BASIC"])
    )
    assert CounterfactualGate().evaluate(patch, [expectation(Decision.ABSTAIN)]) == (
        True,
        1,
        "non-active patch remains unavailable to retrieval",
    )


@pytest.mark.parametrize(
    "scope",
    [
        valid_scope(regions=["REGION_ALPHA", "REGION_BETA"]),
        valid_scope(service_models=["SERVICE_BASIC", "SERVICE_PLUS"]),
    ],
)
def test_structural_single_abstain_probe_rejects_overbroad_scope(scope) -> None:
    assert CounterfactualGate().evaluate(
        valid_patch(scope=scope), [expectation(Decision.ABSTAIN)]
    ) == (False, 0, "candidate patch exposes an overbroad counterfactual scope")


def test_structural_exact_answer_and_alternate_abstain_pass() -> None:
    patch = valid_patch(
        scope=valid_scope(regions=["REGION_BETA"], service_models=["SERVICE_BASIC"])
    )
    expectations = [
        expectation(
            Decision.ABSTAIN,
            context={"region": "REGION_ALPHA", "service_model": "SERVICE_BASIC"},
        ),
        expectation(
            Decision.ABSTAIN,
            context={"region": "REGION_BETA", "service_model": "SERVICE_PLUS"},
        ),
        expectation(Decision.CLARIFY, context={"service_model": "SERVICE_BASIC"}),
    ]
    ok, count, details = CounterfactualGate().evaluate(patch, expectations)
    assert (ok, count) == (True, 3)
    assert details == "structural scope probes passed"


def test_structural_answer_probe_with_exact_scope_is_allowed() -> None:
    patch = valid_patch()
    ok, count, _ = CounterfactualGate().evaluate(
        patch,
        [
            expectation(
                Decision.ANSWER, context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"}
            )
        ],
    )
    assert (ok, count) == (True, 1)


def test_structural_clarify_probe_with_region_fails() -> None:
    ok, count, details = CounterfactualGate().evaluate(
        valid_patch(),
        [expectation(Decision.CLARIFY, context={"region": "REGION_BETA"})],
    )
    assert ok is False
    assert count == 0
    assert "required region" in details


def test_structural_abstain_probe_matching_exact_scope_fails() -> None:
    ok, count, details = CounterfactualGate().evaluate(
        valid_patch(),
        [
            expectation(
                Decision.ABSTAIN,
                context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
            ),
            expectation(Decision.ANSWER),
        ],
    )
    assert ok is False
    assert count == 0
    assert "exact scope" in details


@dataclass
class FakeResult:
    decision: Decision


@dataclass
class FakeVerified:
    result: FakeResult


@dataclass
class FakeRun:
    verified_run: FakeVerified


@pytest.mark.parametrize("wrapped", [False, True])
def test_runner_path_accepts_direct_or_wrapped_result(wrapped: bool) -> None:
    def runner(snapshot, query):
        del snapshot, query
        result = FakeResult(Decision.ANSWER)
        if wrapped:
            return FakeRun(FakeVerified(result))
        return result

    gate = CounterfactualGate(runner)
    ok, count, details = gate.evaluate(valid_patch(), [expectation(Decision.ANSWER)])
    assert (ok, count) == (True, 1)
    assert "sandbox scope" in details


def test_runner_path_stops_at_first_decision_mismatch() -> None:
    calls = 0

    def runner(snapshot, query):
        nonlocal calls
        del snapshot, query
        calls += 1
        return FakeResult(Decision.ABSTAIN)

    expectations = [expectation(Decision.ABSTAIN), expectation(Decision.ANSWER)]
    ok, count, details = CounterfactualGate(runner).evaluate(valid_patch(), expectations)
    assert ok is False
    assert count == 1
    assert calls == 2
    assert "decision mismatch" in details


def test_scope_for_context_constructs_only_declared_dimensions() -> None:
    scope = scope_for_context({"region": "REGION_BETA", "service_model": "SERVICE_BASIC"})
    assert scope.regions == ["REGION_BETA"]
    assert scope.service_models == ["SERVICE_BASIC"]
    assert scope.jurisdictions == []
