"""Audit writer and validator for the M4D unified runtime."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from riskon.models import QueryInput
from riskon.orchestra.diagnostics import route_summary
from riskon.orchestra.models import OrchestraRun, RiskAssessment

M4D_SUCCESS_AUDIT_FIELDS = {
    "trace_id",
    "timestamp_utc",
    "query_hash",
    "baseline_trace_id",
    "baseline_decision",
    "risk_signals",
    "signal_sources",
    "activation_profile",
    "agent_roles",
    "task_count",
    "counterfactual_count",
    "final_decision",
    "route_summary",
    "case_capsule_id",
    "network_enabled",
}

M4D_FAILURE_AUDIT_FIELDS = {
    "trace_id",
    "timestamp_utc",
    "baseline_trace_id",
    "baseline_decision",
    "activation_profile",
    "failed_stage",
    "failed_task_ids",
    "cause_types",
    "fallback_action",
    "answer_returned",
    "route_returned",
    "network_enabled",
}


def query_hash(query: str) -> str:
    """Hash query identity without retaining raw query text."""

    return hashlib.sha256(query.encode("utf-8")).hexdigest()


class UnifiedRuntimeAuditLogger:
    """Append-only local audit sink with separate success and failure schemas."""

    def __init__(self, path: Path, *, network_enabled: bool = False) -> None:
        self.path = path
        self.network_enabled = network_enabled

    def append(
        self,
        run: OrchestraRun,
        request: QueryInput | None = None,
        assessment: RiskAssessment | None = None,
    ) -> None:
        """Append a successful run; this method also satisfies legacy audit protocols."""

        self.append_success(run, request=request, assessment=assessment)

    def append_success(
        self,
        run: OrchestraRun,
        *,
        request: QueryInput | None = None,
        assessment: RiskAssessment | None = None,
    ) -> None:
        """Write one safe success row."""

        self._validate_network()
        trace_id = run.final_verified_run.result.trace_id
        self._reject_duplicate(trace_id)
        baseline = run.baseline_run.verified_run.result
        query = request.query if request is not None else run.baseline_run.query_plan.original_query
        chosen = assessment or run.risk_assessment
        signal_sources = chosen.signal_sources if chosen is not None else {}
        entry = {
            "trace_id": trace_id,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "query_hash": query_hash(query),
            "baseline_trace_id": baseline.trace_id,
            "baseline_decision": baseline.decision.value,
            "risk_signals": [str(signal) for signal in run.risk_signals],
            "signal_sources": {
                str(key): list(value) for key, value in sorted(signal_sources.items())
            },
            "activation_profile": run.activation_profile.value,
            "agent_roles": list(run.investigation_plan.required_agent_roles),
            "task_count": run.orchestra_metrics.task_count,
            "counterfactual_count": run.orchestra_metrics.counterfactual_count,
            "final_decision": run.final_verified_run.result.decision.value,
            "route_summary": route_summary(run),
            "case_capsule_id": run.case_capsule.capsule_id if run.case_capsule else None,
            "network_enabled": self.network_enabled,
        }
        self._append(entry)

    def append_failure(
        self,
        *,
        trace_id: str,
        baseline_trace_id: str,
        baseline_decision: str,
        activation_profile: str,
        failed_stage: str,
        failed_task_ids: list[str],
        cause_types: list[str],
        fallback_action: str,
        answer_returned: bool = False,
        route_returned: bool = False,
    ) -> None:
        """Write one failure row without an answer, route, or raw query."""

        self._validate_network()
        self._reject_duplicate(trace_id)
        self._append(
            {
                "trace_id": trace_id,
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "baseline_trace_id": baseline_trace_id,
                "baseline_decision": baseline_decision,
                "activation_profile": activation_profile,
                "failed_stage": failed_stage,
                "failed_task_ids": sorted(set(failed_task_ids)),
                "cause_types": sorted(set(cause_types)),
                "fallback_action": fallback_action,
                "answer_returned": answer_returned,
                "route_returned": route_returned,
                "network_enabled": self.network_enabled,
            }
        )

    def _validate_network(self) -> None:
        if self.network_enabled:
            raise ValueError("M4D audit cannot be written with network_enabled = true")

    def _reject_duplicate(self, trace_id: str) -> None:
        if trace_id in self._trace_ids():
            raise ValueError(f"Duplicate M4D trace ID: {trace_id}")

    def _trace_ids(self) -> set[str]:
        if not self.path.is_file():
            return set()
        return {
            str(item["trace_id"])
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
            for item in [json.loads(line)]
        }

    def _append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not _audit_strings_are_safe(entry):
            raise ValueError("M4D audit contains unsafe content")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _audit_strings_are_safe(value: Any) -> bool:
    if isinstance(value, str):
        return not any(token in value for token in ("http://", "https://", "/Users/", "@"))
    if isinstance(value, dict):
        return all(_audit_strings_are_safe(child) for child in value.values())
    if isinstance(value, list):
        return all(_audit_strings_are_safe(child) for child in value)
    return True


def validate_m4d_audit_file(path: Path) -> tuple[bool, str]:
    """Validate mixed success/failure rows and all M4D safety invariants."""

    if not path.is_file():
        return False, f"M4D audit file not found: {path}"
    trace_ids: set[str] = set()
    records = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        records += 1
        try:
            item: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError as exc:
            return False, f"Invalid M4D JSONL at line {line_number}: {exc}"
        fields = set(item)
        if fields not in (M4D_SUCCESS_AUDIT_FIELDS, M4D_FAILURE_AUDIT_FIELDS):
            return False, f"M4D audit fields mismatch at line {line_number}"
        trace_id = str(item.get("trace_id", ""))
        if not trace_id or trace_id in trace_ids:
            return False, f"Duplicate M4D trace ID at line {line_number}: {trace_id}"
        trace_ids.add(trace_id)
        if item.get("network_enabled") is not False:
            return False, f"M4D network policy violation at line {line_number}"
        if fields == M4D_SUCCESS_AUDIT_FIELDS:
            digest = item.get("query_hash")
            if not isinstance(digest, str) or len(digest) != 64:
                return False, f"M4D query hash is invalid at line {line_number}"
            if not isinstance(item.get("signal_sources"), dict):
                return False, f"M4D signal sources are invalid at line {line_number}"
        else:
            if item.get("answer_returned") is not False:
                return False, f"M4D failure row returned an answer at line {line_number}"
            if item.get("baseline_decision") == "ANSWER" and (
                item.get("route_returned") is not False
            ):
                return False, f"M4D ANSWER failure returned a route at line {line_number}"
        if not _audit_strings_are_safe(item):
            return False, f"Unsafe M4D audit content at line {line_number}"
    if records == 0:
        return False, "M4D audit file contains no records"
    return True, "M4D audit schema valid"
