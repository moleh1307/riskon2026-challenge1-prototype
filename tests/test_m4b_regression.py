"""M4B CLI and regression-boundary tests."""

import json

import pytest
from m4b_helpers import M4B_CONFIG_PATH

from riskon import cli
from riskon.config import load_milestone4b_config


def test_m4b_cli_dispatches_and_writes_canonical_reports() -> None:
    assert cli._is_milestone4b_config(M4B_CONFIG_PATH)
    assert not cli._is_milestone4a_config(M4B_CONFIG_PATH)
    assert cli.evaluate(M4B_CONFIG_PATH) == 0
    config = load_milestone4b_config(M4B_CONFIG_PATH)
    evaluation = json.loads(
        (config.orchestra.generated_root / "evaluation.json").read_text(encoding="utf-8")
    )
    assert evaluation["metrics"]["m4b_case_match_rate"] == 1.0
    assert evaluation["m4a_regression"] == {"expected": 5, "matched": 5}
    assert evaluation["m3_regression"] == {"expected": 8, "matched": 8}


def test_m4b_does_not_expose_live_query_orchestration() -> None:
    with pytest.raises(ValueError, match="run_orchestrated is not available"):
        cli.run_query(M4B_CONFIG_PATH, "a synthetic query", None)


def test_m4b_report_mentions_counterfactual_stop_condition() -> None:
    config = load_milestone4b_config(M4B_CONFIG_PATH)
    markdown = (config.orchestra.generated_root / "evaluation.md").read_text(encoding="utf-8")
    assert "M4B uses deterministic bounded workers." in markdown
    assert "model-driven swarm" in markdown


def test_m4b_config_dispatch_is_distinct_from_m4a() -> None:
    assert cli._is_milestone4b_config(M4B_CONFIG_PATH)
    assert not cli._is_milestone3_config(M4B_CONFIG_PATH)
