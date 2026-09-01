"""CLI branch coverage for acceptance and failure diagnostics."""

import json

import pytest
from m3_helpers import PROJECT_ROOT as TEST_PROJECT_ROOT

import riskon.cli as cli
from riskon.cli import _matches, evaluate_milestone3, run_query
from riskon.evaluation import M3Evaluator
from riskon.models import QueryInput


def test_matches_reports_expected_mismatch_details(pipeline) -> None:
    scenarios = json.loads(
        (TEST_PROJECT_ROOT / "data" / "synthetic" / "scenarios.json").read_text(encoding="utf-8")
    )
    answer_request = scenarios[0]
    answer = pipeline.run(
        QueryInput(query=answer_request["query"], context=answer_request.get("context", {}))
    )
    matched, failures = _matches(
        answer,
        {
            "decision": "CLARIFY",
            "reason_codes": ["WRONG_REASON"],
            "answer": "wrong answer",
            "clarifying_question": "wrong question",
            "answer_contains": ["missing phrase"],
            "route": {},
        },
    )
    assert not matched
    assert any("decision=" in failure for failure in failures)
    assert "answer missing 'missing phrase'" in failures
    assert "expected a route" in failures

    abstain_request = scenarios[2]
    abstain = pipeline.run(
        QueryInput(query=abstain_request["query"], context=abstain_request.get("context", {}))
    )
    abstain = abstain.model_copy(update={"evidence": []})
    matched, failures = _matches(
        abstain,
        {
            "decision": "ANSWER",
            "reason_codes": [],
            "evidence": True,
            "answer_contains": ["missing phrase"],
            "route": {"support_function": "WRONG", "expert_id": "WRONG"},
        },
    )
    assert not matched
    assert "expected evidence" in failures
    assert "expected no route" not in failures
    assert any("route support_function did not match" in failure for failure in failures)


@pytest.mark.parametrize("config_name", ["milestone1.toml", "milestone2.toml", "milestone3.toml"])
def test_run_query_supports_all_extension_configs(config_name: str, capsys) -> None:
    config_path = TEST_PROJECT_ROOT / "config" / config_name
    context = json.dumps({"location": "ALPHA", "mandate": "PREMIUM"})
    assert (
        run_query(
            config_path,
            "Which session alerts are active for Advisory Location Alpha and a Premium mandate?",
            context,
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload


def test_m3_cli_failure_path_is_explicit(monkeypatch, capsys) -> None:
    config_path = TEST_PROJECT_ROOT / "config" / "milestone3.toml"
    config = cli.load_milestone3_config(config_path)
    document = M3Evaluator(config).run()
    failed_document = document.model_copy(
        update={
            "metrics": document.metrics.model_copy(update={"m3_case_match_rate": 0.0}),
        }
    )

    class StubEvaluator:
        def __init__(self, _config) -> None:
            pass

        def run(self):
            return failed_document

    monkeypatch.setattr(cli, "M3Evaluator", StubEvaluator)
    assert evaluate_milestone3(config_path) == 1
    assert "M3 FAIL:" in capsys.readouterr().out
