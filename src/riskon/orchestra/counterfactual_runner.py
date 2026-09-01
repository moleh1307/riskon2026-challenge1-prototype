"""Frozen-fixture and local planned-pipeline counterfactual runners."""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from riskon.models import PlannedVerifiedRun, QueryInput
from riskon.orchestra.counterfactual_models import (
    CounterfactualExecutionRequest,
    CounterfactualOperation,
)
from riskon.orchestra.errors import RecursiveCounterfactualExecutionError


@runtime_checkable
class CounterfactualRunner(Protocol):
    """Runner boundary accepted by the counterfactual sentinel."""

    def run(
        self,
        request: CounterfactualExecutionRequest,
        *,
        counterfactual_depth: int = 1,
    ) -> PlannedVerifiedRun:
        """Execute one bounded planned run."""


class CounterfactualFixtureEntry(BaseModel):
    """Catalog entry for one frozen counterfactual result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str = Field(min_length=1)
    baseline_plan_id: str = Field(min_length=1)
    context_delta: dict[str, Any]
    fixture_ref: str = Field(min_length=1)
    actual_decision: str = Field(min_length=1)
    actual_reason_codes: list[str]


class CounterfactualFixtureCatalog(BaseModel):
    """Exact catalog wrapper for frozen counterfactual fixtures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    fixture_origin: str
    backend: str
    fixtures: list[CounterfactualFixtureEntry]


