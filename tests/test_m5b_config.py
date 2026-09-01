"""M5B configuration fail-closed validation."""

import shutil
from pathlib import Path

import pytest
from m5b_helpers import M5B_CONFIG_PATH

from riskon.config import load_milestone5b_config


def write_config(tmp_path: Path, text: str) -> Path:
    project = tmp_path / "project"
    config_dir = project / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir = project / "data"
    if not data_dir.exists():
        shutil.copytree(M5B_CONFIG_PATH.parents[1] / "data" / "synthetic", data_dir / "synthetic")
    for source in M5B_CONFIG_PATH.parent.glob("*.toml"):
        if source.name == "milestone5b.toml":
            continue
        target = config_dir / source.name
        if not target.exists():
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    path = config_dir / "milestone5b.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_canonical_m5b_config_loads_with_m4d_base() -> None:
    loaded = load_milestone5b_config(M5B_CONFIG_PATH)
    assert loaded.base.orchestra.m4d.auto_activation_enabled is True
    assert loaded.governance.policy_ci.required_regression_passes == 45
    assert loaded.security.network_enabled is False


def test_missing_m5b_config_is_reported(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_milestone5b_config(tmp_path / "missing.toml")


def test_root_and_nested_key_shapes_are_closed(tmp_path: Path) -> None:
    original = M5B_CONFIG_PATH.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="root"):
        load_milestone5b_config(write_config(tmp_path, "extra = true\n" + original))
    with pytest.raises(ValueError, match="governance.overlay"):
        load_milestone5b_config(
            write_config(
                tmp_path,
                original.replace("[governance.overlay]", "[governance.overlay]\nextra = true"),
            )
        )
    with pytest.raises(ValueError, match="governance.policy_ci"):
        load_milestone5b_config(
            write_config(
                tmp_path,
                original.replace("[governance.policy_ci]", "[governance.policy_ci]\nextra = true"),
            )
        )


@pytest.mark.parametrize(
    ("needle", "replacement", "fragment"),
    [
        (
            'contract_cases = "data/synthetic/m5a/evaluation_cases.json"',
            'contract_cases = "/tmp/cases.json"',
            "must be relative",
        ),
        (
            'contract_cases = "data/synthetic/m5a/evaluation_cases.json"',
            'contract_cases = "../cases.json"',
            "inside the repository",
        ),
        (
            'contract_cases = "data/synthetic/m5a/evaluation_cases.json"',
            "contract_cases = 1",
            "non-empty relative string",
        ),
        ("network_enabled = false", "network_enabled = true", "network and external_api"),
        ("external_api_enabled = false", "external_api_enabled = true", "network and external_api"),
        ("telemetry_enabled = false", "telemetry_enabled = true", "telemetry_enabled"),
        (
            "official_corpus_mutation_enabled = false",
            "official_corpus_mutation_enabled = true",
            "official corpus mutation",
        ),
        (
            "automatic_approval_enabled = false",
            "automatic_approval_enabled = true",
            "automatic, agent",
        ),
        ("special_ranking_boost = false", "special_ranking_boost = true", "overlay policy"),
        ("required_regression_passes = 45", "required_regression_passes = 44", "regression gate"),
        (
            "counterfactual_routing_enabled = false",
            "counterfactual_routing_enabled = true",
            "counterfactual routing",
        ),
        (
            "recursive_policy_ci_enabled = false",
            "recursive_policy_ci_enabled = true",
            "recursive Policy CI",
        ),
        ("expected_cases = 5", "expected_cases = 4", "cardinalities"),
    ],
)
def test_m5b_configuration_rejects_unsafe_or_drifted_values(
    tmp_path: Path, needle: str, replacement: str, fragment: str
) -> None:
    original = M5B_CONFIG_PATH.read_text(encoding="utf-8")
    assert needle in original
    with pytest.raises(ValueError, match=fragment):
        load_milestone5b_config(write_config(tmp_path, original.replace(needle, replacement, 1)))


def test_missing_contract_input_is_reported(tmp_path: Path) -> None:
    original = M5B_CONFIG_PATH.read_text(encoding="utf-8")
    text = original.replace(
        'claim_relations = "data/synthetic/m5b/claim_relations.json"',
        'claim_relations = "data/synthetic/m5b/missing.json"',
    )
    with pytest.raises(FileNotFoundError, match="contract input"):
        load_milestone5b_config(write_config(tmp_path, text))
