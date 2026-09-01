"""Local JSONL audit logging and schema validation."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from riskon.governance.models import PatchStatus, PolicyCIPhase
from riskon.models import PipelineResult, QueryInput
from riskon.orchestra.models import OrchestraRun
from riskon.orchestra.runtime_audit import (  # noqa: F401
    M4D_FAILURE_AUDIT_FIELDS,
    M4D_SUCCESS_AUDIT_FIELDS,
    UnifiedRuntimeAuditLogger,
    query_hash,
    validate_m4d_audit_file,
)

AUDIT_FIELDS = {
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

M4A_AUDIT_FIELDS = {
    "trace_id",
    "timestamp_utc",
    "baseline_trace_id",
    "activation_profile",
    "risk_signals",
    "baseline_decision",
    "final_decision",
    "active_agent_count",
    "worker_execution_count",
    "route_summary",
    "case_capsule_id",
    "network_enabled",
}

M4B_AUDIT_FIELDS = {
    "trace_id",
    "timestamp_utc",
    "baseline_trace_id",
    "activation_profile",
    "risk_signals",
    "baseline_decision",
    "final_decision",
    "active_agent_count",
    "task_count",
    "discovery_task_count",
    "challenge_task_count",
    "worker_execution_count",
    "finding_count",
    "candidate_claim_count",
    "material_objection_count",
    "baseline_mutation_count",
    "agent_to_agent_citation_count",
    "recursive_delegation_count",
    "route_summary",
    "case_capsule_id",
    "network_enabled",
}

M4C_AUDIT_FIELDS = {
    "trace_id",
    "timestamp_utc",
    "baseline_trace_id",
    "activation_profile",
    "risk_signals",
    "baseline_decision",
    "final_decision",
    "task_count",
    "worker_execution_count",
    "counterfactual_count",
    "safe_transition_count",
    "scope_leak_count",
    "counterfactual_routing_execution_count",
    "recursive_orchestration_count",
    "agent_to_agent_citation_count",
    "baseline_mutation_count",
    "route_summary",
    "case_capsule_id",
    "network_enabled",
}

M5B_AUDIT_FIELDS = {
    "case_id",
    "timestamp_utc",
    "patch_status",
    "policy_ci_phase",
    "active_patch_ids",
    "excluded_patch_ids",
    "network_enabled",
}


class AuditLogger:
    """Append one trace per pipeline run and reject duplicate trace IDs."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, request: QueryInput, result: PipelineResult) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existing_ids = self._trace_ids()
        if result.trace_id in existing_ids:
            raise ValueError(f"Duplicate trace ID: {result.trace_id}")
        entry = {
            "trace_id": result.trace_id,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "query": request.query,
            "detected_context": result.detected_context.model_dump(mode="json"),
            "missing_context": result.missing_context,
            "retrieved_sections": [
                hit.model_dump(mode="json") for hit in result.retrieved_sections
            ],
            "evidence_refs": [item.source_ref for item in result.evidence],
            "decision": result.decision.value,
            "reason_codes": [reason.value for reason in result.reason_codes],
            "answer_confidence": result.answer_confidence,
            "routing_confidence": result.routing_confidence,
            "confidence_kind": result.confidence_kind,
            "route": result.route.model_dump(mode="json") if result.route else None,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def _trace_ids(self) -> set[str]:
        if not self.path.is_file():
            return set()
        ids: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                ids.add(str(item["trace_id"]))
        return ids


def validate_audit_file(path: Path) -> tuple[bool, str]:
    """Validate required fields, unique trace IDs, and local-only evidence refs."""

    if not path.is_file():
        return False, f"Audit file not found: {path}"
    trace_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as exc:
            return False, f"Invalid JSONL at line {line_number}: {exc}"
        if set(item) != AUDIT_FIELDS:
            return False, f"Audit fields mismatch at line {line_number}"
        trace_id = str(item["trace_id"])
        if trace_id in trace_ids:
            return False, f"Duplicate trace ID at line {line_number}: {trace_id}"
        trace_ids.add(trace_id)
        refs = item["evidence_refs"]
        if not isinstance(refs, list) or any(
            not isinstance(ref, str)
            or not (
                ref.startswith("local://synthetic/")
                or ref.startswith("local://synthetic-m1/")
                or ref.startswith("local://synthetic-m2/")
                or ref.startswith("local://synthetic-m3/")
            )
            for ref in refs
        ):
            return False, f"Non-local evidence reference at line {line_number}"
        if item["confidence_kind"] != "DETERMINISTIC_GATE_PLACEHOLDER":
            return False, f"Unexpected confidence kind at line {line_number}"
    return True, "audit schema valid"


class M4AAuditLogger:
    """Append the M4A structured audit contract without raw query content."""

    def __init__(self, path: Path, *, network_enabled: bool = False) -> None:
        self.path = path
        self.network_enabled = network_enabled

    def append(self, run: OrchestraRun) -> None:
        """Append one successful zero-worker orchestration trace."""

        if self.network_enabled:
            raise ValueError("M4A audit cannot be written with network_enabled = true")
        trace_id = run.final_verified_run.result.trace_id
        if trace_id in self._trace_ids():
            raise ValueError(f"Duplicate M4A trace ID: {trace_id}")
        route = run.case_capsule
        route_summary = None
        if route is not None:
            route_summary = {
                "support_function": route.support_function,
                "route_mode": route.route_mode.value,
                "selected_expert_id": route.selected_expert_id,
                "queue_id": route.queue_id,
                "routing_reason": route.routing_reason,
                "routing_confidence": route.routing_confidence,
                "confidence_kind": route.confidence_kind,
            }
        metrics = run.orchestra_metrics
        entry = {
            "trace_id": trace_id,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "baseline_trace_id": run.baseline_run.verified_run.result.trace_id,
            "activation_profile": run.activation_profile.value,
            "risk_signals": [str(signal) for signal in run.risk_signals],
            "baseline_decision": run.baseline_run.verified_run.result.decision.value,
            "final_decision": run.final_verified_run.result.decision.value,
            "active_agent_count": metrics.active_agent_count,
            "worker_execution_count": metrics.worker_execution_count,
            "route_summary": route_summary,
            "case_capsule_id": route.capsule_id if route is not None else None,
            "network_enabled": self.network_enabled,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def _trace_ids(self) -> set[str]:
        if not self.path.is_file():
            return set()
        ids: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                ids.add(str(item["trace_id"]))
        return ids


def _audit_strings_are_safe(value: Any) -> bool:
    """Reject URLs, absolute paths, and contact-like strings in M4A audit data."""

    if isinstance(value, str):
        return not any(token in value for token in ("http://", "https://", "/Users/", "@"))
    if isinstance(value, dict):
        return all(_audit_strings_are_safe(child) for child in value.values())
    if isinstance(value, list):
        return all(_audit_strings_are_safe(child) for child in value)
    return True


def validate_m4a_audit_file(path: Path) -> tuple[bool, str]:
    """Validate the exact M4A audit schema and its zero-worker invariants."""

    if not path.is_file():
        return False, f"M4A audit file not found: {path}"
    trace_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as exc:
            return False, f"Invalid M4A JSONL at line {line_number}: {exc}"
        if set(item) != M4A_AUDIT_FIELDS:
            return False, f"M4A audit fields mismatch at line {line_number}"
        trace_id = str(item["trace_id"])
        if trace_id in trace_ids:
            return False, f"Duplicate M4A trace ID at line {line_number}: {trace_id}"
        trace_ids.add(trace_id)
        if item["baseline_trace_id"] != trace_id:
            return False, f"M4A baseline trace mismatch at line {line_number}"
        if item["active_agent_count"] != 0 or item["worker_execution_count"] != 0:
            return False, f"M4A worker count is non-zero at line {line_number}"
        if item["network_enabled"] is not False:
            return False, f"M4A network policy violation at line {line_number}"
        if not isinstance(item["risk_signals"], list) or not all(
            isinstance(signal, str) for signal in item["risk_signals"]
        ):
            return False, f"M4A risk_signals are invalid at line {line_number}"
        route_summary = item["route_summary"]
        if route_summary is not None and not isinstance(route_summary, dict):
            return False, f"M4A route_summary is invalid at line {line_number}"
        if not _audit_strings_are_safe(item):
            return False, f"Unsafe M4A audit content at line {line_number}"
    return True, "M4A audit schema valid"


class M4BAuditLogger:
    """Append safe structured M4B execution traces without raw query content."""

    def __init__(
        self,
        path: Path,
        *,
        network_enabled: bool = False,
        agent_to_agent_citation_enabled: bool = False,
        recursive_delegation_enabled: bool = False,
    ) -> None:
        self.path = path
        self.network_enabled = network_enabled
        self.agent_to_agent_citation_enabled = agent_to_agent_citation_enabled
        self.recursive_delegation_enabled = recursive_delegation_enabled

    def append(self, run: OrchestraRun) -> None:
        """Append one successful bounded-worker trace."""

        if self.network_enabled:
            raise ValueError("M4B audit cannot be written with network_enabled = true")
        if self.agent_to_agent_citation_enabled:
            raise ValueError("M4B audit cannot allow agent-to-agent citations")
        if self.recursive_delegation_enabled:
            raise ValueError("M4B audit cannot allow recursive delegation")
        trace_id = run.final_verified_run.result.trace_id
        if trace_id in self._trace_ids():
            raise ValueError(f"Duplicate M4B trace ID: {trace_id}")
        route = run.case_capsule
        route_summary = None
        if route is not None:
            route_summary = {
                "support_function": route.support_function,
                "route_mode": route.route_mode.value,
                "selected_expert_id": route.selected_expert_id,
                "queue_id": route.queue_id,
                "routing_confidence": route.routing_confidence,
                "confidence_kind": route.confidence_kind,
            }
        metrics = run.orchestra_metrics
        entry = {
            "trace_id": trace_id,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "baseline_trace_id": run.baseline_run.verified_run.result.trace_id,
            "activation_profile": run.activation_profile.value,
            "risk_signals": [str(signal) for signal in run.risk_signals],
            "baseline_decision": run.baseline_run.verified_run.result.decision.value,
            "final_decision": run.final_verified_run.result.decision.value,
            "active_agent_count": metrics.active_agent_count,
            "task_count": metrics.task_count,
            "discovery_task_count": sum(
                task.execution_wave.value == "DISCOVERY" for task in run.agent_tasks
            ),
            "challenge_task_count": sum(
                task.execution_wave.value == "CHALLENGE" for task in run.agent_tasks
            ),
            "worker_execution_count": metrics.worker_execution_count,
            "finding_count": metrics.finding_count,
            "candidate_claim_count": metrics.candidate_claim_count,
            "material_objection_count": metrics.material_objection_count,
            "baseline_mutation_count": 0,
            "agent_to_agent_citation_count": 0,
            "recursive_delegation_count": 0,
            "route_summary": route_summary,
            "case_capsule_id": route.capsule_id if route is not None else None,
            "network_enabled": self.network_enabled,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def _trace_ids(self) -> set[str]:
        if not self.path.is_file():
            return set()
        ids: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                ids.add(str(item["trace_id"]))
        return ids


def validate_m4b_audit_file(path: Path) -> tuple[bool, str]:
    """Validate the exact M4B audit schema and safety counters."""

    if not path.is_file():
        return False, f"M4B audit file not found: {path}"
    trace_ids: set[str] = set()
    row_count = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as exc:
            return False, f"Invalid M4B JSONL at line {line_number}: {exc}"
        if set(item) != M4B_AUDIT_FIELDS:
            return False, f"M4B audit fields mismatch at line {line_number}"
        row_count += 1
        trace_id = str(item["trace_id"])
        if trace_id in trace_ids:
            return False, f"Duplicate M4B trace ID at line {line_number}: {trace_id}"
        trace_ids.add(trace_id)
        if item["baseline_trace_id"] != trace_id:
            return False, f"M4B baseline trace mismatch at line {line_number}"
        if item["network_enabled"] is not False:
            return False, f"M4B network policy violation at line {line_number}"
        if any(
            item[name] != 0
            for name in (
                "baseline_mutation_count",
                "agent_to_agent_citation_count",
                "recursive_delegation_count",
            )
        ):
            return False, f"M4B safety counter is non-zero at line {line_number}"
        if not isinstance(item["risk_signals"], list) or not all(
            isinstance(signal, str) for signal in item["risk_signals"]
        ):
            return False, f"M4B risk_signals are invalid at line {line_number}"
        route_summary = item["route_summary"]
        if route_summary is not None and not isinstance(route_summary, dict):
            return False, f"M4B route_summary is invalid at line {line_number}"
        if not _audit_strings_are_safe(item):
            return False, f"Unsafe M4B audit content at line {line_number}"
    if row_count == 0:
        return False, "M4B audit file contains no records"
    return True, "M4B audit schema valid"


class M4CAuditLogger:
    """Append safe structured M4C transition-adjudication traces."""

    def __init__(
        self,
        path: Path,
        *,
        network_enabled: bool = False,
        counterfactual_routing_enabled: bool = False,
        recursive_orchestration_enabled: bool = False,
        agent_to_agent_citation_enabled: bool = False,
    ) -> None:
        self.path = path
        self.network_enabled = network_enabled
        self.counterfactual_routing_enabled = counterfactual_routing_enabled
        self.recursive_orchestration_enabled = recursive_orchestration_enabled
        self.agent_to_agent_citation_enabled = agent_to_agent_citation_enabled

    def append(self, run: OrchestraRun) -> None:
        """Append one bounded counterfactual orchestration trace."""

        if self.network_enabled:
            raise ValueError("M4C audit cannot be written with network_enabled = true")
        if self.counterfactual_routing_enabled:
            raise ValueError("M4C audit cannot allow counterfactual routing")
        if self.recursive_orchestration_enabled:
            raise ValueError("M4C audit cannot allow recursive orchestration")
        if self.agent_to_agent_citation_enabled:
            raise ValueError("M4C audit cannot allow agent-to-agent citations")
        trace_id = run.final_verified_run.result.trace_id
        if trace_id in self._trace_ids():
            raise ValueError(f"Duplicate M4C trace ID: {trace_id}")
        route = run.case_capsule
        route_summary = None
        if route is not None:
            route_summary = {
                "support_function": route.support_function,
                "route_mode": route.route_mode.value,
                "selected_expert_id": route.selected_expert_id,
                "queue_id": route.queue_id,
                "routing_confidence": route.routing_confidence,
                "confidence_kind": route.confidence_kind,
            }
        counterfactual_count = len(run.counterfactual_results)
        safe_transition_count = sum(item.passed for item in run.counterfactual_results)
        scope_leak_count = sum(not item.passed for item in run.counterfactual_results)
        metrics = run.orchestra_metrics
        entry = {
            "trace_id": trace_id,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "baseline_trace_id": run.baseline_run.verified_run.result.trace_id,
            "activation_profile": run.activation_profile.value,
            "risk_signals": [str(signal) for signal in run.risk_signals],
            "baseline_decision": run.baseline_run.verified_run.result.decision.value,
            "final_decision": run.final_verified_run.result.decision.value,
            "task_count": metrics.task_count,
            "worker_execution_count": metrics.worker_execution_count,
            "counterfactual_count": counterfactual_count,
            "safe_transition_count": safe_transition_count,
            "scope_leak_count": scope_leak_count,
            "counterfactual_routing_execution_count": 0,
            "recursive_orchestration_count": 0,
            "agent_to_agent_citation_count": 0,
            "baseline_mutation_count": 0,
            "route_summary": route_summary,
            "case_capsule_id": route.capsule_id if route is not None else None,
            "network_enabled": self.network_enabled,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    def _trace_ids(self) -> set[str]:
        if not self.path.is_file():
            return set()
        ids: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                ids.add(str(item["trace_id"]))
        return ids


def validate_m4c_audit_file(path: Path) -> tuple[bool, str]:
    """Validate the exact M4C audit schema and fail-closed safety counters."""

    if not path.is_file():
        return False, f"M4C audit file not found: {path}"
    trace_ids: set[str] = set()
    row_count = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as exc:
            return False, f"Invalid M4C JSONL at line {line_number}: {exc}"
        if set(item) != M4C_AUDIT_FIELDS:
            return False, f"M4C audit fields mismatch at line {line_number}"
        row_count += 1
        trace_id = str(item["trace_id"])
        if trace_id in trace_ids:
            return False, f"Duplicate M4C trace ID at line {line_number}: {trace_id}"
        trace_ids.add(trace_id)
        if item["baseline_trace_id"] != trace_id:
            return False, f"M4C baseline trace mismatch at line {line_number}"
        if item["network_enabled"] is not False:
            return False, f"M4C network policy violation at line {line_number}"
        if any(
            item[name] != 0
            for name in (
                "counterfactual_routing_execution_count",
                "recursive_orchestration_count",
                "agent_to_agent_citation_count",
                "baseline_mutation_count",
            )
        ):
            return False, f"M4C safety counter is non-zero at line {line_number}"
        if not isinstance(item["risk_signals"], list) or not all(
            isinstance(signal, str) for signal in item["risk_signals"]
        ):
            return False, f"M4C risk_signals are invalid at line {line_number}"
        for name in (
            "task_count",
            "worker_execution_count",
            "counterfactual_count",
            "safe_transition_count",
            "scope_leak_count",
        ):
            if not isinstance(item[name], int) or item[name] < 0:
                return False, f"M4C count {name} is invalid at line {line_number}"
        route_summary = item["route_summary"]
        if route_summary is not None and not isinstance(route_summary, dict):
            return False, f"M4C route_summary is invalid at line {line_number}"
        if not _audit_strings_are_safe(item):
            return False, f"Unsafe M4C audit content at line {line_number}"
    if row_count == 0:
        return False, "M4C audit file contains no records"
    return True, "M4C audit schema valid"


def validate_m5b_audit_file(path: Path) -> tuple[bool, str]:
    """Validate the compact M5B governance audit and local-only boundary."""

    if not path.is_file():
        return False, f"M5B audit file not found: {path}"
    case_ids: set[str] = set()
    row_count = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as exc:
            return False, f"Invalid JSONL at line {line_number}: {exc}"
        if set(item) != M5B_AUDIT_FIELDS:
            return False, f"M5B audit fields mismatch at line {line_number}"
        row_count += 1
        case_id = item["case_id"]
        if not isinstance(case_id, str) or not case_id:
            return False, f"M5B case ID is invalid at line {line_number}"
        if case_id in case_ids:
            return False, f"Duplicate M5B case ID at line {line_number}: {case_id}"
        case_ids.add(case_id)
        try:
            datetime.fromisoformat(str(item["timestamp_utc"]).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return False, f"M5B timestamp is invalid at line {line_number}"
        if item["patch_status"] not in {status.value for status in PatchStatus}:
            return False, f"M5B patch status is invalid at line {line_number}"
        if item["policy_ci_phase"] not in {phase.value for phase in PolicyCIPhase}:
            return False, f"M5B Policy CI phase is invalid at line {line_number}"
        for name in ("active_patch_ids", "excluded_patch_ids"):
            values = item[name]
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                return False, f"M5B {name} is invalid at line {line_number}"
        if item["network_enabled"] is not False:
            return False, f"M5B network policy violation at line {line_number}"
        if not _audit_strings_are_safe(item):
            return False, f"Unsafe M5B audit content at line {line_number}"
    if row_count == 0:
        return False, "M5B audit file contains no records"
    return True, "M5B audit schema valid"
