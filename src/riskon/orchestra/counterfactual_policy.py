"""Closed-world M4C policy and synthetic context-value registry loaders."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field

from riskon.models import Decision, ReasonCode
from riskon.orchestra.counterfactual_models import (
    CounterfactualOperation,
    CounterfactualVariant,
)
from riskon.orchestra.errors import CounterfactualDimensionNotImplementedError


class RegistryReplacement(BaseModel):
    """One closed-world replacement declared by the synthetic registry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_value: str = Field(alias="from", min_length=1)
    to_value: str = Field(alias="to", min_length=1)

    @property
    def source_value(self) -> str:
        """Return the replacement source value without exposing the JSON alias."""

        return self.from_value


class ContextDimension(BaseModel):
    """One registered structured-context dimension."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: str = Field(min_length=1)
    values: tuple[str, ...] = Field(min_length=1)
    replacements: tuple[RegistryReplacement, ...] = Field(min_length=1)


class ContextValueRegistry:
    """Immutable registry of allowed synthetic context values."""

    def __init__(self, dimensions: tuple[ContextDimension, ...], source_path: Path) -> None:
        self.source_path = source_path
        by_dimension = {item.dimension: item for item in dimensions}
        if len(by_dimension) != len(dimensions):
            raise ValueError("M4C context dimensions must be unique")
        self._dimensions = MappingProxyType(by_dimension)

    @classmethod
    def from_file(cls, path: Path) -> ContextValueRegistry:
        """Load the exact synthetic context-value registry."""

        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"M4C context registry not found: {resolved}")
        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != {"schema_version", "dimensions"}:
                raise ValueError("M4C context registry fields do not match the frozen schema")
            if raw["schema_version"] != "1.0" or not isinstance(raw["dimensions"], list):
                raise ValueError("Unsupported M4C context registry schema")
            dimensions = tuple(
                ContextDimension.model_validate(
                    {
                        "dimension": item["dimension"],
                        "values": tuple(item["values"]),
                        "replacements": tuple(
                            RegistryReplacement.model_validate(replacement)
                            for replacement in item["replacements"]
                        ),
                    }
                )
                for item in raw["dimensions"]
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith(("M4C ", "Unsupported")):
                raise
            raise ValueError(f"Invalid M4C context registry: {exc}") from exc
        for dimension in dimensions:
            values = set(dimension.values)
            if len(values) != len(dimension.values):
                raise ValueError(f"M4C registry values are not unique: {dimension.dimension}")
            if any(
                replacement.source_value not in values
                or replacement.to_value not in values
                or replacement.source_value == replacement.to_value
                for replacement in dimension.replacements
            ):
                raise ValueError(f"M4C registry replacement is invalid: {dimension.dimension}")
        return cls(dimensions, resolved)

    @property
    def dimensions(self) -> tuple[ContextDimension, ...]:
        """Return detached registry dimensions in declaration order."""

        return tuple(item.model_copy(deep=True) for item in self._dimensions.values())

    def dimension(self, name: str) -> ContextDimension:
        """Return one registered dimension or fail closed."""

        item = self._dimensions.get(name)
        if item is None:
            raise CounterfactualDimensionNotImplementedError(
                f"M4C dimension is not implemented: {name}"
            )
        return item.model_copy(deep=True)

    def canonical_value(self, dimension: str, value: str) -> str:
        """Validate and normalize one value to its registry spelling."""

        item = self.dimension(dimension)
        normalized = value.strip().upper().replace(" ", "_")
        for candidate in item.values:
            if candidate.upper() == normalized:
                return candidate
        raise ValueError(f"Value {value!r} is not registered for dimension {dimension!r}")

    def replacement_for(self, dimension: str, value: str) -> str | None:
        """Return the declared opposite value, if one exists."""

        item = self.dimension(dimension)
        canonical = self.canonical_value(dimension, value)
        for replacement in item.replacements:
            if replacement.source_value == canonical:
                return replacement.to_value
        return None

    def value_in_text(self, dimension: str, value: str, text: str) -> bool:
        """Check whether a registered value is explicitly represented in source text."""

        canonical = self.canonical_value(dimension, value)
        lowered = text.lower()
        return canonical.lower() in lowered or canonical.replace("_", " ").lower() in lowered

    def infer_context(self, dimensions: list[str], text: str) -> dict[str, str]:
        """Infer only registered values from a query/plan text snapshot."""

        result: dict[str, str] = {}
        for dimension in dimensions:
            item = self.dimension(dimension)
            for value in item.values:
                if self.value_in_text(dimension, value, text):
                    result[dimension] = value
                    break
        return result


class CounterfactualExpectationRule(BaseModel):
    """One deterministic transition rule from the M4C policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str = Field(min_length=1)
    operation: CounterfactualOperation
    preconditions: tuple[str, ...] = Field(min_length=1)
    expected_decision: Decision
    expected_reason_code: ReasonCode


