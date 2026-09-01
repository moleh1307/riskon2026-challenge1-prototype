"""Deterministic aggregate metrics for the event evaluation suite."""

from __future__ import annotations

from statistics import median

from riskon.event_eval.models import EventCaseResult, EventEvaluationMetrics


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def compute_metrics(results: list[EventCaseResult]) -> EventEvaluationMetrics:
    """Aggregate the required event baseline fields from case results."""

    executed = len(results)
    latencies = [item.latency_ms for item in results]
    return EventEvaluationMetrics(
        cases_executed=executed,
        decision_match_count=sum(item.behavior_match for item in results),
        source_hit_at_1=sum(
            item.source_hit_rank is not None and item.source_hit_rank <= 1 for item in results
        ),
        source_hit_at_5=sum(
            item.source_hit_rank is not None and item.source_hit_rank <= 5 for item in results
        ),
        source_hit_at_10=sum(
            item.source_hit_rank is not None and item.source_hit_rank <= 10 for item in results
        ),
        citation_validity=_rate(sum(item.citation_valid for item in results), executed),
        clarification_match_count=sum(
            item.behavior_match and item.actual_decision == "CLARIFY" for item in results
        ),
        answer_count=sum(item.actual_decision == "ANSWER" for item in results),
        clarify_count=sum(item.actual_decision == "CLARIFY" for item in results),
        abstain_count=sum(item.actual_decision == "ABSTAIN" for item in results),
        routed_count=sum(item.route_present for item in results),
        table_required_count=sum(item.requires_table for item in results),
        image_required_count=sum(item.requires_image for item in results),
        unsupported_modality_count=sum(item.unsupported_modality_count for item in results),
        scope_violation_count=sum(item.scope_violation_count for item in results),
        critical_control_omission_count=sum(
            item.critical_control_omission_count for item in results
        ),
        broken_reference_count=sum(item.broken_reference_count for item in results),
        median_latency_ms=float(median(latencies)) if latencies else 0.0,
        runtime_error_count=sum(item.runtime_error is not None for item in results),
        manual_review_case_count=sum(item.requires_manual_review for item in results),
    )
