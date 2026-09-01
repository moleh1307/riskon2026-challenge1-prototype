"""Safe diagnostic helpers for the M4D runtime."""

from __future__ import annotations

from collections.abc import Iterable

from riskon.orchestra.models import RuntimeDiagnostics
from riskon.orchestra.source_safety import SourceSafetyReport


def build_runtime_diagnostics(
    source_safety: SourceSafetyReport,
    *,
    run_planned_call_count: int = 1,
    failure_stage: str | None = None,
    failed_task_ids: Iterable[str] = (),
    cause_types: Iterable[str] = (),
    fallback_action: str | None = None,
) -> RuntimeDiagnostics:
    """Build a source-safe, deterministic diagnostic record."""

    return RuntimeDiagnostics(
        run_planned_call_count=run_planned_call_count,
        source_safety_diagnostic_codes=tuple(
            sorted({item.diagnostic_code for item in source_safety.diagnostics})
        ),
        failure_stage=failure_stage,
        failed_task_ids=tuple(sorted(set(failed_task_ids))),
        cause_types=tuple(sorted(set(cause_types))),
        fallback_action=fallback_action,
    )


def safe_failure_payload(diagnostics: RuntimeDiagnostics) -> dict[str, object]:
    """Return only structured failure fields suitable for an audit row."""

    return {
        "failed_stage": diagnostics.failure_stage,
        "failed_task_ids": list(diagnostics.failed_task_ids),
        "cause_types": list(diagnostics.cause_types),
        "fallback_action": diagnostics.fallback_action,
    }
