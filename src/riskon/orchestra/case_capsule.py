"""Structured human-first case-capsule construction."""

from riskon.models import PlannedVerifiedRun, RoutedRun
from riskon.orchestra.models import CaseCapsule


def _local_evidence_refs(planned: PlannedVerifiedRun) -> list[str]:
    """Collect deduplicated local references without copying source text."""

    result = planned.verified_run.result
    refs = list(planned.verified_run.verification.evidence_refs)
    refs.extend(item.source_ref for item in result.evidence)
    refs.extend(item.source_ref for item in result.retrieved_sections)
    return list(dict.fromkeys(refs))


def build_case_capsule(
    baseline_run: PlannedVerifiedRun,
    routed_run: RoutedRun,
    *,
    namespace: str = "m4a",
) -> CaseCapsule:
    """Build a deterministic capsule from structured baseline and route state."""

    route = routed_run.expert_route
    if route is None:
        raise ValueError("A case capsule requires an expert route")
    result = baseline_run.verified_run.result
    legacy_route = result.route
    routing_reason = (
        legacy_route.routing_reason
        if legacy_route is not None
        else route.explanation.fallback_reason or "M3_STRUCTURED_ROUTE"
    )
    return CaseCapsule(
        capsule_id=f"{namespace}-capsule-{result.trace_id}",
        baseline_trace_id=result.trace_id,
        baseline_decision=result.decision,
        reason_codes=list(result.reason_codes),
        detected_context=result.detected_context.model_copy(deep=True),
        missing_context=list(result.missing_context),
        evidence_refs=_local_evidence_refs(baseline_run),
        verification_status=baseline_run.verified_run.verification.status,
        support_function=route.support_function,
        route_mode=route.route_mode,
        selected_expert_id=route.selected_expert_id,
        queue_id=route.queue_id,
        routing_reason=routing_reason,
        routing_confidence=route.routing_confidence,
        confidence_kind=route.confidence_kind,
    )
