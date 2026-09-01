"""Frozen counterfactual-fixture runner tests."""

import copy
import json
from pathlib import Path

import pytest
from m4c_helpers import M4C_ROOT, case, planned

from riskon.evaluation import M4CEvaluator
from riskon.orchestra.counterfactual_models import CounterfactualExecutionRequest
from riskon.orchestra.counterfactual_policy import CounterfactualExecutionPolicy
from riskon.orchestra.counterfactual_runner import FrozenCounterfactualRunner
from riskon.orchestra.errors import RecursiveCounterfactualExecutionError


def _runner() -> FrozenCounterfactualRunner:
    return FrozenCounterfactualRunner(
        M4C_ROOT / "counterfactual_fixture_catalog.json",
        M4C_ROOT / "counterfactual_runs",
    )


def _request(case_id: str, index: int = 0) -> CounterfactualExecutionRequest:
    baseline = planned(case_id).planned_verified_run
    value = M4CEvaluator._requested_variants(case(case_id))[index]
    return CounterfactualExecutionRequest(
        baseline_plan_id=baseline.query_plan.plan_id,
        original_query=baseline.query_plan.original_query,
        structured_context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
        variant=value,
    )


def _catalog_raw() -> dict[str, object]:
    return json.loads(
        (M4C_ROOT / "counterfactual_fixture_catalog.json").read_text(encoding="utf-8")
    )


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_frozen_runner_resolves_all_four_variants_and_preserves_query() -> None:
    runner = _runner()
    for case_id, count in (("M4-035", 3), ("M4-036", 1)):
        for index in range(count):
            request = _request(case_id, index)
            result = runner.run(request)
            assert result.query_plan.original_query == request.original_query
            assert result.verified_run.result.trace_id.endswith(f"{case_id}-CF-0{index + 1}")


def test_frozen_runner_accepts_remove_operation_and_rejects_depth() -> None:
    runner = _runner()
    assert runner.run(_request("M4-035", 2)).verified_run.result.decision.value == "CLARIFY"
    with pytest.raises(RecursiveCounterfactualExecutionError, match="maximum depth"):
        runner.run(_request("M4-035"), counterfactual_depth=2)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"baseline_plan_id": "unknown"}, "No frozen"),
        ({"variant": {"variant_id": "wrong"}}, "lineage mismatch"),
        ({"original_query": "changed"}, "original query"),
    ],
)
def test_frozen_runner_rejects_lineage_and_query_mutations(update, message: str) -> None:
    request = _request("M4-035")
    if "variant" in update:
        update = {"variant": request.variant.model_copy(update=update["variant"])}
    bad = request.model_copy(update=update)
    with pytest.raises(ValueError, match=message):
        _runner().run(bad)


def test_frozen_runner_rejects_bad_catalog_context_and_references(tmp_path: Path) -> None:
    request = _request("M4-035")
    raw = _catalog_raw()
    raw["fixtures"][0]["context_delta"]["before"] = "REGION_ALPHA"
    with pytest.raises(ValueError, match="context delta"):
        FrozenCounterfactualRunner(
            _write(tmp_path / "delta.json", raw),
            M4C_ROOT / "counterfactual_runs",
        ).run(request)

    raw = _catalog_raw()
    raw["fixtures"][0]["fixture_ref"] = "local://other/fixture.json"
    with pytest.raises(ValueError, match="outside"):
        FrozenCounterfactualRunner(
            _write(tmp_path / "namespace.json", raw),
            M4C_ROOT / "counterfactual_runs",
        ).run(request)

    raw = _catalog_raw()
    raw["fixtures"][0]["fixture_ref"] = "local://synthetic-m4c/counterfactual-runs/missing.json"
    with pytest.raises(FileNotFoundError, match="not found"):
        FrozenCounterfactualRunner(
            _write(tmp_path / "missing.json", raw),
            M4C_ROOT / "counterfactual_runs",
        ).run(request)


def test_frozen_runner_rejects_duplicate_keys_and_bad_catalog_files(tmp_path: Path) -> None:
    raw = _catalog_raw()
    raw["fixtures"].append(copy.deepcopy(raw["fixtures"][0]))
    with pytest.raises(ValueError, match="duplicate keys"):
        FrozenCounterfactualRunner(
            _write(tmp_path / "duplicate.json", raw),
            M4C_ROOT / "counterfactual_runs",
        )
    with pytest.raises(ValueError, match="Invalid M4C counterfactual fixture catalog"):
        FrozenCounterfactualRunner(tmp_path / "missing.json", M4C_ROOT / "counterfactual_runs")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid M4C"):
        FrozenCounterfactualRunner(invalid, M4C_ROOT / "counterfactual_runs")


def test_policy_and_catalog_backend_labels_are_distinct_and_frozen() -> None:
    policy = CounterfactualExecutionPolicy.from_files(
        M4C_ROOT / "counterfactual_execution_policy.json",
        M4C_ROOT / "context_value_registry.json",
    )
    assert policy.document.fixture_backend == _runner().backend
    assert policy.document.runtime_backend == "LOCAL_PLANNED_PIPELINE_V1"
