"""Closed-world structured-context registry tests."""

import copy
import json
from pathlib import Path

import pytest
from m4c_helpers import M4C_ROOT

from riskon.orchestra.counterfactual_policy import ContextValueRegistry
from riskon.orchestra.errors import CounterfactualDimensionNotImplementedError


def _raw() -> dict[str, object]:
    return json.loads((M4C_ROOT / "context_value_registry.json").read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_registry_normalizes_values_and_returns_detached_state() -> None:
    registry = ContextValueRegistry.from_file(M4C_ROOT / "context_value_registry.json")
    assert [item.dimension for item in registry.dimensions] == ["region", "service_model"]
    assert registry.canonical_value("region", "region beta") == "REGION_BETA"
    assert registry.replacement_for("service_model", "SERVICE_BASIC") == "SERVICE_PLUS"
    assert registry.value_in_text("region", "REGION_BETA", "only region_beta applies")
    assert registry.infer_context(
        ["region", "service_model"], "Region Beta with Service Basic"
    ) == {"region": "REGION_BETA", "service_model": "SERVICE_BASIC"}

    detached = registry.dimensions
    assert detached[0] is not registry.dimensions[0]


def test_registry_rejects_unknown_dimensions_and_values() -> None:
    registry = ContextValueRegistry.from_file(M4C_ROOT / "context_value_registry.json")
    with pytest.raises(CounterfactualDimensionNotImplementedError):
        registry.dimension("channel")
    with pytest.raises(CounterfactualDimensionNotImplementedError):
        registry.canonical_value("channel", "ADVISORY")
    with pytest.raises(ValueError, match="not registered"):
        registry.canonical_value("region", "REGION_GAMMA")
    with pytest.raises(ValueError, match="not registered"):
        registry.replacement_for("region", "REGION_GAMMA")


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda raw: raw.pop("schema_version"), "fields do not match"),
        (lambda raw: raw.__setitem__("schema_version", "2.0"), "Unsupported"),
        (lambda raw: raw.__setitem__("dimensions", "not-an-array"), "Unsupported"),
        (lambda raw: raw.__setitem__("dimensions", [{}]), "Invalid M4C context registry"),
        (
            lambda raw: raw["dimensions"][0].__setitem__(
                "values", ["REGION_ALPHA", "REGION_ALPHA"]
            ),
            "not unique",
        ),
        (
            lambda raw: raw["dimensions"][0]["replacements"][0].__setitem__("to", "REGION_ALPHA"),
            "replacement is invalid",
        ),
    ],
)
def test_registry_rejects_schema_and_value_mutations(tmp_path: Path, mutator, message: str) -> None:
    raw = copy.deepcopy(_raw())
    mutator(raw)
    with pytest.raises(ValueError, match=message):
        ContextValueRegistry.from_file(_write(tmp_path / "registry.json", raw))


def test_registry_rejects_missing_and_invalid_json(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        ContextValueRegistry.from_file(tmp_path / "missing.json")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid M4C context registry"):
        ContextValueRegistry.from_file(invalid)
    with pytest.raises(ValueError, match="fields do not match"):
        ContextValueRegistry.from_file(_write(tmp_path / "list.json", []))
