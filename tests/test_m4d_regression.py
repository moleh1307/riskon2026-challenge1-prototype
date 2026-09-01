"""M4D evaluator, report, and CLI regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from m4d_helpers import M4D_CONFIG_PATH, m4d_config, pipeline

from riskon import cli
from riskon.m4d_evaluation import M4DEvaluator
from riskon.orchestra.errors import OrchestraFailClosedError
from riskon.reporting import render_m4d_markdown, write_m4d_reports


def test_m4d_evaluator_produces_complete_report_and_artifact_set(tmp_path: Path) -> None:
    config = m4d_config(tmp_path)
    document = M4DEvaluator(config).run()
    assert document.m4d_contract == {"expected": 5, "matched": 5}
    assert document.m4_frozen_contract == {"expected": 12, "matched": 12}
    assert document.m4a_regression == {"expected": 5, "matched": 5}
    assert document.m4b_regression == {"expected": 5, "matched": 5}
    assert document.m4c_regression == {"expected": 2, "matched": 2}
    assert document.m0_m3_regression == {"expected": 28, "matched": 28}
    assert document.metrics.failure_contract_count == 3
    assert document.metrics.run_planned_once_accuracy == 1.0
    assert document.audit_schema_valid is True
    assert document.network_enabled is False
    assert {item.id for item in document.scenario_results} == {
        "M4D-041",
        "M4D-042",
        "M4D-043",
        "M4D-044",
        "M4D-045",
    }
    json_path, markdown_path = write_m4d_reports(document, config.orchestra.m4d.generated_root)
    assert (
        json.loads(json_path.read_text(encoding="utf-8"))["metrics"][
            "automatic_activation_accuracy"
        ]
        == 1.0
    )
    markdown = markdown_path.read_text(encoding="utf-8")
    assert markdown == render_m4d_markdown(document)
    assert "does not yet use an LLM" in markdown
    for name in (
        "agent_tasks.jsonl",
        "counterfactual_results.jsonl",
        "orchestra_runs.jsonl",
        "activation_diagnostics.jsonl",
        "audit.jsonl",
    ):
        assert (config.orchestra.m4d.generated_root / name).is_file()


def test_m4d_cli_evaluation_dispatches_to_the_unified_evaluator(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli._is_milestone4d_config(M4D_CONFIG_PATH)
    assert not cli._is_milestone4d_config(M4D_CONFIG_PATH.with_name("missing-m4d.toml"))
    assert cli.evaluate(M4D_CONFIG_PATH) == 0
    output = capsys.readouterr().out
    assert output.startswith("M4D PASS: end-to-end 5/5;")


def test_m4d_cli_run_returns_safe_structured_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.run_query(M4D_CONFIG_PATH, "What is the Synthetic Stability Marker?", None) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["activation_profile"] == "FAST_PATH"
    assert value["final_verified_run"]["result"]["decision"] == "ANSWER"
    assert value["runtime_diagnostics"]["run_planned_call_count"] == 1


def test_m4d_cli_failure_prints_only_the_safe_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FailingPipeline:
        def run_orchestrated(self, _request: object) -> None:
            raise OrchestraFailClosedError(
                stage="WORKER_EXECUTION",
                activation_profile="DUAL_CHECK",
                baseline_decision="ANSWER",
            )

    monkeypatch.setattr(
        cli.RiskonPipeline,
        "from_milestone4d_config",
        lambda _config: FailingPipeline(),
    )
    assert cli.run_query(M4D_CONFIG_PATH, "synthetic query", None) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == OrchestraFailClosedError.safe_message


def test_m4d_runtime_factory_isolated_from_legacy_pipeline(tmp_path: Path) -> None:
    m4d = pipeline(tmp_path)
    assert m4d._m4d_runtime is not None
    assert m4d._m4d_audit_logger is not None
