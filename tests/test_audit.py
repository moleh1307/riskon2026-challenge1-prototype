"""Audit schema and local-only trace tests."""

import json
from pathlib import Path

import pytest

from riskon.audit import AuditLogger, validate_audit_file
from riskon.models import QueryInput


def test_pipeline_writes_valid_jsonl_and_unique_trace(config, pipeline) -> None:
    result = pipeline.run(
        QueryInput(
            query="What is the direct rule for a delegated order giver?", trace_id="trace-audit"
        )
    )
    assert result.trace_id == "trace-audit"
    ok, message = validate_audit_file(config.audit.path)
    assert (ok, message) == (True, "audit schema valid")
    item = json.loads(config.audit.path.read_text(encoding="utf-8").splitlines()[0])
    assert set(item) == {
        "trace_id",
        "timestamp_utc",
        "query",
        "detected_context",
        "missing_context",
        "retrieved_sections",
        "evidence_refs",
        "decision",
        "reason_codes",
        "answer_confidence",
        "routing_confidence",
        "confidence_kind",
        "route",
    }
    assert all(ref.startswith("local://synthetic/") for ref in item["evidence_refs"])
    with pytest.raises(ValueError, match="Duplicate"):
        pipeline.audit_logger.append(QueryInput(query="same trace"), result)


def test_audit_validator_rejects_missing_or_malformed_files(tmp_path: Path) -> None:
    missing = validate_audit_file(tmp_path / "missing.jsonl")
    assert missing[0] is False
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{}\n", encoding="utf-8")
    assert validate_audit_file(bad)[0] is False
    logger = AuditLogger(tmp_path / "new.jsonl")
    assert logger._trace_ids() == set()
