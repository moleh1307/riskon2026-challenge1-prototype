"""M5B command-line evaluation and query surface."""

import json
from pathlib import Path

from m5b_helpers import PROJECT_ROOT

from riskon import cli

M5B_CONFIG = PROJECT_ROOT / "config" / "milestone5b.toml"


def test_m5b_config_detector_is_specific() -> None:
    assert cli._is_milestone5b_config(M5B_CONFIG) is True
    assert cli._is_milestone5b_config(PROJECT_ROOT / "config" / "milestone4d.toml") is False
    assert cli._is_milestone5b_config(PROJECT_ROOT / "config" / "does-not-exist.toml") is False


def test_m5b_evaluate_command_returns_pass_and_writes_reports(capsys) -> None:
    assert cli.evaluate(M5B_CONFIG) == 0
    output = capsys.readouterr().out
    assert output.startswith("M5B PASS:")
    root = PROJECT_ROOT / "data" / "generated" / "m5b"
    assert (root / "evaluation.json").is_file()
    assert (root / "evaluation.md").is_file()
    assert (
        json.loads((root / "evaluation.json").read_text())["metrics"]["m5b_case_match_rate"] == 1.0
    )


def test_m5b_run_query_uses_orchestrated_pipeline(capsys) -> None:
    result = cli.run_query(
        M5B_CONFIG,
        "Does Control Meridian apply to Service Basic in Region Beta?",
        json.dumps({"region": "REGION_BETA", "service_model": "SERVICE_BASIC"}),
    )
    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["final_verified_run"]["result"]["decision"] in {
        "ANSWER",
        "ABSTAIN",
        "CLARIFY",
    }


def test_m5b_run_query_accepts_missing_context_json(capsys) -> None:
    assert cli.run_query(M5B_CONFIG, "Does Control Meridian apply?", None) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "final_verified_run" in payload


def test_parser_main_dispatches_m5b_evaluation(monkeypatch) -> None:
    seen: list[Path] = []

    def fake_evaluate(path: Path) -> int:
        seen.append(path)
        return 7

    monkeypatch.setattr(cli, "evaluate", fake_evaluate)
    assert cli.main(["evaluate", "--config", str(M5B_CONFIG)]) == 7
    assert seen == [M5B_CONFIG]
