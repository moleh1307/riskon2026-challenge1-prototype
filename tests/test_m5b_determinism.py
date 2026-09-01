"""Determinism of M5B synthetic evaluation artifacts."""

from pathlib import Path

from m5b_helpers import config

from riskon.m5b_evaluation import M5BEvaluator


def artifact_bytes(root: Path) -> dict[str, bytes]:
    return {
        name: (root / name).read_bytes()
        for name in (
            "policy_ci_reports.jsonl",
            "governance_events.jsonl",
            "knowledge_releases.jsonl",
            "overlay_snapshot.json",
            "audit.jsonl",
        )
    }


def test_m5b_evaluator_and_event_log_are_byte_deterministic() -> None:
    first = M5BEvaluator(config()).run()
    first_artifacts = artifact_bytes(config().governance.generated_root)
    second = M5BEvaluator(config()).run()
    second_artifacts = artifact_bytes(config().governance.generated_root)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first_artifacts == second_artifacts
