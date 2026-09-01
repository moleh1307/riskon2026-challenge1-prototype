"""Closed-world policy contracts for the M4D unified runtime."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field

from riskon.orchestra.errors import OrchestraConfigurationError
from riskon.orchestra.models import RiskSignal


class RuntimePolicyRule(BaseModel):
    """One deterministic risk-signal rule declaration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    signal: RiskSignal
    source: str = Field(min_length=1)
    rule: str = Field(min_length=1)


class ExecutionBudget(BaseModel):
    """Structural M4D execution limits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    maximum_total_worker_tasks: int = Field(ge=1)
    maximum_worker_depth: int = Field(ge=1)
    maximum_parallel_discovery_workers: int = Field(ge=1)
    maximum_challenge_rounds: int = Field(ge=1)
    maximum_counterfactual_variants: int = Field(ge=1)
    maximum_counterfactual_depth: int = Field(ge=1)


class RuntimePolicyDocument(BaseModel):
    """Exact JSON document accepted by :class:`RuntimePolicy`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    activation_policy_ref: str = Field(min_length=1)
    counterfactual_policy_ref: str = Field(min_length=1)
    auto_activation_enabled: bool
    risk_signal_order: tuple[RiskSignal, ...]
    risk_signal_rules: tuple[RuntimePolicyRule, ...]
    execution_budget: ExecutionBudget


class RuntimePolicy:
    """Immutable M4D runtime policy with deterministic signal ordering."""

    def __init__(self, document: RuntimePolicyDocument, source_path: Path) -> None:
        self.source_path = source_path
        self.schema_version = document.schema_version
        self.activation_policy_ref = document.activation_policy_ref
        self.counterfactual_policy_ref = document.counterfactual_policy_ref
        self.auto_activation_enabled = document.auto_activation_enabled
        self.risk_signal_order = tuple(document.risk_signal_order)
        self.execution_budget = document.execution_budget.model_copy(deep=True)
        self._rules = MappingProxyType(
            {str(rule.signal): rule.model_copy(deep=True) for rule in document.risk_signal_rules}
        )

    @classmethod
    def from_file(cls, path: Path) -> RuntimePolicy:
        """Load and validate the exact M4D runtime policy, failing closed."""

        resolved = path.resolve()
        if not resolved.is_file():
            raise OrchestraConfigurationError(f"M4D runtime policy not found: {resolved}")
        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("policy must be a JSON object")
            if set(raw) != {
                "schema_version",
                "activation_policy_ref",
                "counterfactual_policy_ref",
                "auto_activation_enabled",
                "risk_signal_order",
                "risk_signal_rules",
                "execution_budget",
            }:
                raise ValueError("M4D runtime policy fields do not match the frozen schema")
            document = RuntimePolicyDocument.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise OrchestraConfigurationError(f"Invalid M4D runtime policy: {exc}") from exc
        if document.schema_version != "1.0":
            raise OrchestraConfigurationError("Unsupported M4D runtime policy schema")
        if not document.auto_activation_enabled:
            raise OrchestraConfigurationError("M4D automatic activation must remain enabled")
        signal_ids = [str(signal) for signal in document.risk_signal_order]
        rule_ids = [str(rule.signal) for rule in document.risk_signal_rules]
        if len(signal_ids) != len(set(signal_ids)) or signal_ids != rule_ids:
            raise OrchestraConfigurationError(
                "M4D risk signal order and rule declarations must be unique and aligned"
            )
        if len(signal_ids) != 20:
            raise OrchestraConfigurationError("M4D must declare exactly 20 risk signals")
        budget = document.execution_budget
        if budget.model_dump(mode="json") != {
            "maximum_total_worker_tasks": 7,
            "maximum_worker_depth": 1,
            "maximum_parallel_discovery_workers": 3,
            "maximum_challenge_rounds": 1,
            "maximum_counterfactual_variants": 3,
            "maximum_counterfactual_depth": 1,
        }:
            raise OrchestraConfigurationError("M4D execution budget does not match the contract")
        return cls(document, resolved)

    @property
    def risk_signal_rules(self) -> tuple[RuntimePolicyRule, ...]:
        """Return detached rules in frozen signal order."""

        return tuple(
            self._rules[str(signal)].model_copy(deep=True) for signal in self.risk_signal_order
        )

    def rule(self, signal: RiskSignal | str) -> RuntimePolicyRule:
        """Return one declared rule or fail closed."""

        rule = self._rules.get(str(signal))
        if rule is None:
            raise OrchestraConfigurationError(f"Unknown M4D risk signal: {signal}")
        return rule.model_copy(deep=True)

    def validate_signals(
        self,
        signals: tuple[RiskSignal, ...] | list[RiskSignal],
    ) -> tuple[RiskSignal, ...]:
        """Validate and canonicalize a signal tuple in policy order."""

        values = {str(signal) for signal in signals}
        unknown = sorted(values - {str(signal) for signal in self.risk_signal_order})
        if unknown:
            raise OrchestraConfigurationError(f"Unknown M4D risk signal(s): {unknown}")
        return tuple(
            RiskSignal(str(signal)) for signal in self.risk_signal_order if str(signal) in values
        )

    def as_dict(self) -> dict[str, object]:
        """Return a detached JSON-shaped policy snapshot."""

        return {
            "schema_version": self.schema_version,
            "activation_policy_ref": self.activation_policy_ref,
            "counterfactual_policy_ref": self.counterfactual_policy_ref,
            "auto_activation_enabled": self.auto_activation_enabled,
            "risk_signal_order": [str(signal) for signal in self.risk_signal_order],
            "risk_signal_rules": [rule.model_dump(mode="json") for rule in self.risk_signal_rules],
            "execution_budget": self.execution_budget.model_dump(mode="json"),
        }
