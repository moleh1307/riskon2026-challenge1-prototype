"""M4C policy and expectation-derivation tests."""

import copy
import json
from pathlib import Path

import pytest
from m4c_helpers import M4C_ROOT

from riskon.models import Decision, ReasonCode
from riskon.orchestra.counterfactual_models import CounterfactualOperation
from riskon.orchestra.counterfactual_policy import CounterfactualExecutionPolicy
from riskon.orchestra.errors import CounterfactualDimensionNotImplementedError


def _policy_raw() -> dict[str, object]:
    return json.loads(
        (M4C_ROOT / "counterfactual_execution_policy.json").read_text(encoding="utf-8")
    )


def _registry_raw() -> dict[str, object]:
    return json.loads((M4C_ROOT / "context_value_registry.json").read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _policy() -> CounterfactualExecutionPolicy:
    return CounterfactualExecutionPolicy.from_files(
        M4C_ROOT / "counterfactual_execution_policy.json",
        M4C_ROOT / "context_value_registry.json",
    )


def test_policy_derives_replace_remove_expectations_and_is_detached() -> None:
    policy = _policy()
    assert policy.candidate_variant_specs() == (
        ("region", CounterfactualOperation.REPLACE),
        ("service_model", CounterfactualOperation.REPLACE),
        ("region", CounterfactualOperation.REMOVE),
    )
    source = "The rule applies only to REGION_BETA with SERVICE_BASIC."
    replacement = policy.build_variant(
        variant_id="v-region",
        dimension="region",
        operation=CounterfactualOperation.REPLACE,
        from_value="region beta",
        to_value="region alpha",
        source_scope_text=source,
        required_context_fields=["region", "service_model"],
    )
    removed = policy.build_variant(
        variant_id="v-remove",
        dimension="region",
        operation=CounterfactualOperation.REMOVE,
        from_value="REGION_BETA",
        to_value=None,
        source_scope_text=source,
        required_context_fields=["region", "service_model"],
    )
    assert replacement.expected_decision is Decision.ABSTAIN
    assert replacement.expected_reason_codes == [ReasonCode.SCOPE_MISMATCH]
    assert removed.expected_decision is Decision.CLARIFY
    assert removed.expected_reason_codes == [ReasonCode.MISSING_REQUIRED_CONTEXT]
    rules = policy.expectation_rules
    assert rules[0] is not policy.expectation_rules[0]
    assert policy.rule("EXACT_SCOPE_REPLACED").rule_id == "EXACT_SCOPE_REPLACED"


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda raw: raw.pop("runtime_backend"), "Invalid M4C execution policy"),
        (lambda raw: raw.__setitem__("schema_version", "2.0"), "Unsupported"),
        (lambda raw: raw.__setitem__("fixture_backend", "MODEL"), "fixture backend"),
        (lambda raw: raw.__setitem__("runtime_backend", "MODEL"), "runtime backend"),
        (
            lambda raw: raw.__setitem__("maximum_dimensions_changed_per_variant", 2),
            "exactly one",
        ),
        (lambda raw: raw.__setitem__("recursive_orchestration_enabled", True), "recursive"),
        (lambda raw: raw.__setitem__("counterfactual_routing_enabled", True), "recursive"),
        (lambda raw: raw.__setitem__("implemented_dimensions", ["region"]), "dimensions"),
        (
            lambda raw: raw.__setitem__(
                "expectation_rules",
                list(reversed(raw["expectation_rules"])),
            ),
            "rule order",
        ),
    ],
)
def test_policy_loader_rejects_closed_world_mutations(
    tmp_path: Path, mutator, message: str
) -> None:
    raw = copy.deepcopy(_policy_raw())
    mutator(raw)
    with pytest.raises(ValueError, match=message):
        CounterfactualExecutionPolicy.from_files(
            _write(tmp_path / "policy.json", raw),
            M4C_ROOT / "context_value_registry.json",
        )


def test_policy_loader_rejects_registry_mismatch_and_bad_files(tmp_path: Path) -> None:
    registry = copy.deepcopy(_registry_raw())
    registry["dimensions"] = list(reversed(registry["dimensions"]))
    with pytest.raises(ValueError, match="registry dimensions"):
        CounterfactualExecutionPolicy.from_files(
            M4C_ROOT / "counterfactual_execution_policy.json",
            _write(tmp_path / "registry.json", registry),
        )
    with pytest.raises(FileNotFoundError, match="not found"):
        CounterfactualExecutionPolicy.from_files(
            tmp_path / "missing.json",
            M4C_ROOT / "context_value_registry.json",
        )
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid M4C execution policy"):
        CounterfactualExecutionPolicy.from_files(
            invalid,
            M4C_ROOT / "context_value_registry.json",
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"dimension": "channel", "operation": CounterfactualOperation.REPLACE},
            "not implemented",
        ),
        (
            {
                "dimension": "region",
                "operation": CounterfactualOperation.REPLACE,
                "from_value": "REGION_BETA",
                "to_value": "REGION_BETA",
            },
            "must change",
        ),
        (
            {
                "dimension": "region",
                "operation": CounterfactualOperation.REPLACE,
                "from_value": "REGION_ALPHA",
                "to_value": "REGION_BETA",
            },
            "original value",
        ),
        (
            {
                "dimension": "region",
                "operation": CounterfactualOperation.REMOVE,
                "from_value": "REGION_BETA",
                "to_value": None,
            },
            "answer-changing",
        ),
        (
            {
                "dimension": "region",
                "operation": CounterfactualOperation.REMOVE,
                "from_value": "REGION_BETA",
                "to_value": "REGION_ALPHA",
            },
            "cannot carry",
        ),
    ],
)
def test_policy_rejects_unsupported_or_invalid_variant_inputs(kwargs, message: str) -> None:
    values = {
        "variant_id": "invalid",
        "dimension": kwargs.get("dimension", "region"),
        "operation": kwargs.get("operation", CounterfactualOperation.REPLACE),
        "from_value": kwargs.get("from_value", "REGION_BETA"),
        "to_value": kwargs.get("to_value", "REGION_ALPHA"),
    }
    if values["operation"] is CounterfactualOperation.REMOVE:
        values["to_value"] = kwargs.get("to_value")
    if values["dimension"] == "channel":
        with pytest.raises(CounterfactualDimensionNotImplementedError, match=message):
            _policy().build_variant(
                **values,
                source_scope_text="REGION_BETA",
                required_context_fields=["region"],
            )
        return
    with pytest.raises(ValueError, match=message):
        _policy().build_variant(
            **values,
            source_scope_text="The rule applies only to REGION_BETA with SERVICE_BASIC.",
            required_context_fields=[],
        )
