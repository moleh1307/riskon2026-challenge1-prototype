"""Closed-world safe-failure policy for the M4D runtime."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field

from riskon.models import Decision
from riskon.orchestra.errors import OrchestraConfigurationError


class FailurePolicyRule(BaseModel):
    """One baseline-decision failure rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str = Field(min_length=1)
    baseline_decision: str = Field(min_length=1)
    action: str = Field(min_length=1)
    fallback_action: str = Field(min_length=1)


class FailurePolicyDocument(BaseModel):
    """Exact JSON schema for M4D failure behavior."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    retry_count: int
    partial_answer_enabled: bool
    rules: tuple[FailurePolicyRule, ...]


class FailurePolicy:
    """Immutable failure policy that never permits partial answers."""

    def __init__(self, document: FailurePolicyDocument, source_path: Path) -> None:
        self.source_path = source_path
        self.schema_version = document.schema_version
        self.retry_count = document.retry_count
        self.partial_answer_enabled = document.partial_answer_enabled
        self._rules = MappingProxyType(
            {rule.rule_id: rule.model_copy(deep=True) for rule in document.rules}
        )

    @classmethod
    def from_file(cls, path: Path) -> FailurePolicy:
        """Load the exact M4D failure policy and reject drift."""

        resolved = path.resolve()
        if not resolved.is_file():
            raise OrchestraConfigurationError(f"M4D failure policy not found: {resolved}")
        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != {
                "schema_version",
                "retry_count",
                "partial_answer_enabled",
                "rules",
            }:
                raise ValueError("M4D failure policy fields do not match the frozen schema")
            document = FailurePolicyDocument.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise OrchestraConfigurationError(f"Invalid M4D failure policy: {exc}") from exc
        if document.schema_version != "1.0":
            raise OrchestraConfigurationError("Unsupported M4D failure policy schema")
        if document.retry_count != 0 or document.partial_answer_enabled:
            raise OrchestraConfigurationError(
                "M4D retries and partial answers must remain disabled"
            )
        ids = [rule.rule_id for rule in document.rules]
        if ids != [
            "ANSWER_WORKER_FAILURE",
            "ABSTAIN_WORKER_FAILURE",
            "CLARIFY_WORKER_FAILURE",
            "CONFIGURATION_FAILURE",
        ]:
            raise OrchestraConfigurationError("M4D failure-rule order does not match the contract")
        expected = {
            "ANSWER_WORKER_FAILURE": ("ANSWER", "FAIL_CLOSED", "NONE"),
            "ABSTAIN_WORKER_FAILURE": (
                "ABSTAIN",
                "PRESERVE_ABSTAIN",
                "ROUTE_AND_OPEN_ORCHESTRATION_INCOMPLETE",
            ),
            "CLARIFY_WORKER_FAILURE": ("CLARIFY", "NO_WORKERS", "PRESERVE_CLARIFY"),
            "CONFIGURATION_FAILURE": ("ANY", "RAISE_CONFIGURATION_ERROR", "NONE"),
        }
        for rule in document.rules:
            if (
                rule.baseline_decision,
                rule.action,
                rule.fallback_action,
            ) != expected[rule.rule_id]:
                raise OrchestraConfigurationError(
                    f"M4D failure rule does not match the contract: {rule.rule_id}"
                )
        return cls(document, resolved)

    def rule_for(self, decision: Decision) -> FailurePolicyRule:
        """Return the rule for one baseline decision."""

        key = f"{decision.value}_WORKER_FAILURE"
        rule = self._rules.get(key)
        if rule is None:
            raise OrchestraConfigurationError(f"No M4D failure rule for {decision.value}")
        return rule.model_copy(deep=True)

    def configuration_rule(self) -> FailurePolicyRule:
        """Return the policy/schema failure rule."""

        return self._rules["CONFIGURATION_FAILURE"].model_copy(deep=True)

    @property
    def rules(self) -> tuple[FailurePolicyRule, ...]:
        """Return detached rules in contract order."""

        return tuple(rule.model_copy(deep=True) for rule in self._rules.values())
