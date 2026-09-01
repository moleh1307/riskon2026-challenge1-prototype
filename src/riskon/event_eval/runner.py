"""Execute the 17-case event evaluation against the unified runtime."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from riskon.event_eval.failure_taxonomy import classify_case
from riskon.event_eval.metrics import compute_metrics
from riskon.event_eval.models import (
    EventCaseResult,
    EventCaseSet,
    EventEvalCase,
    EventEvaluationDocument,
    EventExpectedBehavior,
)
from riskon.event_runtime.config import EventRuntimeConfig
from riskon.models import Decision, QueryInput
from riskon.orchestra.diagnostics import route_summary
from riskon.orchestra.errors import OrchestraFailClosedError
from riskon.orchestra.models import OrchestraRun
from riskon.pipeline import M4DRiskonPipeline, RiskonPipeline

_ABSOLUTE_PATH = re.compile(r"(?:/Users|/Volumes|/private/var|/tmp)/[^\s,;]+")


def load_event_cases(path: Path) -> EventCaseSet:
    """Load and validate exactly the 17 real event evaluation cases."""

    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Event evaluation cases not found: {resolved}")
    try:
        case_set = EventCaseSet.model_validate_json(resolved.read_text(encoding="utf-8"))
    except (OSError, ValidationError, json.JSONDecodeError) as exc:
        raise ValueError("Event evaluation cases do not match the expected schema") from exc
    if case_set.schema_version != "1.0":
        raise ValueError("Unsupported event evaluation case schema")
    if case_set.suite != "RISKON_CHALLENGE_1":
        raise ValueError("Unexpected event evaluation suite")
    if len(case_set.cases) != 17:
        raise ValueError(f"Event evaluation requires exactly 17 cases, got {len(case_set.cases)}")
    ids = [case.id for case in case_set.cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Event evaluation case IDs must be unique")
    return case_set


class EventEvaluationRunner:
    """Run deterministic retrieval and contract checks over the event corpus."""

    def __init__(self, event_config: EventRuntimeConfig) -> None:
        pipeline = RiskonPipeline.from_event_runtime_config(event_config)
        if not isinstance(pipeline, M4DRiskonPipeline):
            raise TypeError("Event runtime did not construct an M4D pipeline")
        self.pipeline = pipeline
        self.event_config = event_config

    def run(self, cases_path: Path) -> EventEvaluationDocument:
        """Execute all cases and return a safe machine-readable document."""

        case_set = load_event_cases(cases_path)
        results = [self._run_case(case) for case in case_set.cases]
        return EventEvaluationDocument(
            schema_version="1.0",
            suite=case_set.suite,
            metrics=compute_metrics(results),
            case_results=results,
            network_enabled=self.event_config.network_enabled,
            event_data_copied=self.event_config.event_data_copy_enabled,
        )

    def _run_case(self, case: EventEvalCase) -> EventCaseResult:
        started = time.perf_counter()
        try:
            run = self.pipeline.run_orchestrated(
                QueryInput(
                    query=case.question,
                    context=case.input_context,
                    trace_id=f"event-eval:{case.id}",
                )
            )
        except (OrchestraFailClosedError, ValueError, OSError, RuntimeError) as exc:
            result = EventCaseResult(
                case_id=case.id,
                question=case.question,
                expected_behavior=case.expected_behavior,
                requires_table=case.requires_table,
                requires_image=case.requires_image,
                requires_manual_review=case.requires_manual_review,
                expected_source_title_contains=list(case.expected_source_title_contains),
                citation_valid=False,
                latency_ms=_elapsed_ms(started),
                runtime_error=type(exc).__name__,
            )
            return result.model_copy(update={"failure_codes": classify_case(result)})
        result = self._result_for_run(case, run, _elapsed_ms(started))
        return result.model_copy(update={"failure_codes": classify_case(result)})

    def _result_for_run(
        self,
        case: EventEvalCase,
        run: OrchestraRun,
        latency_ms: float,
    ) -> EventCaseResult:
        final = run.final_verified_run
        pipeline_result = final.result
        actual_decision = pipeline_result.decision.value
        route = _safe_route(run)
        route_present = route is not None
        behavior_match = _behavior_matches(case.expected_behavior, actual_decision, route_present)
        retrieved_hits = list(pipeline_result.retrieved_sections)
        evidence_items = list(pipeline_result.evidence)
        titles = list(
            dict.fromkeys(
                [item.title for item in retrieved_hits]
                + ([] if retrieved_hits else [item.title for item in evidence_items])
            )
        )
        source_hit_rank = _source_hit_rank(titles, case.expected_source_title_contains)
        evidence_refs = list(
            dict.fromkeys(
                [
                    *final.verification.evidence_refs,
                    *(item.source_ref for item in pipeline_result.evidence),
                ]
            )
        )
        broken_reference_count = self._broken_reference_count(evidence_refs)
        invalid_references = [
            ref for ref in evidence_refs if not ref.startswith("local://event-wiki/")
        ]
        citation_valid = _citation_is_valid(
            actual_decision,
            bool(pipeline_result.evidence),
            invalid_references,
            broken_reference_count,
        )
        answer = _safe_clip(pipeline_result.answer, 4000)
        answer_lower = (answer or "").casefold()
        scope_violations = sum(
            phrase.casefold() in answer_lower for phrase in case.forbidden_answer_concepts
        )
        scope_violations += len(invalid_references)
        control_omissions = 0
        if answer is not None and case.required_answer_concepts:
            control_omissions = sum(
                concept.casefold() not in answer_lower for concept in case.required_answer_concepts
            )
        unsupported_modality = int(
            case.requires_image
            and (
                bool(final.verification.unsupported_modalities)
                or "UNSUPPORTED_MODALITY"
                in {reason.value for reason in pipeline_result.reason_codes}
            )
        )
        review_items = retrieved_hits if retrieved_hits else evidence_items
        excerpts = [
            f"{_safe_clip(item.title, 160)}: {_safe_clip(item.excerpt, 400)}"
            for item in review_items[:3]
        ]
        return EventCaseResult(
            case_id=case.id,
            question=case.question,
            expected_behavior=case.expected_behavior,
            requires_table=case.requires_table,
            requires_image=case.requires_image,
            requires_manual_review=case.requires_manual_review,
            actual_decision=actual_decision,
            route_present=route_present,
            behavior_match=behavior_match,
            expected_source_title_contains=list(case.expected_source_title_contains),
            top_source_titles=titles[:10],
            source_hit_rank=source_hit_rank,
            citation_valid=citation_valid,
            broken_reference_count=broken_reference_count,
            unsupported_modality_count=unsupported_modality,
            scope_violation_count=scope_violations,
            critical_control_omission_count=control_omissions,
            latency_ms=latency_ms,
            answer=answer,
            clarifying_question=_safe_clip(pipeline_result.clarifying_question, 1000),
            reason_codes=[reason.value for reason in pipeline_result.reason_codes],
            evidence_refs=evidence_refs,
            route=route,
            evidence_excerpts=excerpts,
        )

    def _broken_reference_count(self, references: list[str]) -> int:
        """Count only unresolved event-local evidence addresses."""

        corpus = self.pipeline._m4d_corpus
        if corpus is None:
            return len(references)
        return sum(corpus.resolve(reference) is None for reference in references)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _behavior_matches(expected: EventExpectedBehavior, actual: str, route: bool) -> bool:
    if expected is EventExpectedBehavior.ANSWER:
        return actual == Decision.ANSWER.value
    if expected is EventExpectedBehavior.CLARIFY:
        return actual == Decision.CLARIFY.value
    return actual == Decision.ABSTAIN.value and route


def _source_hit_rank(titles: list[str], expected: list[str]) -> int | None:
    if not expected:
        return None
    normalized_expected = [" ".join(value.casefold().split()) for value in expected]
    for rank, title in enumerate(titles, start=1):
        normalized_title = " ".join(title.casefold().split())
        if any(value in normalized_title for value in normalized_expected):
            return rank
    return None


def _citation_is_valid(
    actual_decision: str,
    has_evidence: bool,
    invalid_references: list[str],
    broken_reference_count: int,
) -> bool:
    if invalid_references or broken_reference_count:
        return False
    if actual_decision == Decision.ANSWER.value:
        return has_evidence
    return True


def _safe_route(run: OrchestraRun) -> dict[str, Any] | None:
    if run.case_capsule is not None:
        return route_summary(run)
    if run.routed_run is not None and run.routed_run.expert_route is not None:
        route = run.routed_run.expert_route
        return {
            "support_function": route.support_function,
            "route_mode": route.route_mode.value,
            "selected_expert_id": route.selected_expert_id,
            "queue_id": route.queue_id,
            "routing_confidence": route.routing_confidence,
            "confidence_kind": route.confidence_kind,
        }
    if run.final_verified_run.result.route is not None:
        return run.final_verified_run.result.route.model_dump(mode="json")
    return None


def _safe_clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    cleaned = _ABSOLUTE_PATH.sub("[path]", cleaned)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"