class FrozenCounterfactualRunner:
    """Resolve a frozen result by structured plan key, never by case ID."""

    backend = "FROZEN_COUNTERFACTUAL_FIXTURE_V1"

    def __init__(self, catalog_path: Path, fixture_root: Path, maximum_depth: int = 1) -> None:
        self.catalog_path = catalog_path.resolve()
        self.fixture_root = fixture_root.resolve()
        self.maximum_depth = maximum_depth
        try:
            catalog = CounterfactualFixtureCatalog.model_validate_json(
                self.catalog_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise ValueError(f"Invalid M4C counterfactual fixture catalog: {exc}") from exc
        if catalog.schema_version != "1.0":
            raise ValueError("Unsupported M4C counterfactual fixture catalog schema")
        if catalog.fixture_origin != "SYNTHETIC_COUNTERFACTUAL_RUN_V1":
            raise ValueError("Unexpected M4C counterfactual fixture origin")
        if catalog.backend != self.backend:
            raise ValueError("M4C counterfactual fixture catalog backend is not frozen")
        entries = {
            self._key(item.baseline_plan_id, item.context_delta): item for item in catalog.fixtures
        }
        if len(entries) != len(catalog.fixtures):
            raise ValueError("M4C counterfactual fixture catalog contains duplicate keys")
        self._entries = entries

    @staticmethod
    def _key(baseline_plan_id: str, delta: dict[str, Any]) -> tuple[str, str, str, str | None]:
        operation = delta.get("operation")
        if operation is None:
            operation = "REPLACE" if delta.get("after") is not None else "REMOVE"
        return (
            baseline_plan_id,
            str(delta.get("dimension")),
            str(operation),
            delta.get("after"),
        )

    def run(
        self,
        request: CounterfactualExecutionRequest,
        *,
        counterfactual_depth: int = 1,
    ) -> PlannedVerifiedRun:
        """Load one schema-valid frozen result and enforce query immutability."""

        self._validate_depth(counterfactual_depth)
        delta = {
            "dimension": request.variant.dimension,
            "operation": request.variant.operation.value,
            "before": request.variant.from_value,
            "after": request.variant.to_value,
        }
        entry = self._entries.get(self._key(request.baseline_plan_id, delta))
        if entry is None:
            raise ValueError("No frozen M4C counterfactual fixture matches the structured key")
        if entry.variant_id != request.variant.variant_id:
            raise ValueError("Frozen counterfactual fixture variant lineage mismatch")
        if entry.context_delta != {
            "dimension": request.variant.dimension,
            "before": request.variant.from_value,
            "after": request.variant.to_value,
        }:
            raise ValueError("Frozen counterfactual fixture context delta mismatch")
        path = self._resolve_fixture(entry.fixture_ref)
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(wrapper, dict):
            raise ValueError("M4C counterfactual fixture must be a JSON object")
        if wrapper.get("baseline_plan_id") != request.baseline_plan_id:
            raise ValueError("M4C counterfactual fixture baseline lineage mismatch")
        if wrapper.get("variant_id") != request.variant.variant_id:
            raise ValueError("M4C counterfactual fixture variant mismatch")
        planned = PlannedVerifiedRun.model_validate(wrapper["planned_verified_run"])
        if planned.query_plan.original_query != request.original_query:
            raise ValueError("Counterfactual runner changed the original query")
        return planned

    def _resolve_fixture(self, reference: str) -> Path:
        prefix = "local://synthetic-m4c/counterfactual-runs/"
        if not reference.startswith(prefix):
            raise ValueError("M4C fixture reference is outside the local counterfactual namespace")
        filename = reference.removeprefix(prefix)
        if not filename or "/" in filename or "\\" in filename:
            raise ValueError("M4C fixture reference must name one fixture file")
        path = (self.fixture_root / filename).resolve()
        if not path.is_relative_to(self.fixture_root) or not path.is_file():
            raise FileNotFoundError(f"M4C counterfactual fixture not found: {path}")
        return path

    def _validate_depth(self, depth: int) -> None:
        if depth > self.maximum_depth:
            raise RecursiveCounterfactualExecutionError(
                "Counterfactual execution exceeded the maximum depth"
            )


RunPlanned = Callable[[QueryInput], PlannedVerifiedRun]


class LocalPlannedPipelineCounterfactualRunner:
    """Apply one context delta and call only the existing ``run_planned`` boundary."""

    backend = "LOCAL_PLANNED_PIPELINE_V1"

    def __init__(self, run_planned: RunPlanned, maximum_depth: int = 1) -> None:
        self.run_planned = run_planned
        self.maximum_depth = maximum_depth

    def run(
        self,
        request: CounterfactualExecutionRequest,
        *,
        counterfactual_depth: int = 1,
    ) -> PlannedVerifiedRun:
        """Run one copied-context request and reject recursive depth."""

        if counterfactual_depth > self.maximum_depth:
            raise RecursiveCounterfactualExecutionError(
                "Counterfactual execution exceeded the maximum depth"
            )
        original_context = deepcopy(request.structured_context)
        mutated_context = deepcopy(original_context)
        dimension = request.variant.dimension
        if request.variant.operation is CounterfactualOperation.REPLACE:
            if request.variant.to_value is None:
                raise ValueError("Local M4C replacement requires a target value")
            mutated_context[dimension] = request.variant.to_value
        else:
            mutated_context.pop(dimension, None)
        changed = {
            key
            for key in set(original_context) | set(mutated_context)
            if original_context.get(key) != mutated_context.get(key)
        }
        if changed != {dimension}:
            raise ValueError("Counterfactual mutation must change exactly one context field")
        query = QueryInput(
            query=request.original_query,
            context=mutated_context,
            trace_id=f"cf:{request.baseline_plan_id}:{request.variant.variant_id}",
        )
        planned = self.run_planned(query)
        if not isinstance(planned, PlannedVerifiedRun):
            planned = PlannedVerifiedRun.model_validate(planned)
        if planned.query_plan.original_query != request.original_query:
            raise ValueError("Local counterfactual runner changed the original query")
        return planned


async def run_maybe_async(
    runner: CounterfactualRunner,
    request: CounterfactualExecutionRequest,
    *,
    counterfactual_depth: int = 1,
) -> PlannedVerifiedRun:
    """Accept synchronous production runners and asynchronous test doubles."""

    result = runner.run(request, counterfactual_depth=counterfactual_depth)
    if inspect.isawaitable(result):
        return await cast(Awaitable[PlannedVerifiedRun], result)
    return result
