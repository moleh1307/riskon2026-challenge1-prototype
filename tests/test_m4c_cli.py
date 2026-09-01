"""M4C CLI dispatch and acceptance-line tests."""

from pathlib import Path

import pytest
from m4c_helpers import M4C_CONFIG_PATH, m4c_config

from riskon import cli
from riskon.evaluation import M4CEvaluator


def test_m4c_cli_dispatch_prints_the_canonical_pass_line(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config = m4c_config(tmp_path)
    monkeypatch.setattr(cli, "load_milestone4c_config", lambda _path: config)
    assert cli.main(["evaluate", "--config", str(M4C_CONFIG_PATH)]) == 0
    output = capsys.readouterr().out
    assert (
        "M4C PASS: counterfactual cases 2/2; consistency pass 1/1; safe transitions 3/3; "
        "scope leak detected 1/1; unsafe answer blocked 1/1; variants 4/4; worker tasks 7/7; "
        "BRM queue route 1/1; M4A regression 5/5; M4B regression 5/5; M0-M3 regression 28/28; "
        "recursive orchestration 0; counterfactual routing 0; baseline mutations 0; "
        "network disabled."
    ) in output


def test_m4c_cli_prints_fail_summary_when_one_gate_is_false(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config = m4c_config(tmp_path)
    valid = M4CEvaluator(config).run()
    failed = valid.model_copy(
        update={
            "metrics": valid.metrics.model_copy(update={"scope_leak_count": 0}),
        }
    )

    class FakeEvaluator:
        def __init__(self, _config) -> None:
            pass

        def run(self):
            return failed

    monkeypatch.setattr(cli, "load_milestone4c_config", lambda _path: config)
    monkeypatch.setattr(cli, "M4CEvaluator", FakeEvaluator)
    assert cli.evaluate_milestone4c(M4C_CONFIG_PATH) == 1
    assert "M4C FAIL: counterfactual cases 2/2" in capsys.readouterr().out


def test_m4c_cli_detects_only_its_own_config_and_blocks_live_query(tmp_path: Path) -> None:
    assert cli._is_milestone4c_config(M4C_CONFIG_PATH)
    assert not cli._is_milestone4c_config(tmp_path / "missing.toml")
    with pytest.raises(ValueError, match="orchestrate_planned"):
        cli.run_query(M4C_CONFIG_PATH, "a query", None)
