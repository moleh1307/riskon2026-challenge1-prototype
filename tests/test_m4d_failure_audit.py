"""M4D success/failure audit schemas and privacy checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from m4d_helpers import pipeline, request

from riskon.orchestra.runtime_audit import (
    M4D_FAILURE_AUDIT_FIELDS,
    M4D_SUCCESS_AUDIT_FIELDS,
    UnifiedRuntimeAuditLogger,
    query_hash,
    validate_m4d_audit_file,
)


def _rows(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_success_audit_contains_exact_safe_fields_and_hashes_query(tmp_path: Path) -> None:
    runtime_pipeline = pipeline(tmp_path / "runtime")
    run = runtime_pipeline.run_orchestrated(request("M4D-041", trace_id="audit-success"))
    path = tmp_path / "audit.jsonl"
    logger = UnifiedRuntimeAuditLogger(path)
    logger.append(run)
    row = _rows(path)[0]
    assert set(row) == M4D_SUCCESS_AUDIT_FIELDS
    assert row["query_hash"] == query_hash("What is the Synthetic Stability Marker?")
    assert row["query_hash"] != "What is the Synthetic Stability Marker?"
    assert row["network_enabled"] is False
    assert validate_m4d_audit_file(path) == (True, "M4D audit schema valid")


def test_failure_audit_deduplicates_structured_lists_and_allows_abstain_route(
    tmp_path: Path,
) -> None:
    path = tmp_path / "failure.jsonl"
    logger = UnifiedRuntimeAuditLogger(path)
    logger.append_failure(
        trace_id="failure-abstain-audit",
        baseline_trace_id="baseline",
        baseline_decision="ABSTAIN",
        activation_profile="HUMAN_FIRST",
        failed_stage="WORKER_EXECUTION",
        failed_task_ids=["task:b", "task:a", "task:a"],
        cause_types=["RuntimeError", "RuntimeError"],
        fallback_action="PRESERVE_ABSTAIN_AND_ROUTE",
        route_returned=True,
    )
    row = _rows(path)[0]
    assert set(row) == M4D_FAILURE_AUDIT_FIELDS
    assert row["failed_task_ids"] == ["task:a", "task:b"]
    assert row["cause_types"] == ["RuntimeError"]
    assert validate_m4d_audit_file(path) == (True, "M4D audit schema valid")


def test_audit_logger_rejects_duplicates_network_and_unsafe_values(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = UnifiedRuntimeAuditLogger(path)
    kwargs = dict(
        trace_id="duplicate",
        baseline_trace_id="baseline",
        baseline_decision="ANSWER",
        activation_profile="DUAL_CHECK",
        failed_stage="WORKER_EXECUTION",
        failed_task_ids=[],
        cause_types=[],
        fallback_action="FAIL_CLOSED",
    )
    logger.append_failure(**kwargs)
    with pytest.raises(ValueError, match="Duplicate M4D trace ID"):
        logger.append_failure(**kwargs)
    with pytest.raises(ValueError, match="unsafe content"):
        logger.append_failure(**{**kwargs, "trace_id": "unsafe", "cause_types": ["https://bad"]})
    with pytest.raises(ValueError, match="network_enabled"):
        UnifiedRuntimeAuditLogger(tmp_path / "network.jsonl", network_enabled=True).append_failure(
            **{**kwargs, "trace_id": "network"}
        )


def test_audit_validator_reports_missing_empty_malformed_and_wrong_fields(tmp_path: Path) -> None:
    missing = validate_m4d_audit_file(tmp_path / "missing.jsonl")
    assert missing[0] is False and "not found" in missing[1]
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    assert validate_m4d_audit_file(empty) == (False, "M4D audit file contains no records")
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text("{not-json}\n", encoding="utf-8")
    assert validate_m4d_audit_file(malformed)[0] is False
    wrong = tmp_path / "wrong.jsonl"
    wrong.write_text(json.dumps({"trace_id": "wrong"}) + "\n", encoding="utf-8")
    assert validate_m4d_audit_file(wrong) == (False, "M4D audit fields mismatch at line 1")


def test_audit_validator_reports_success_and_failure_field_invariants(tmp_path: Path) -> None:
    valid_success = {
        "trace_id": "success",
        "timestamp_utc": "now",
        "query_hash": "0" * 64,
        "baseline_trace_id": "baseline",
        "baseline_decision": "ANSWER",
        "risk_signals": [],
        "signal_sources": {},
        "activation_profile": "FAST_PATH",
        "agent_roles": [],
        "task_count": 0,
        "counterfactual_count": 0,
        "final_decision": "ANSWER",
        "route_summary": None,
        "case_capsule_id": None,
        "network_enabled": False,
    }
    valid_failure = {
        "trace_id": "failure",
        "timestamp_utc": "now",
        "baseline_trace_id": "baseline",
        "baseline_decision": "ANSWER",
        "activation_profile": "DUAL_CHECK",
        "failed_stage": "WORKER_EXECUTION",
        "failed_task_ids": [],
        "cause_types": ["RuntimeError"],
        "fallback_action": "FAIL_CLOSED",
        "answer_returned": False,
        "route_returned": False,
        "network_enabled": False,
    }
    for name, row, expected in (
        ("bad-hash", {**valid_success, "query_hash": "short"}, "query hash is invalid"),
        (
            "bad-sources",
            {**valid_success, "signal_sources": []},
            "signal sources are invalid",
        ),
        (
            "bad-answer",
            {**valid_failure, "answer_returned": True},
            "returned an answer",
        ),
        (
            "bad-route",
            {**valid_failure, "route_returned": True},
            "returned a route",
        ),
        (
            "bad-network",
            {**valid_failure, "trace_id": "network", "network_enabled": True},
            "network policy violation",
        ),
        (
            "unsafe",
            {**valid_failure, "trace_id": "unsafe", "cause_types": ["https://bad"]},
            "Unsafe M4D audit content",
        ),
    ):
        path = tmp_path / f"{name}.jsonl"
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        ok, message = validate_m4d_audit_file(path)
        assert ok is False
        assert expected in message


def test_audit_validator_rejects_duplicate_and_blank_trace_ids(tmp_path: Path) -> None:
    row = {
        "trace_id": "same",
        "timestamp_utc": "now",
        "baseline_trace_id": "baseline",
        "baseline_decision": "ABSTAIN",
        "activation_profile": "HUMAN_FIRST",
        "failed_stage": "WORKER_EXECUTION",
        "failed_task_ids": [],
        "cause_types": [],
        "fallback_action": "PRESERVE_ABSTAIN_AND_ROUTE",
        "answer_returned": False,
        "route_returned": True,
        "network_enabled": False,
    }
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    assert validate_m4d_audit_file(duplicate) == (
        False,
        "Duplicate M4D trace ID at line 2: same",
    )
    blank = tmp_path / "blank.jsonl"
    blank.write_text(json.dumps({**row, "trace_id": ""}) + "\n", encoding="utf-8")
    assert validate_m4d_audit_file(blank) == (False, "Duplicate M4D trace ID at line 1: ")
