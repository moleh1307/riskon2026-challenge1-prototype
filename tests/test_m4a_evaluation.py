"""Evaluator and generated-artifact tests for M4A."""

import copy
import json
from pathlib import Path

import pytest

from riskon.audit import M4A_AUDIT_FIELDS, M4AAuditLogger, validate_m4a_audit_file
from riskon.config import load_milestone4a_config
from riskon.evaluation import M4AEvaluationDocument, M4AEvaluator
from riskon.models import PlannedVerifiedRun, RoutingContext
from riskon.orchestra.models import OrchestraContext, RiskSignal
from riskon.pipeline import RiskonPipeline
from riskon.reporting import write_m4a_reports

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"


def isolated_config(tmp_path: Path):
    """Build M4A with a temporary generated root."""

    config = load_milestone4a_config(PROJECT_ROOT / "config" / "milestone4a.toml")
    orchestra = config.orchestra.model_copy(update={"generated_root": tmp_path / "m4a"})
    return config.model_copy(update={"orchestra": orchestra})


def test_m4a_evaluator_matches_all_zero_worker_cases_and_regressions(tmp_path: Path) -> None:
    config = isolated_config(tmp_path)
    document = M4AEvaluator(config).run()
    assert document.metrics.m4a_case_match_rate == 1.0
    assert document.metrics.fast_path_accuracy == 1.0
    assert document.metrics.short_circuit_clarify_accuracy == 1.0
    assert document.metrics.human_first_accuracy == 1.0
    assert document.metrics.active_agent_count == 0
    assert document.metrics.worker_execution_count == 0
    assert document.metrics.baseline_mutation_count == 0
    assert document.metrics.network_violation_count == 0
    assert [item.id for item in document.scenario_results] == [
        "M4-029",
        "M4-033",
        "M4-034",
        "M4-039",
        "M4-040",
    ]
    assert all(item.matched for item in document.scenario_results)
    assert document.m0_regression == {"expected": 5, "matched": 5}
    assert document.m1_regression == {"expected": 7, "matched": 7}
    assert document.m2_regression == {"expected": 8, "matched": 8}
    assert document.m3_regression == {"expected": 8, "matched": 8}
    assert document.audit_schema_valid is True


def test_m4a_reports_and_audit_are_canonical_safe_artifacts(tmp_path: Path) -> None:
    config = isolated_config(tmp_path)
    document = M4AEvaluator(config).run()
    json_path, markdown_path = write_m4a_reports(document, config.orchestra.generated_root)
    audit_path = config.orchestra.generated_root / "audit.jsonl"
    assert json_path.is_file()
    assert markdown_path.is_file()
    assert audit_path.is_file()
    loaded = M4AEvaluationDocument.model_validate_json(json_path.read_text(encoding="utf-8"))
    assert loaded.model_dump(mode="json") == document.model_dump(mode="json")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "not an agent swarm" in markdown
    assert "DUAL_CHECK and FULL_ORCHESTRA are reserved for M4B" in markdown
    assert "active_agent_count" in markdown
    assert "worker_execution_count" in markdown

    audit_ok, message = validate_m4a_audit_file(audit_path)
    assert audit_ok is True
    assert message == "M4A audit schema valid"
    rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 5
    assert all(set(row) == M4A_AUDIT_FIELDS for row in rows)
    serialized = json.dumps(rows)
    assert '"query"' not in serialized
    assert "http://" not in serialized
    assert "https://" not in serialized
    assert "/Users/" not in serialized
    assert "@" not in serialized


def test_m4a_audit_validator_rejects_each_unsafe_shape(tmp_path: Path) -> None:
    config = isolated_config(tmp_path)
    M4AEvaluator(config).run()
    audit_path = config.orchestra.generated_root / "audit.jsonl"
    valid_row = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])

    missing = tmp_path / "missing-audit.jsonl"
    assert validate_m4a_audit_file(missing)[0] is False
    with_blank = tmp_path / "blank-audit.jsonl"
    with_blank.write_text("\n" + json.dumps(valid_row) + "\n", encoding="utf-8")
    assert validate_m4a_audit_file(with_blank)[0] is True

    cases: list[dict[str, object]] = []
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text("{not-json}\n", encoding="utf-8")
    assert validate_m4a_audit_file(malformed)[0] is False

    missing_field = copy.deepcopy(valid_row)
    missing_field.pop("trace_id")
    cases.append(missing_field)
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(
        json.dumps(valid_row) + "\n" + json.dumps(valid_row) + "\n", encoding="utf-8"
    )
    assert validate_m4a_audit_file(duplicate)[0] is False

    baseline_mismatch = copy.deepcopy(valid_row)
    baseline_mismatch["baseline_trace_id"] = "other"
    cases.append(baseline_mismatch)
    active_agents = copy.deepcopy(valid_row)
    active_agents["active_agent_count"] = 1
    cases.append(active_agents)
    worker_executions = copy.deepcopy(valid_row)
    worker_executions["worker_execution_count"] = 1
    cases.append(worker_executions)
    network_enabled = copy.deepcopy(valid_row)
    network_enabled["network_enabled"] = True
    cases.append(network_enabled)
    invalid_signals = copy.deepcopy(valid_row)
    invalid_signals["risk_signals"] = "APPROVAL_REQUIRED"
    cases.append(invalid_signals)
    invalid_route = copy.deepcopy(valid_row)
    invalid_route["route_summary"] = "not-a-route"
    cases.append(invalid_route)
    unsafe_route = copy.deepcopy(valid_row)
    unsafe_route["route_summary"] = {"support_function": "https://bad.invalid"}
    cases.append(unsafe_route)
    for index, row in enumerate(cases):
        candidate = tmp_path / f"invalid-{index}.jsonl"
        candidate.write_text(json.dumps(row) + "\n", encoding="utf-8")
        assert validate_m4a_audit_file(candidate)[0] is False


def test_m4a_audit_logger_rejects_duplicates_and_network(tmp_path: Path) -> None:
    config = isolated_config(tmp_path)
    pipeline = RiskonPipeline.from_milestone4a_config(config)
    raw = json.loads((M4_ROOT / "upstream_runs" / "M4-034.planned.json").read_text())
    planned = PlannedVerifiedRun.model_validate(raw["planned_verified_run"])
    result = planned.verified_run.result
    run = pipeline.orchestrate_planned(
        planned,
        OrchestraContext(
            risk_signals=(RiskSignal("UNRESOLVED_REQUIRED_REFERENCE"),),
            routing_context=RoutingContext(
                need_type=result.detected_context.need_type,
                reason_codes=list(result.reason_codes),
            ),
            routing_profile="default",
        ),
        "HUMAN_FIRST",
    )
    manual_path = tmp_path / "manual-audit.jsonl"
    logger = M4AAuditLogger(manual_path)
    logger.append(run)
    with pytest.raises(ValueError, match="Duplicate M4A trace ID"):
        logger.append(run)
    with pytest.raises(ValueError, match="network_enabled"):
        M4AAuditLogger(tmp_path / "network-audit.jsonl", network_enabled=True).append(run)
