"""Fail-closed M4C TOML loading tests."""

import shutil
from pathlib import Path

import pytest
from m4c_helpers import M4C_CONFIG_PATH, PROJECT_ROOT

from riskon.config import _resolve_m4c_path, load_milestone4c_config


def _isolated_config(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "project"
    shutil.copytree(PROJECT_ROOT / "config", root / "config")
    shutil.copytree(PROJECT_ROOT / "data", root / "data")
    return root / "config" / "milestone4c.toml", root


def _mutate_config(tmp_path: Path, old: str, new: str) -> Path:
    config_path, _root = _isolated_config(tmp_path)
    text = config_path.read_text(encoding="utf-8")
    assert old in text
    config_path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return config_path


def test_m4c_loader_resolves_the_repository_local_contract() -> None:
    config = load_milestone4c_config(M4C_CONFIG_PATH)
    assert config.orchestra.m4c.fixture_backend == "FROZEN_COUNTERFACTUAL_FIXTURE_V1"
    assert config.orchestra.m4c.runtime_backend == "LOCAL_PLANNED_PIPELINE_V1"
    assert config.orchestra.m4c.evaluation_cases.is_file()
    assert config.orchestra.m4c.fixture_root.is_dir()


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "non-empty"),
        ("", "non-empty"),
        ("/tmp/outside", "relative"),
        ("../outside", "inside the repository"),
    ],
)
def test_m4c_path_resolution_is_repository_local(value, message: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=message):
        _resolve_m4c_path(tmp_path, value, "test.path")


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("network_enabled = false", "network_enabled = true", "network_enabled"),
        (
            "counterfactual_routing_enabled = false",
            "counterfactual_routing_enabled = true",
            "counterfactual_routing_enabled",
        ),
        (
            "recursive_orchestration_enabled = false",
            "recursive_orchestration_enabled = true",
            "recursive_orchestration_enabled",
        ),
        (
            "agent_to_agent_citation_enabled = false",
            "agent_to_agent_citation_enabled = true",
            "agent_to_agent_citation_enabled",
        ),
        (
            'fixture_backend = "FROZEN_COUNTERFACTUAL_FIXTURE_V1"',
            'fixture_backend = "MODEL"',
            "fixture backend",
        ),
        (
            'runtime_backend = "LOCAL_PLANNED_PIPELINE_V1"',
            'runtime_backend = "MODEL"',
            "runtime backend",
        ),
        ("maximum_parallel_variants = 3", "maximum_parallel_variants = 2", "worker bounds"),
        ('  "service_model"', '  "channel"', "implemented dimensions"),
        ('  "M4-036"', '  "M4-037"', "included cases"),
        ("expected_worker_tasks = 7", "expected_worker_tasks = 8", "cardinalities"),
    ],
)
def test_m4c_loader_rejects_frozen_contract_mutations(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    path = _mutate_config(tmp_path, old, new)
    with pytest.raises(ValueError, match=message):
        load_milestone4c_config(path)


def test_m4c_loader_rejects_base_security_and_missing_inputs(tmp_path: Path) -> None:
    path, root = _isolated_config(tmp_path / "base")
    base_path = root / "config" / "milestone4b.toml"
    base_path.write_text(
        base_path.read_text(encoding="utf-8").replace(
            "network_enabled = false", "network_enabled = true", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="M4B requires network_enabled"):
        load_milestone4c_config(path)

    missing = _mutate_config(tmp_path / "missing", "execution_policy =", "execution_policy =")
    missing.write_text(
        missing.read_text(encoding="utf-8").replace(
            'execution_policy = "data/synthetic/m4c/counterfactual_execution_policy.json"',
            'execution_policy = "data/synthetic/m4c/missing.json"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="contract input"):
        load_milestone4c_config(missing)


def test_m4c_loader_rejects_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_milestone4c_config(tmp_path / "missing.toml")