class CounterfactualExecutionPolicyDocument(BaseModel):
    """Exact JSON schema for the M4C execution policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    base_policy_ref: str
    fixture_backend: str
    runtime_backend: str
    implemented_dimensions: tuple[str, ...]
    maximum_variants_per_case: int = Field(ge=1)
    maximum_parallel_variants: int = Field(ge=1)
    maximum_dimensions_changed_per_variant: int = Field(ge=1)
    variant_precedence: tuple[str, ...]
    recursive_orchestration_enabled: bool
    counterfactual_routing_enabled: bool
    expectation_rules: tuple[CounterfactualExpectationRule, ...]


class CounterfactualExecutionPolicy:
    """Immutable policy view used by planning and transition adjudication."""

    def __init__(
        self,
        document: CounterfactualExecutionPolicyDocument,
        registry: ContextValueRegistry,
        source_path: Path,
    ) -> None:
        self.source_path = source_path
        self.registry = registry
        self.document = document
        self.implemented_dimensions = tuple(document.implemented_dimensions)
        self.maximum_variants_per_case = document.maximum_variants_per_case
        self.maximum_parallel_variants = document.maximum_parallel_variants
        self.maximum_dimensions_changed_per_variant = (
            document.maximum_dimensions_changed_per_variant
        )
        self.recursive_orchestration_enabled = document.recursive_orchestration_enabled
        self.counterfactual_routing_enabled = document.counterfactual_routing_enabled
        self._rules = MappingProxyType(
            {rule.rule_id: rule.model_copy(deep=True) for rule in document.expectation_rules}
        )

    @classmethod
    def from_files(
        cls,
        policy_path: Path,
        registry_path: Path,
    ) -> CounterfactualExecutionPolicy:
        """Load the closed policy and registry without reading evaluation cases."""

        resolved = policy_path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"M4C execution policy not found: {resolved}")
        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
            document = CounterfactualExecutionPolicyDocument.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Invalid M4C execution policy: {exc}") from exc
        if document.schema_version != "1.0":
            raise ValueError("Unsupported M4C execution policy schema")
        if document.fixture_backend != "FROZEN_COUNTERFACTUAL_FIXTURE_V1":
            raise ValueError("M4C fixture backend must be frozen and deterministic")
        if document.runtime_backend != "LOCAL_PLANNED_PIPELINE_V1":
            raise ValueError("M4C runtime backend must use the planned pipeline")
        if document.maximum_dimensions_changed_per_variant != 1:
            raise ValueError("M4C permits exactly one changed context dimension")
        if document.recursive_orchestration_enabled or document.counterfactual_routing_enabled:
            raise ValueError("M4C recursive orchestration and counterfactual routing are disabled")
        if set(document.implemented_dimensions) != {"region", "service_model"}:
            raise ValueError("M4C implemented dimensions do not match the frozen contract")
        rule_ids = [rule.rule_id for rule in document.expectation_rules]
        if rule_ids != ["EXACT_SCOPE_REPLACED", "REQUIRED_CONTEXT_REMOVED"]:
            raise ValueError("M4C expectation-rule order does not match the frozen contract")
        registry = ContextValueRegistry.from_file(registry_path)
        if tuple(item.dimension for item in registry.dimensions) != document.implemented_dimensions:
            raise ValueError("M4C registry dimensions do not match the execution policy")
        return cls(document, registry, resolved)

    @property
    def expectation_rules(self) -> tuple[CounterfactualExpectationRule, ...]:
        """Return detached expectation rules."""

        return tuple(item.model_copy(deep=True) for item in self._rules.values())

    def rule(self, rule_id: str) -> CounterfactualExpectationRule:
        """Return a declared expectation rule."""

        rule = self._rules.get(rule_id)
        if rule is None:
            raise ValueError(f"Unknown M4C expectation rule: {rule_id}")
        return rule.model_copy(deep=True)

    def validate_dimension(self, dimension: str) -> None:
        """Reject dimensions that are outside the current bounded implementation."""

        if dimension not in self.implemented_dimensions:
            raise CounterfactualDimensionNotImplementedError(
                f"M4C dimension is not implemented: {dimension}"
            )
        self.registry.dimension(dimension)

    def build_variant(
        self,
        *,
        variant_id: str,
        dimension: str,
        operation: CounterfactualOperation,
        from_value: str,
        to_value: str | None,
        source_scope_text: str,
        required_context_fields: list[str],
    ) -> CounterfactualVariant:
        """Build one variant and derive its expected transition from policy inputs."""

        self.validate_dimension(dimension)
        source = self.registry.canonical_value(dimension, from_value)
        target = None if to_value is None else self.registry.canonical_value(dimension, to_value)
        if operation is CounterfactualOperation.REPLACE:
            if target is None or target == source:
                raise ValueError("M4C replacement must change a registered value")
            if not self.registry.value_in_text(dimension, source, source_scope_text):
                raise ValueError("M4C replacement requires the original value in source scope")
            if self.registry.value_in_text(dimension, target, source_scope_text):
                raise ValueError("M4C replacement target is already in source scope")
            rule = self.rule("EXACT_SCOPE_REPLACED")
        else:
            if target is not None:
                raise ValueError("M4C REMOVE variants cannot carry a target value")
            if dimension not in required_context_fields:
                raise ValueError("M4C REMOVE requires an answer-changing context field")
            rule = self.rule("REQUIRED_CONTEXT_REMOVED")
        return CounterfactualVariant(
            variant_id=variant_id,
            dimension=dimension,
            operation=operation,
            from_value=source,
            to_value=target,
            expectation_rule_id=rule.rule_id,
            expected_decision=rule.expected_decision,
            expected_reason_codes=[rule.expected_reason_code],
        )

    def candidate_variant_specs(self) -> tuple[tuple[str, CounterfactualOperation], ...]:
        """Return the deterministic dimension/operation order from policy."""

        return tuple(
            (item.split(":", 1)[0], CounterfactualOperation(item.split(":", 1)[1]))
            for item in self.document.variant_precedence
        )
