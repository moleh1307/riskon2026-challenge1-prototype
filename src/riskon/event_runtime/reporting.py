"""Safe event-runtime intake and query reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from riskon.event_intake.models import CorpusIntakeReport, CorpusIntakeRequest, PreparedCorpus
from riskon.event_intake.reporting import write_inspection_reports, write_prepared_corpus
from riskon.event_runtime.models import EventQueryPayload
from riskon.orchestra.models import OrchestraRun


def write_intake_artifacts(
    report: CorpusIntakeReport,
    prepared: PreparedCorpus | None,
    request: CorpusIntakeRequest,
    output_root: Path,
) -> None:
    """Persist only ER-A descriptor reports under the ignored runtime output."""

    write_inspection_reports(report, output_root)
    if prepared is not None:
        write_prepared_corpus(prepared, output_root)


def query_result_payload(run: OrchestraRun) -> dict[str, Any]:
    """Build a terminal-safe structured view without paths or raw markup."""

    result = run.final_verified_run.result
    expert_route = run.routed_run.expert_route if run.routed_run is not None else None
    route: Any = expert_route.model_dump(mode="json") if expert_route is not None else None
    if route is None and result.route is not None:
        route = result.route.model_dump(mode="json")
    payload = EventQueryPayload(
        decision=result.decision.value,
        answer=result.answer,
        clarification=result.clarifying_question,
        abstention_reason=[reason.value for reason in result.reason_codes],
        evidence_refs=list(
            dict.fromkeys(
                [*run.final_verified_run.verification.evidence_refs]
                + [item.source_ref for item in result.evidence]
            )
        ),
        route=route,
        activation_profile=run.activation_profile.value,
        worker_roles=list(run.investigation_plan.required_agent_roles),
        worker_execution_count=run.orchestra_metrics.worker_execution_count,
    )
    return payload.model_dump(mode="json")
