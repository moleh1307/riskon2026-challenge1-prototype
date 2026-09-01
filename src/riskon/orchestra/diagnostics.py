"""Safe deterministic serializers for M4B worker artifacts."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from riskon.orchestra.models import OrchestraRun


def write_model_jsonl(path: Path, records: Iterable[BaseModel]) -> Path:
    """Write validated worker records as one deterministic JSON object per line."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record.model_dump(mode="json"), sort_keys=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def route_summary(run: OrchestraRun) -> dict[str, Any] | None:
    """Return only safe structured route fields for reports and audit views."""

    capsule = run.case_capsule
    if capsule is None:
        return None
    return {
        "support_function": capsule.support_function,
        "route_mode": capsule.route_mode.value,
        "selected_expert_id": capsule.selected_expert_id,
        "queue_id": capsule.queue_id,
        "routing_confidence": capsule.routing_confidence,
        "confidence_kind": capsule.confidence_kind,
    }


def run_safe_summary(run: OrchestraRun) -> dict[str, Any]:
    """Return a report-safe orchestration summary without query or source text."""

    metrics = run.orchestra_metrics
    return {
        "baseline_trace_id": run.baseline_run.verified_run.result.trace_id,
        "activation_profile": run.activation_profile.value,
        "risk_signals": [str(signal) for signal in run.risk_signals],
        "task_count": len(run.agent_tasks),
        "finding_count": len(run.findings),
        "candidate_claim_ids": [claim.claim_id for claim in run.candidate_claims],
        "material_objection_count": len(run.material_objections),
        "open_material_objection_count": sum(
            objection.materiality == "MATERIAL" and objection.status == "OPEN"
            for objection in run.material_objections
        ),
        "worker_execution_count": metrics.worker_execution_count,
        "final_decision": run.final_verified_run.result.decision.value,
        "final_reason_codes": [
            reason.value for reason in run.final_verified_run.result.reason_codes
        ],
        "final_evidence_refs": list(run.final_verified_run.verification.evidence_refs),
        "route": route_summary(run),
        "case_capsule_id": run.case_capsule.capsule_id if run.case_capsule else None,
    }
