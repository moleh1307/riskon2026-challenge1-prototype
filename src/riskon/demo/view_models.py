"""Convert runtime and evaluator contracts into safe ER-B view models."""

from __future__ import annotations

from typing import Any

from riskon.demo.models import (
    BeforeView,
    CounterfactualView,
    EvidenceView,
    GovernanceChecksView,
    GovernanceView,
    RouteView,
    StoryView,
    TraceStep,
)
from riskon.demo.sanitization import safe_scope, sanitize_excerpt, sanitize_reference, sanitize_text
from riskon.orchestra.models import OrchestraRun

GOVERNANCE_LIFECYCLE: tuple[str, ...] = (
    "Expert Resolution",
    "Proposed Patch",
    "Policy CI",
    "Human Approval",
    "Knowledge Release",
    "Active Overlay",
)


def story_view_from_run(
    run: OrchestraRun,
    *,
    case_id: str,
    source_case_id: str,
    story_kind: str,
    title: str,
    question: str,
    presentation_message: str,
    audit_reference: str,
    activation_profile: str | None = None,
    governance: GovernanceView | None = None,
    maximum_excerpt_characters: int = 280,
) -> StoryView:
    """Build a display-only story without exposing prompts or private reasoning."""

    result = run.final_verified_run.result
    context = result.detected_context.model_dump(mode="json")
    displayed_context = safe_scope(
        {
            key: value
            for key, value in context.items()
            if key not in {"missing_context"} and value is not None
        }
    )
    if result.detected_context.missing_context:
        displayed_context["missing_context"] = sanitize_text(
            ", ".join(result.detected_context.missing_context)
        )

    evidence = [
        _evidence_view(item, displayed_context, run, maximum_excerpt_characters)
        for item in result.evidence
    ]
    route = _route_view(run)
    if route is None and result.route is not None:
        route = RouteView(
            support_function=sanitize_text(result.route.support_function),
            route_mode="FUNCTIONAL_QUEUE",
            queue_id=None,
            selected_expert_id=sanitize_text(result.route.expert_id)
            if result.route.expert_id
            else None,
            routing_reason=sanitize_text(result.route.routing_reason),
            routing_confidence=result.route.routing_confidence,
            confidence_kind=sanitize_text(result.confidence_kind),
        )

    reason_codes = [reason.value for reason in result.reason_codes]
    abstention_reason = (
        ", ".join(sanitize_text(reason) for reason in reason_codes)
        if result.decision.value == "ABSTAIN"
        else None
    )
    return StoryView(
        case_id=sanitize_text(case_id),
        source_case_id=sanitize_text(source_case_id),
        story_kind=sanitize_text(story_kind),
        title=sanitize_text(title),
        question=sanitize_text(question),
        detected_context=displayed_context,
        decision=result.decision.value,
        reason_codes=[sanitize_text(reason.value) for reason in result.reason_codes],
        activation_profile=sanitize_text(activation_profile or run.activation_profile.value),
        runtime_activation_profile=run.activation_profile.value,
        answer=sanitize_text(result.answer) if result.answer else None,
        clarifying_question=(
            sanitize_text(result.clarifying_question) if result.clarifying_question else None
        ),
        abstention_reason=abstention_reason,
        evidence=evidence,
        why=sanitize_text(presentation_message),
        orchestra_activity=_trace_steps(run),
        counterfactuals=_counterfactual_views(run),
        open_material_objection_count=sum(
            objection.materiality == "MATERIAL" and objection.status == "OPEN"
            for objection in run.material_objections
        ),
        route=route,
        case_capsule_id=(sanitize_text(f"capsule-{source_case_id}") if run.case_capsule else None),
        governance=governance,
        audit_reference=sanitize_text(audit_reference),
    )


def governed_view(
    *,
    before: BeforeView,
    checks: GovernanceChecksView,
    after: dict[str, str],
    patch_status: str,
    active_release: str | None,
) -> GovernanceView:
    """Create the fixed M5B lifecycle panel from observed evaluator values."""

    return GovernanceView(
        before=before,
        lifecycle=list(GOVERNANCE_LIFECYCLE),
        checks=checks,
        after={key: sanitize_text(value) for key, value in after.items()},
        patch_status=sanitize_text(patch_status),
        active_release=sanitize_text(active_release) if active_release else None,
    )


def before_view_from_capsule(raw: dict[str, Any]) -> BeforeView:
    """Build the pre-patch panel from the frozen M5A capsule descriptor."""

    route = None
    if raw.get("support_function"):
        route = RouteView(
            support_function=sanitize_text(str(raw["support_function"])),
            route_mode=sanitize_text(str(raw.get("route_mode", "FUNCTIONAL_QUEUE"))),
            queue_id=sanitize_text(str(raw["queue_id"])) if raw.get("queue_id") else None,
            selected_expert_id=(
                sanitize_text(str(raw["selected_expert_id"]))
                if raw.get("selected_expert_id")
                else None
            ),
            routing_reason=sanitize_text(str(raw.get("routing_reason", "Synthetic route"))),
            routing_confidence=float(raw.get("routing_confidence", 0.0)),
            confidence_kind=sanitize_text(str(raw.get("confidence_kind", "SYNTHETIC_CONTRACT"))),
        )
    return BeforeView(
        decision=sanitize_text(str(raw["baseline_decision"])),
        reason_codes=[sanitize_text(str(value)) for value in raw.get("reason_codes", [])],
        route_present=route is not None,
        route=route,
    )


