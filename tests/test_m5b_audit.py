"""M5B compact audit output and safety validation."""

import json
from pathlib import Path

import pytest
from m5b_helpers import REFERENCE_TIME, config

from riskon.audit import M5B_AUDIT_FIELDS, validate_m5b_audit_file
from riskon.m5b_evaluation import M5BEvaluator


@pytest.fixture(scope="module")
def generated_audit() -> Path:
    M5BEvaluator(config()).run()
    return config().governance.generated_root / "audit.jsonl"


def test_generated_m5b_audit_has_exact_schema_and_five_rows(generated_audit: Path) -> None:
    ok, message = validate_m5b_audit_file(generated_audit)
    assert (ok, message) == (True, "M5B audit schema valid")
    rows = [json.loads(line) for line in generated_audit.read_text().splitlines()]
    assert len(rows) == 5
    assert all(set(row) == M5B_AUDIT_FIELDS for row in rows)
    assert all(row["timestamp_utc"] == REFERENCE_TIME.isoformat() for row in rows)


def test_m5b_audit_missing_file_is_reported(tmp_path: Path) -> None:
    assert validate_m5b_audit_file(tmp_path / "missing.jsonl")[0] is False


@pytest.mark.parametrize(
    "mutator,fragment",
    [
        (lambda row: {**row, "extra": True}, "fields mismatch"),
        (lambda row: {**row, "network_enabled": True}, "network policy"),
        (lambda row: {**row, "patch_status": "INVALID"}, "patch status"),
        (lambda row: {**row, "policy_ci_phase": "INVALID"}, "Policy CI phase"),
        (lambda row: {**row, "timestamp_utc": "not-a-time"}, "timestamp"),
        (lambda row: {**row, "active_patch_ids": "patch"}, "active_patch_ids"),
        (lambda row: {**row, "case_id": ""}, "case ID"),
        (lambda row: {**row, "case_id": "M5A-001", "active_patch_ids": ["https://x"]}, "Unsafe"),
    ],
)
def test_m5b_audit_rejects_schema_and_boundary_violations(
    tmp_path: Path, mutator, fragment: str
) -> None:
    row = {
        "case_id": "M5A-001",
        "timestamp_utc": REFERENCE_TIME.isoformat(),
        "patch_status": "ACTIVE",
        "policy_ci_phase": "ACTIVATION",
        "active_patch_ids": ["patch-1"],
        "excluded_patch_ids": [],
        "network_enabled": False,
    }
    path = tmp_path / "audit.jsonl"
    path.write_text(json.dumps(mutator(row)) + "\n", encoding="utf-8")
    ok, message = validate_m5b_audit_file(path)
    assert ok is False
    assert fragment in message


def test_m5b_audit_rejects_invalid_json_duplicate_and_empty_files(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text("not-json\n", encoding="utf-8")
    assert "Invalid JSONL" in validate_m5b_audit_file(invalid)[1]
    row = {
        "case_id": "M5A-001",
        "timestamp_utc": REFERENCE_TIME.isoformat(),
        "patch_status": "ACTIVE",
        "policy_ci_phase": "ACTIVATION",
        "active_patch_ids": [],
        "excluded_patch_ids": [],
        "network_enabled": False,
    }
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    assert "Duplicate" in validate_m5b_audit_file(duplicate)[1]
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    assert "no records" in validate_m5b_audit_file(empty)[1]
