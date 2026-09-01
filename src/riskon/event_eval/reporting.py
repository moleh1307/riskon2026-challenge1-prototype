"""Safe report writers for the event evaluation boundary."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from riskon.event_eval.models import EventEvaluationDocument


def write_evaluation_reports(
    document: EventEvaluationDocument,
    output_root: Path,
) -> dict[str, Path]:
    """Write JSON, JSONL, CSV, and human-review reports under one output root."""

    output_root.mkdir(parents=True, exist_ok=True)
    evaluation_json = output_root / "evaluation.json"
    case_results_jsonl = output_root / "case_results.jsonl"
    failure_matrix_csv = output_root / "failure_matrix.csv"
    evaluation_md = output_root / "evaluation.md"
    manual_review_md = output_root / "manual_review.md"

    evaluation_json.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    case_results_jsonl.write_text(
        "".join(
            json.dumps(item.model_dump(mode="json"), sort_keys=True, ensure_ascii=False) + "\n"
            for item in document.case_results
        ),
        encoding="utf-8",
    )
    _write_failure_matrix(document, failure_matrix_csv)
    evaluation_md.write_text(_evaluation_markdown(document), encoding="utf-8")
    manual_review_md.write_text(_manual_review_markdown(document), encoding="utf-8")
    return {
        "evaluation": evaluation_json,
        "case_results": case_results_jsonl,
        "failure_matrix": failure_matrix_csv,
        "summary": evaluation_md,
        "manual_review": manual_review_md,
    }


def _write_failure_matrix(document: EventEvaluationDocument, path: Path) -> None:
    fields = (
        "case_id",
        "expected_behavior",
        "actual_decision",
        "behavior_match",
        "source_hit_rank",
        "route_present",
        "citation_valid",
        "failure_codes",
        "latency_ms",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in document.case_results:
            writer.writerow(
                {
                    "case_id": item.case_id,
                    "expected_behavior": item.expected_behavior.value,
                    "actual_decision": item.actual_decision or "RUNTIME_ERROR",
                    "behavior_match": item.behavior_match,
                    "source_hit_rank": item.source_hit_rank or "",
                    "route_present": item.route_present,
                    "citation_valid": item.citation_valid,
                    "failure_codes": "|".join(item.failure_codes),
                    "latency_ms": item.latency_ms,
                }
            )


def _evaluation_markdown(document: EventEvaluationDocument) -> str:
    metrics = document.metrics
    total = metrics.cases_executed
    return "\n".join(
        [
            "# RiskON event evaluation",
            "",
            "This is a local, deterministic baseline report over the 17 event questions.",
            "The event corpus and this report are kept outside the public repository.",
            "",
            "## Baseline metrics",
            "",
            f"- Cases executed: {metrics.cases_executed}/{total}",
            f"- Expected behavior match: {metrics.decision_match_count}/{total}",
            f"- Source hit@1: {metrics.source_hit_at_1}/{total}",
            f"- Source hit@5: {metrics.source_hit_at_5}/{total}",
            f"- Source hit@10: {metrics.source_hit_at_10}/{total}",
            f"- Citation validity: {metrics.citation_validity:.1%}",
            f"- Clarification matches: {metrics.clarification_match_count}/{total}",
            f"- Decisions: ANSWER={metrics.answer_count}, CLARIFY={metrics.clarify_count}, "
            f"ABSTAIN={metrics.abstain_count}",
            f"- Routed cases: {metrics.routed_count}/{total}",
            f"- Table-dependent cases: {metrics.table_required_count}",
            f"- Image-dependent cases: {metrics.image_required_count}",
            f"- Unsupported-modality cases: {metrics.unsupported_modality_count}",
            f"- Scope violations: {metrics.scope_violation_count}",
            f"- Critical-control omissions: {metrics.critical_control_omission_count}",
            f"- Broken references: {metrics.broken_reference_count}",
            f"- Runtime errors: {metrics.runtime_error_count}",
            f"- Median latency: {metrics.median_latency_ms:.1f} ms",
            "",
            "## Failure matrix",
            "",
            "| Case | Expected | Actual | Source rank | Failures |",
            "|---|---|---|---:|---|",
            *[
                f"| {item.case_id} | {item.expected_behavior.value} | "
                f"{item.actual_decision or 'RUNTIME_ERROR'} | "
                f"{item.source_hit_rank or '—'} | {', '.join(item.failure_codes)} |"
                for item in document.case_results
            ],
            "",
            "Manual factual, scope, table/image, and operational review is mandatory for every "
            "case; see `manual_review.md`.",
            "",
        ]
    )


def _manual_review_markdown(document: EventEvaluationDocument) -> str:
    sections = [
        "# RiskON event evaluation — manual review",
        "",
        "Every case below requires human review. The excerpts are intentionally short and are "
        "not a source export.",
        "",
    ]
    for item in document.case_results:
        excerpts = (
            [f"- {excerpt}" for excerpt in item.evidence_excerpts]
            if item.evidence_excerpts
            else ["- (none)"]
        )
        sections.extend(
            [
                f"## {item.case_id}",
                "",
                f"**Question:** {item.question}",
                f"**Expected behavior:** `{item.expected_behavior.value}`",
                f"**Actual decision:** `{item.actual_decision or 'RUNTIME_ERROR'}`",
                f"**Failure codes:** `{', '.join(item.failure_codes)}`",
                "",
                "**Answer / clarification:**",
                item.answer or item.clarifying_question or "(none)",
                "",
                "**Reason codes:** " + (", ".join(item.reason_codes) or "(none)"),
                "",
                "**Top source titles:** " + (", ".join(item.top_source_titles) or "(none)"),
                "",
                "**Short evidence excerpts:**",
                *excerpts,
                "",
                "- [ ] Factual correctness",
                "- [ ] Completeness",
                "- [ ] Relevance",
                "- [ ] Scope safety (jurisdiction / service model)",
                "- [ ] Critical-control safety",
                "- [ ] Citation actionability and operational next step",
                f"- [ ] Table interpretation (required: {item.requires_table})",
                f"- [ ] Image or process-graph interpretation (required: {item.requires_image})",
                "",
            ]
        )
    return "\n".join(sections)
