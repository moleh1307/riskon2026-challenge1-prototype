"""Small deterministic failure taxonomy for event evaluation reports."""

from __future__ import annotations

from riskon.event_eval.models import EventCaseResult, EventExpectedBehavior


def classify_case(result: EventCaseResult) -> list[str]:
    """Return stable failure codes without using an LLM grader."""

    failures: list[str] = []
    if result.runtime_error is not None:
        failures.append("RUNTIME_ERROR")
        return failures
    if not result.behavior_match:
        failures.append("DECISION_MISMATCH")
    if result.expected_source_title_contains and result.source_hit_rank is None:
        failures.append("NO_SOURCE_HIT")
    elif result.source_hit_rank is not None and result.source_hit_rank > 10:
        failures.append("SOURCE_HIT_AFTER_10")
    if result.expected_behavior is EventExpectedBehavior.ABSTAIN_ROUTE and not result.route_present:
        failures.append("NO_ROUTE")
    if result.expected_behavior is not EventExpectedBehavior.ABSTAIN_ROUTE and result.route_present:
        failures.append("UNEXPECTED_ROUTE")
    if not result.citation_valid:
        failures.append("CITATION_INVALID")
    if result.broken_reference_count:
        failures.append("BROKEN_REFERENCE")
    if result.unsupported_modality_count:
        failures.append("UNSUPPORTED_MODALITY")
    if result.scope_violation_count:
        failures.append("SCOPE_VIOLATION")
    if result.critical_control_omission_count:
        failures.append("CRITICAL_CONTROL_OMISSION")
    if (
        result.expected_behavior is EventExpectedBehavior.CLARIFY
        and result.actual_decision == EventExpectedBehavior.CLARIFY
        and not result.clarifying_question
    ):
        failures.append("CLARIFICATION_MISSING")
    return failures or ["PASS"]
