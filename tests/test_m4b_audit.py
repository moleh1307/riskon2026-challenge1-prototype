"""M4B audit and generated-artifact tests."""

import json
from pathlib import Path

import pytest
from m4b_helpers import m4b_config, run_case

from riskon.audit import M4B_AUDIT_FIELDS, M4BAuditLogger, validate_m4b_audit_file
from riskon.evaluation import M4BEvaluator
from riskon.reporting import write_m4b_reports


def test_m4b_evaluator_writes_all_safe_artifacts(tmp_path: Path) -> None:
    config = m4b_config(tmp_path)
    document = M4BEvaluator(config).run()
    json_path, markdown_path = write_m4b_reports(document, config.orchestra.generated_root)
    generated = config.orchestra.generated_root
    assert json_path.is_file() and markdown_path.is_file()
    for name in (
        "agent_tasks.jsonl",
        "evidence_ledger.jsonl",
        "material_objections.jsonl",
        "audit.jsonl",
    ):
        assert (generated / name).is_file()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    serialized = json.dumps(loaded)
    assert "http://" not in serialized and "https://" not in serialized
    assert "/Users/" not in serialized
    assert '"query"' not in serialized
    assert "Ignore previous instructions" not in serialized


def test_m4b_audit_schema_and_row_count_are_exact(tmp_path: Path) -> None:
    config = m4b_config(tmp_path)
    M4BEvaluator(config).run()
    audit_path = config.orchestra.generated_root / "audit.jsonl"
    valid, message = validate_m4b_audit_file(audit_path)
    assert valid is True
    assert message == "M4B audit schema valid"
    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 5
    assert all(set(row) == M4B_AUDIT_FIELDS for row in rows)
    assert all(row["baseline_trace_id"] == row["trace_id"] for row in rows)


def test_m4b_audit_logger_rejects_duplicate_and_network_modes(tmp_path: Path) -> None:
    config, pipeline, _case, _planned, run = run_case(tmp_path, "M4-037")
    path = config.orchestra.generated_root / "manual-audit.jsonl"
    logger = M4BAuditLogger(path)
    logger.append(run)
    with pytest.raises(ValueError, match="Duplicate M4B trace ID"):
        logger.append(run)
    with pytest.raises(ValueError, match="network_enabled"):
        M4BAuditLogger(tmp_path / "network.jsonl", network_enabled=True).append(run)
    assert pipeline._m4b_orchestrator is not None
