"""End-to-end M0 scenarios."""

import json
from pathlib import Path

from riskon.cli import build_parser, evaluate, main, run_query
from riskon.models import Decision, QueryInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_all_five_scenarios_match(pipeline) -> None:
    scenarios = json.loads(
        (PROJECT_ROOT / "data" / "synthetic" / "scenarios.json").read_text(encoding="utf-8")
    )
    results = [
        pipeline.run(QueryInput(query=item["query"], context=item.get("context", {})))
        for item in scenarios
    ]
    assert [result.decision for result in results] == [
        Decision.ANSWER,
        Decision.CLARIFY,
        Decision.ABSTAIN,
        Decision.ANSWER,
        Decision.ABSTAIN,
    ]
    assert results[1].clarifying_question == (
        "Did the alert arise during an interactive advice session or during "
        "overnight portfolio monitoring?"
    )
    assert [reason.value for reason in results[1].reason_codes] == ["MISSING_REQUIRED_CONTEXT"]
    assert results[2].route is not None
    assert results[2].route.expert_id == "SYN-BRM-BETA-001"
    assert results[2].answer is None
    assert results[3].answer is not None
    assert all(
        phrase in results[3].answer for phrase in ["Concentration", "Regional", "Manual review"]
    )
    assert results[4].route is not None
    assert results[4].route.support_function == "IT_SERVICE_DESK"


def _config_file(tmp_path: Path) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    generated = tmp_path / "generated"
    audit = tmp_path / "audit.jsonl"
    config_path = config_dir / "milestone0.toml"
    config_path.write_text(
        f"""[paths]
data_root = {str(PROJECT_ROOT / "data" / "synthetic")!r}
generated_root = {str(generated)!r}

[retrieval]
top_k = 5
minimum_score = 0.10
ngram_min = 1
ngram_max = 2

[audit]
path = {str(audit)!r}

[security]
network_enabled = false

[runtime]
confidence_kind = "DETERMINISTIC_GATE_PLACEHOLDER"
""",
        encoding="utf-8",
    )
    return config_path


def test_cli_evaluate_writes_artifact(tmp_path: Path) -> None:
    config_path = _config_file(tmp_path)
    assert evaluate(config_path) == 0
    evaluation = json.loads(
        (tmp_path / "generated" / "evaluation.json").read_text(encoding="utf-8")
    )
    assert evaluation["matched_count"] == 5
    assert evaluation["audit_schema_valid"] is True


def test_cli_run_and_parser_are_local_only(tmp_path: Path, capsys) -> None:
    config_path = _config_file(tmp_path)
    assert run_query(config_path, "plain unsupported question", None) == 0
    assert main(["run", "--config", str(config_path), "plain unsupported question"]) == 0
    output = capsys.readouterr().out
    assert '"decision": "ABSTAIN"' in output
    parsed = build_parser().parse_args(["evaluate", "--config", str(config_path)])
    assert parsed.command == "evaluate"