def _evidence_view(
    item: Any,
    scope: dict[str, str],
    run: OrchestraRun,
    maximum_excerpt_characters: int,
) -> EvidenceView:
    """Map one admitted evidence item to its redacted presentation form."""

    signals = {str(signal) for signal in run.risk_signals}
    criticality = (
        "CRITICAL_CONTROL"
        if "CRITICAL_CONTROL_RISK" in signals
        else "SCOPE_SENSITIVE"
        if "SCOPE_SENSITIVE" in signals or "SERVICE_MODEL_SENSITIVE" in signals
        else "STANDARD"
    )
    heading_path = getattr(item, "heading_path", [])
    return EvidenceView(
        source_title=sanitize_text(str(item.title)),
        section_heading=sanitize_text(" › ".join(str(value) for value in heading_path)),
        provenance_ref=sanitize_reference(str(item.source_ref)),
        scope=scope,
        criticality=criticality,
        excerpt=sanitize_excerpt(str(item.excerpt), maximum_excerpt_characters),
    )


def _route_view(run: OrchestraRun) -> RouteView | None:
    """Expose only functional route fields from a human-first case capsule."""

    capsule = run.case_capsule
    if capsule is None:
        return None
    return RouteView(
        support_function=sanitize_text(capsule.support_function),
        route_mode=capsule.route_mode.value,
        queue_id=sanitize_text(capsule.queue_id) if capsule.queue_id else None,
        selected_expert_id=(
            sanitize_text(capsule.selected_expert_id) if capsule.selected_expert_id else None
        ),
        routing_reason=sanitize_text(capsule.routing_reason),
        routing_confidence=capsule.routing_confidence,
        confidence_kind=sanitize_text(capsule.confidence_kind),
    )


def _counterfactual_views(run: OrchestraRun) -> list[CounterfactualView]:
    """Map local counterfactual results without exposing source text."""

    return [
        CounterfactualView(
            variant_id=sanitize_text(item.variant_id),
            dimension=sanitize_text(item.context_delta.dimension),
            before=(
                sanitize_text(item.context_delta.before)
                if item.context_delta.before is not None
                else None
            ),
            after=(
                sanitize_text(item.context_delta.after)
                if item.context_delta.after is not None
                else None
            ),
            decision=item.actual_decision.value,
            reason_codes=[reason.value for reason in item.actual_reason_codes],
            passed=item.passed,
        )
        for item in run.counterfactual_results
    ]


def _trace_steps(run: OrchestraRun) -> list[TraceStep]:
    """Create a bounded structured trace rather than a transcript."""

    steps: list[TraceStep] = [
        TraceStep(
            order=1,
            stage="Plan",
            actor="Risk-Adaptive Orchestra",
            detail=(
                f"Activation profile {run.activation_profile.value} selected from structured "
                "risk signals."
            ),
        )
    ]
    order = 2
    for task in run.agent_tasks:
        role = _display_role(task.agent_role)
        steps.append(
            TraceStep(
                order=order,
                stage="Worker activated",
                actor=role,
                detail="Bounded worker completed with structured output.",
            )
        )
        order += 1
    if run.findings:
        steps.append(
            TraceStep(
                order=order,
                stage="Evidence found",
                actor="Evidence Ledger",
                detail=f"{len(run.findings)} source-grounded finding(s) collected.",
            )
        )
        order += 1
    if run.material_objections:
        resolved = sum(item.status == "RESOLVED" for item in run.material_objections)
        open_count = sum(item.status == "OPEN" for item in run.material_objections)
        steps.append(
            TraceStep(
                order=order,
                stage="Objection raised/resolved",
                actor="Material-Objection Gate",
                detail=f"{resolved} resolved; {open_count} open material objection(s).",
            )
        )
        order += 1
    if run.counterfactual_results:
        passed = sum(item.passed for item in run.counterfactual_results)
        steps.append(
            TraceStep(
                order=order,
                stage="Counterfactual check",
                actor="Counterfactual Sentinel",
                detail=(
                    f"{passed}/{len(run.counterfactual_results)} context transition(s) passed."
                ),
            )
        )
        order += 1
    steps.extend(
        [
            TraceStep(
                order=order,
                stage="Verification",
                actor="Evidence Constitution",
                detail=(
                    f"Claims and scope checked; {len(run.final_verified_run.result.evidence)} "
                    "evidence item(s) admitted."
                ),
            ),
            TraceStep(
                order=order + 1,
                stage="Final decision",
                actor="RiskON Orchestra",
                detail=f"Decision released as {run.final_verified_run.result.decision.value}.",
            ),
        ]
    )
    return steps


def _display_role(role: str) -> str:
    """Render stable worker role labels without exposing task objectives."""

    return " ".join(word.title() for word in role.split("_"))
