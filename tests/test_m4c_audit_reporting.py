"""M4C audit invariants and canonical report-artifact tests."""

import copy
import json
from pathlib import Path

import pytest
from m4c_helpers import case, context_for, m4c_config, planned

from riskon.audit import M4C_AUDIT_FIELDS, M4CAuditLogger, validate_m4c_audit_file
from riskon.evaluation import M4CEvaluator
from riskon.orchestra.counterfactual_runner import FrozenCounterfactualRunner
from riskon.pipeline import RiskonPipeline
from riskon.reporting import write_m4c_reports


def _run_case(tmp_path: Path, case_id: str):
    config = m4c_config(tmp_path)
    pipeline = RiskonPipeline.from_milestone4c_config(config)
    orchestrator = pipeline._m4c_orchestrator
    assert orchestrator is not None
    envelope = planned(case_id)
    baseline = envelope.planned_verified_run
    context = context_for(case(case_id), envelope).model_copy(
        update={"structured_context": orchestrator.planner.context_for(baseline)}
    )
    plan = orchestrator.planner.plan(
        baseline,
        context.structured_context,
        requested_variants=M4CEvaluator._requested_variants(case(case_id)),
    )
    runner = FrozenCounterfactualRunner(
        config.orchestra.m4c.fixture_catalog,
        config.orchestra.m4c.fixture_root,
    )
    run = pipeline.orchestrate_planned(
        baseline,
        context,
        "FULL_ORCHESTRA",
        counterfactual_plan=plan,
        counterfactual_runner=runner,
    )
    return config, run


def _valid_row(tmp_path: Path) -> dict[str, object]:
    document = M4CEvaluator(m4c_config(tmp_path)).run()
    path = tmp_path / "m4c" / "audit.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert document.audit_schema_valid is True
    assert len(rows) == 2
    return rows[1]


def _write_row(path: Path, row: object) -> Path:
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def test_m4c_audit_logger_writes_route_summary_and_rejects_duplicates(tmp_path: Path) -> None:
    config, run = _run_case(tmp_path / "run", "M4-036")
    path = tmp_path / "custom-audit.jsonl"
    logger = M4CAuditLogger(path)
    logger.append(run)
    ok, message = validate_m4c_audit_file(path)
    assert (ok, message) == (True, "M4C audit schema valid")
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert set(row) == M4C_AUDIT_FIELDS
    assert row["route_summary"]["route_mode"] == "FUNCTIONAL_QUEUE"
    with pytest.raises(ValueError, match="Duplicate M4C trace ID"):
        logger.append(run)
    assert config.security.network_enabled is False


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda row: row.pop("trace_id"), "fields mismatch"),
        (lambda row: row.__setitem__("baseline_trace_id", "other"), "baseline trace"),
        (lambda row: row.__setitem__("network_enabled", True), "network policy"),
        (
            lambda row: row.__setitem__("counterfactual_routing_execution_count", 1),
            "safety counter",
        ),
        (lambda row: row.__setitem__("risk_signals", "not-a-list"), "risk_signals"),
        (lambda row: row.__setitem__("task_count", -1), "count task_count"),
        (lambda row: row.__setitem__("route_summary", []), "route_summary"),
        (
            lambda row: row.__setitem__("route_summary", {"support_function": "https://unsafe"}),
            "Unsafe M4C",
        ),
    ],
)
def test_m4c_audit_validator_fails_closed_for_mutations(
    tmp_path: Path, mutator, message: str
) -> None:
    row = _valid_row(tmp_path / "source")
    mutated = copy.deepcopy(row)
    mutator(mutated)
    ok, detail = validate_m4c_audit_file(_write_row(tmp_path / "mutated.jsonl", mutated))
    assert ok is False
    assert message in detail


def test_m4c_audit_validator_rejects_duplicate_invalid_empty_and_missing_files(
    tmp_path: Path,
) -> None:
    row = _valid_row(tmp_path / "source")
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(
        json.dumps(row) + "\n" + json.dumps(row) + "\n",
        encoding="utf-8",
    )
    ok, message = validate_m4c_audit_file(duplicate)
    assert (ok, message) == (False, "Duplicate M4C trace ID at line 2: " + str(row["trace_id"]))

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text("{\n", encoding="utf-8")
    ok, message = validate_m4c_audit_file(invalid)
    assert ok is False and "Invalid M4C JSONL" in message

    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    assert validate_m4c_audit_file(empty) == (False, "M4C audit file contains no records")
    missing = validate_m4c_audit_file(tmp_path / "missing.jsonl")
    assert missing[0] is False and "not found" in missing[1]


@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("network_enabled", "network_enabled"),
        ("counterfactual_routing_enabled", "counterfactual routing"),
        ("recursive_orchestration_enabled", "recursive orchestration"),
        ("agent_to_agent_citation_enabled", "agent-to-agent"),
    ],
)
def test_m4c_audit_logger_rejects_unsafe_switches(tmp_path: Path, flag: str, message: str) -> None:
    _config, run = _run_case(tmp_path / flag, "M4-035")
    with pytest.raises(ValueError, match=message):
        M4CAuditLogger(tmp_path / f"{flag}.jsonl", **{flag: True}).append(run)


def test_m4c_reports_are_written_with_frozen_fixture_boundary(tmp_path: Path) -> None:
    config = m4c_config(tmp_path)
    document = M4CEvaluator(config).run()
    json_path, markdown_path = write_m4c_reports(document, config.orchestra.m4c.generated_root)
    assert json_path.is_file() and markdown_path.is_file()
    rendered = markdown_path.read_text(encoding="utf-8")
    assert "# M4C Evaluation Report" in rendered
    assert (
        "Canonical M4C evaluation uses frozen synthetic counterfactual PlannedVerifiedRun fixtures"
        in rendered
    )
    assert "A separate local run_planned adapter is implemented and tested" in rendered
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["metrics"]["counterfactual_variant_count"] == 4
