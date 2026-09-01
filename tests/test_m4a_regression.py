"""CLI and regression-boundary tests for M4A."""

import json
from pathlib import Path

import pytest

import riskon.config as config_module
from riskon import cli
from riskon.config import load_milestone3_config, load_milestone4a_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4A_CONFIG = PROJECT_ROOT / "config" / "milestone4a.toml"


def test_m4a_cli_dispatches_and_writes_the_three_required_outputs() -> None:
    assert cli._is_milestone4a_config(M4A_CONFIG)
    assert not cli._is_milestone3_config(M4A_CONFIG)
    assert cli.evaluate(M4A_CONFIG) == 0
    config = load_milestone4a_config(M4A_CONFIG)
    generated = config.orchestra.generated_root
    assert (generated / "evaluation.json").is_file()
    assert (generated / "evaluation.md").is_file()
    assert (generated / "audit.jsonl").is_file()
    evaluation = json.loads((generated / "evaluation.json").read_text(encoding="utf-8"))
    assert evaluation["metrics"]["m4a_case_match_rate"] == 1.0
    assert evaluation["m3_regression"] == {"expected": 8, "matched": 8}


def test_m4a_cli_does_not_expose_live_query_orchestration() -> None:
    with pytest.raises(ValueError, match="run_orchestrated is not available"):
        cli.run_query(M4A_CONFIG, "a synthetic query", None)


def test_m4a_config_rejects_invalid_relative_paths_and_unknown_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = load_milestone3_config(PROJECT_ROOT / "config" / "milestone3.toml")
    source = M4A_CONFIG.read_text(encoding="utf-8")

    def check(mutated: str, message: str) -> None:
        path = tmp_path / "milestone4a.toml"
        path.write_text(mutated, encoding="utf-8")
        monkeypatch.setattr(config_module, "load_milestone3_config", lambda _path: base)
        with pytest.raises(ValueError, match=message):
            load_milestone4a_config(path)

    check(
        source.replace(
            'evaluation_cases = "data/synthetic/m4/evaluation_cases.json"',
            'evaluation_cases = "/tmp/cases.json"',
        ),
        "relative",
    )
    check(
        source.replace(
            'evaluation_cases = "data/synthetic/m4/evaluation_cases.json"',
            'evaluation_cases = "../../outside.json"',
        ),
        "inside the repository",
    )
    check(
        source.replace(
            'evaluation_cases = "data/synthetic/m4/evaluation_cases.json"', "evaluation_cases = 1"
        ),
        "relative string",
    )
    check(source + "\n[extra]\nvalue = true\n", "fields mismatch")


def test_m4a_config_rejects_activation_switches_and_cardinality_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = load_milestone3_config(PROJECT_ROOT / "config" / "milestone3.toml")
    source = M4A_CONFIG.read_text(encoding="utf-8")
    monkeypatch.setattr(config_module, "load_milestone3_config", lambda _path: base)

    invalid_values = [
        (
            source.replace("worker_execution_enabled = false", "worker_execution_enabled = true"),
            "worker_execution_enabled",
        ),
        (source.replace('"HUMAN_FIRST"', '"DUAL_CHECK"', 1), "supported_profiles"),
        (source.replace('"M4-040"', '"M4-999"'), "included_cases"),
        (source.replace("expected_cases = 5", "expected_cases = 4"), "cardinalities"),
        (source.replace("network_enabled = false", "network_enabled = true"), "network_enabled"),
    ]
    for index, (mutated, message) in enumerate(invalid_values):
        path = tmp_path / f"invalid-{index}.toml"
        path.write_text(mutated, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            load_milestone4a_config(path)
