"""Deterministic structured explanations for M3 routing decisions."""

from riskon.models import (
    RouteMode,
    RoutingAlternative,
    RoutingCandidateDiagnostic,
    RoutingExclusion,
    RoutingExplanation,
    RoutingRequest,
)


def build_explanation(
    request: RoutingRequest,
    support_function: str,
    candidates: list[RoutingCandidateDiagnostic],
    *,
    route_mode: RouteMode,
    fallback_reason: str | None,
) -> RoutingExplanation:
    """Build a schema-validated explanation without an LLM or raw query text."""

    eligible = sorted(
        [item for item in candidates if item.eligible],
        key=lambda item: item.rank or 10**9,
    )
    top = eligible[0] if eligible else None
    selected_factors = dict(top.component_scores) if top is not None else {}
    alternatives: list[RoutingAlternative] = []
    for item in eligible[1:]:
        alternatives.append(
            RoutingAlternative(
                expert_id=item.expert_id,
                rank=item.rank or 0,
                total_score=item.total_score or 0.0,
                reason=(
                    "Lower deterministic total score"
                    if top is not None and item.total_score != top.total_score
                    else "Deterministic expert-id tie-break"
                ),
            )
        )
    excluded = [
        RoutingExclusion(expert_id=item.expert_id, reason=item.exclusion_reason or "EXCLUDED")
        for item in candidates
        if not item.eligible and item.exclusion_reason is not None
    ]
    decisive_factors = [
        "support_function_selection",
        "mandate_match",
        "context_match",
        "strongest_two_score_components",
        "alternative_candidate_reason",
    ]
    if "network_proximity" in selected_factors:
        decisive_factors.append("network_proximity")
    if route_mode is RouteMode.FUNCTIONAL_QUEUE:
        decisive_factors = [
            "support_function_selection",
            "hard_gate_result",
            "low_score_or_margin",
            "functional_queue_selection",
        ]
    return RoutingExplanation(
        function_reason=(
            "Versioned support model selected the function from structured need and reason fields."
        ),
        hard_constraints_applied=[
            "active",
            "effective_window",
            "support_function_exact",
            "mandate",
            "jurisdiction",
            "region",
            "system",
            "accepting_new_cases",
        ],
        selected_candidate_factors=selected_factors,
        alternative_candidates=alternatives,
        excluded_candidates=excluded,
        fallback_reason=fallback_reason,
        decisive_factors=decisive_factors,
    )
