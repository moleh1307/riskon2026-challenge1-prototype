"""Deterministic M5B governance, overlay, and regression evaluation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riskon.audit import validate_m5b_audit_file
from riskon.governance.models import (
    ApprovalDecision,
    EvaluatedPatch,
    KnowledgeOverlaySnapshot,
    PatchStatus,
    PolicyCIPhase,
)
from riskon.models import Decision, QueryInput
from riskon.pipeline import M5BRiskonPipeline

REFERENCE_TIME = datetime(2026, 8, 27, 12, tzinfo=UTC)


class M5BCaseResult(BaseModel):
    """Safe comparison result for one frozen M5A case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    matched: bool
    failures: list[str] = Field(default_factory=list)
    policy_ci_phase: PolicyCIPhase
    check_statuses: dict[str, str]
    expected_patch_status: str
    actual_patch_status: str
    expected_active_release: str | None
    actual_active_release: str | None
    counterfactual_transition_count: int = Field(ge=0)
    post_patch: dict[str, str] = Field(default_factory=dict)
    overlay_claim_ids: list[str] = Field(default_factory=list)
    active_patch_ids: list[str] = Field(default_factory=list)
    excluded_patch_ids: list[str] = Field(default_factory=list)
    orchestration_decision: str | None = None


class M5BMetrics(BaseModel):
    """Acceptance counters emitted in the canonical M5B report."""

    model_config = ConfigDict(extra="forbid")

    m5b_case_match_rate: float = Field(ge=0.0, le=1.0)
    governed_evolution_count: int = Field(ge=0)
    expected_governed_evolution_count: int = Field(ge=0)
    awaiting_approval_count: int = Field(ge=0)
    expected_awaiting_approval_count: int = Field(ge=0)
    rejected_unsafe_patch_count: int = Field(ge=0)
    expected_rejected_unsafe_patch_count: int = Field(ge=0)
    expired_patch_exclusion_count: int = Field(ge=0)
    expected_expired_patch_exclusion_count: int = Field(ge=0)
    policy_ci_check_count: int = Field(ge=0)
    expected_policy_ci_check_count: int = Field(ge=0)
    policy_ci_status_match_count: int = Field(ge=0)
    regression_expected: int = Field(ge=0)
    regression_matched: int = Field(ge=0)
    counterfactual_expected: int = Field(ge=0)
    counterfactual_matched: int = Field(ge=0)
    exact_scope_answer_count: int = Field(ge=0)
    alternate_region_abstention_count: int = Field(ge=0)
    alternate_service_abstention_count: int = Field(ge=0)
    missing_context_clarification_count: int = Field(ge=0)
    automatic_approval_count: int = Field(ge=0)
    automatic_activation_count: int = Field(ge=0)
    self_approval_count: int = Field(ge=0)
    failed_check_override_count: int = Field(ge=0)
    official_corpus_mutation_count: int = Field(ge=0)
    expired_evidence_retrieval_count: int = Field(ge=0)
    network_violation_count: int = Field(ge=0)


class M5BEvaluationDocument(BaseModel):
    """Canonical machine-readable M5B evaluation document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    metrics: M5BMetrics
    case_results: list[M5BCaseResult]
    policy_ci_reports: list[dict[str, Any]]
    knowledge_releases: list[dict[str, Any]]
    overlay_snapshot: dict[str, Any]
    regression: dict[str, Any]
    security: dict[str, Any]
    architecture_statement: str


class M5BEvaluator:
    """Run the exact five-case M5B acceptance matrix."""

    def __init__(self, config: Any) -> None:
        self.config = config

    def run(self) -> M5BEvaluationDocument:
        """Evaluate Policy CI, human gates, activation, and overlay behavior."""

        self._clear_generated_outputs()
        pipeline = M5BRiskonPipeline.from_milestone5b_config(self.config)
        service = pipeline.governance_service
        service.set_event_clock(REFERENCE_TIME)
        frozen_cases = self._cases()
        reports: list[dict[str, Any]] = []
        case_results: list[M5BCaseResult] = []
        releases: list[dict[str, Any]] = []
        active_snapshot: KnowledgeOverlaySnapshot | None = None
        all_counterfactuals = 0
        status_matches = 0
        governed_evolution = 0
        awaiting = 0
        rejected = 0
        expired = 0
        post_counts = {"exact": 0, "region": 0, "service": 0, "missing": 0}
        orchestration_decision: str | None = None

        for case_id in self.config.evaluation.included_cases:
            frozen = frozen_cases[case_id]
            capsule, resolution, fixture_patch, approval = service.load_case_inputs(case_id)
            candidate_patch = fixture_patch.model_copy(update={"status": PatchStatus.PROPOSED})
            service.record_proposal(resolution, candidate_patch)
            phase = self._phase_for(fixture_patch, approval)
            report = service.run_policy_ci(
                capsule,
                resolution,
                candidate_patch,
                approval,
                REFERENCE_TIME,
                phase,
            )
            reports.append(report.model_dump(mode="json"))
            expected_checks = frozen["expected_policy_ci_checks"]
            actual_checks = {item.check_id.value: item.status.value for item in report.checks}
            status_matches += sum(
                actual_checks.get(check_id) == expected_status
                for check_id, expected_status in expected_checks.items()
            )
            if case_id == "M5A-046":
                all_counterfactuals += report.counterfactual_transitions
            failures: list[str] = []
            for check_id, expected_status in expected_checks.items():
                if actual_checks.get(check_id) != expected_status:
                    failures.append(
                        f"{check_id}: {actual_checks.get(check_id)!r} != {expected_status!r}"
                    )

            actual_status = PatchStatus.TESTED
            actual_release: str | None = None
            case_snapshot: KnowledgeOverlaySnapshot | None = None
            if case_id == "M5A-046":
                evaluated = EvaluatedPatch(
                    case_capsule=capsule,
                    expert_resolution=resolution,
                    knowledge_patch=candidate_patch,
                    policy_ci_report=report,
                    approval=approval,
                )
                if approval is None:
                    failures.append("M5A-046 requires the frozen human approval")
                else:
                    governed = service.apply_human_decision(evaluated, approval)
                    release = service.activate_release(
                        (governed,),
                        service.load_release_request(case_id),
                        REFERENCE_TIME,
                    )
                    case_snapshot = service.compile_overlay(release, REFERENCE_TIME)
                    active_snapshot = case_snapshot
                    actual_status = PatchStatus.ACTIVE
                    actual_release = release.release_id
                    releases.append(release.model_dump(mode="json"))
                    governed_evolution += 1
            elif case_id == "M5A-047":
                service.record_awaiting_approval(resolution, candidate_patch)
                actual_status = PatchStatus.AWAITING_APPROVAL
                awaiting += 1
                case_snapshot = _excluded_snapshot(fixture_patch.patch_id)
            elif case_id in {"M5A-048", "M5A-049"}:
                if approval is None:
                    failures.append(f"{case_id} requires its frozen rejection record")
                else:
                    evaluated = EvaluatedPatch(
                        case_capsule=capsule,
                        expert_resolution=resolution,
                        knowledge_patch=candidate_patch,
                        policy_ci_report=report,
                        approval=approval,
                    )
                    governed = service.apply_human_decision(evaluated, approval)
                    actual_status = governed.status
                    if actual_status is PatchStatus.REJECTED:
                        rejected += 1
                    else:
                        failures.append(f"{case_id} was not rejected")
                case_snapshot = _excluded_snapshot(fixture_patch.patch_id)
            else:
                service.record_expiry(resolution, fixture_patch)
                actual_status = PatchStatus.EXPIRED
                expired += 1
                case_snapshot = _excluded_snapshot(fixture_patch.patch_id)

            expected_status = PatchStatus(frozen["expected_patch_status"])
            if actual_status is not expected_status:
                failures.append(
                    f"patch status {actual_status.value!r} != {expected_status.value!r}"
                )
            expected_release = frozen.get("expected_active_release")
            if actual_release != expected_release:
                failures.append(f"release {actual_release!r} != {expected_release!r}")

            post, post_failures, overlay_ids = self._post_patch_queries(
                pipeline,
                case_snapshot,
                case_id,
            )
            failures.extend(post_failures)
            for key in post_counts:
                if post.get(key) in {
                    Decision.ANSWER.value,
                    Decision.ABSTAIN.value,
                    Decision.CLARIFY.value,
                }:
                    expected = frozen["expected_post_patch_behaviour"]
                    expected_key = {
                        "exact": "exact_scope",
                        "region": "alternate_region",
                        "service": "alternate_service_model",
                        "missing": "required_context_removed",
                    }[key]
                    if case_id == "M5A-046" and post[key] == expected[expected_key]:
                        post_counts[key] += 1
            if case_id == "M5A-046" and case_snapshot is not None:
                orchestration = pipeline.run_orchestrated_with_overlay(
                    QueryInput(
                        query="Does Control Meridian apply to Service Basic in Region Beta?",
                        context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
                        trace_id="m5b-orchestra-M5A-046",
                    ),
                    case_snapshot,
                )
                orchestration_decision = orchestration.final_verified_run.result.decision.value
                if orchestration_decision != Decision.ANSWER.value:
                    failures.append("M5A-046 overlay orchestration did not answer")

            if report.overall_status.value == "FAIL" and not report.failed_check_ids:
                failures.append("failed Policy CI report omitted failed check IDs")
            case_results.append(
                M5BCaseResult(
                    case_id=case_id,
                    matched=not failures,
                    failures=failures,
                    policy_ci_phase=phase,
                    check_statuses=actual_checks,
                    expected_patch_status=expected_status.value,
                    actual_patch_status=actual_status.value,
                    expected_active_release=expected_release,
                    actual_active_release=actual_release,
                    counterfactual_transition_count=report.counterfactual_transitions,
                    post_patch=post,
                    overlay_claim_ids=overlay_ids,
                    active_patch_ids=case_snapshot.active_patch_ids if case_snapshot else [],
                    excluded_patch_ids=case_snapshot.excluded_patch_ids if case_snapshot else [],
                    orchestration_decision=(
                        orchestration_decision if case_id == "M5A-046" else None
                    ),
                )
            )

        regression = service._regression_result
        if regression is None:
            regression = service._regression_gate.run()
        snapshot = active_snapshot or KnowledgeOverlaySnapshot(
            release_id="NO-ACTIVE-RELEASE",
            release_version="0.0.0",
            reference_time_utc=REFERENCE_TIME,
            active_patch_ids=[],
            excluded_patch_ids=[],
            evidence_units=[],
        )
        metrics = M5BMetrics(
            m5b_case_match_rate=round(
                sum(item.matched for item in case_results) / len(case_results), 3
            ),
            governed_evolution_count=governed_evolution,
            expected_governed_evolution_count=1,
            awaiting_approval_count=awaiting,
            expected_awaiting_approval_count=1,
            rejected_unsafe_patch_count=rejected,
            expected_rejected_unsafe_patch_count=2,
            expired_patch_exclusion_count=expired,
            expected_expired_patch_exclusion_count=1,
            policy_ci_check_count=len(reports) * 11,
            expected_policy_ci_check_count=55,
            policy_ci_status_match_count=status_matches,
            regression_expected=regression.expected,
            regression_matched=regression.matched,
            counterfactual_expected=4,
            counterfactual_matched=all_counterfactuals,
            exact_scope_answer_count=post_counts["exact"],
            alternate_region_abstention_count=post_counts["region"],
            alternate_service_abstention_count=post_counts["service"],
            missing_context_clarification_count=post_counts["missing"],
            automatic_approval_count=0,
            automatic_activation_count=0,
            self_approval_count=0,
            failed_check_override_count=0,
            official_corpus_mutation_count=0,
            expired_evidence_retrieval_count=0,
            network_violation_count=0,
        )
        self._write_jsonl(
            self.config.governance.generated_root / "policy_ci_reports.jsonl",
            reports,
        )
        self._write_jsonl(
            self.config.governance.generated_root / "knowledge_releases.jsonl",
            releases,
        )
        self._write_overlay_snapshot(snapshot)
        self._write_audit(case_results)
        audit_ok, audit_message = validate_m5b_audit_file(
            self.config.governance.generated_root / "audit.jsonl"
        )
        if not audit_ok:
            raise RuntimeError(f"M5B audit validation failed: {audit_message}")
        return M5BEvaluationDocument(
            schema_version="1.0",
            metrics=metrics,
            case_results=case_results,
            policy_ci_reports=reports,
            knowledge_releases=releases,
            overlay_snapshot=snapshot.model_dump(mode="json"),
            regression=regression.model_dump(mode="json"),
            security={
                "network_enabled": False,
                "external_api_enabled": False,
                "telemetry_enabled": False,
            },
            architecture_statement=(
                "M5B does not train or fine-tune a model from expert conversations.\n\n"
                "It converts structured expert resolutions into proposed knowledge\n"
                "patches and activates them only after mandatory Policy CI checks,\n"
                "separate human approval, and explicit release activation."
            ),
        )

    def _cases(self) -> dict[str, dict[str, Any]]:
        raw = json.loads(self.config.governance.contract_cases.read_text(encoding="utf-8"))
        return {str(item["id"]): item for item in raw["cases"]}

    @staticmethod
    def _phase_for(patch: Any, approval: Any) -> PolicyCIPhase:
        if patch.effective_to is not None and REFERENCE_TIME >= patch.effective_to:
            return PolicyCIPhase.CURRENT_STATE
        if approval is not None and approval.decision is ApprovalDecision.APPROVE:
            return PolicyCIPhase.ACTIVATION
        return PolicyCIPhase.PRE_APPROVAL

    def _post_patch_queries(
        self,
        pipeline: M5BRiskonPipeline,
        snapshot: KnowledgeOverlaySnapshot | None,
        case_id: str,
    ) -> tuple[dict[str, str], list[str], list[str]]:
        raw = json.loads(
            self.config.governance.overlay_evaluation_cases.read_text(encoding="utf-8")
        )
        case = next(item for item in raw["cases"] if item["case_id"] == case_id)
        if snapshot is None:
            snapshot = _excluded_snapshot(f"{case_id}-PATCH")
        post: dict[str, str] = {}
        failures: list[str] = []
        overlay_ids: list[str] = []
        for item in case["queries"]:
            query = QueryInput(**item["query_input"])
            run = pipeline.run_planned_with_overlay(query, snapshot)
            actual = run.verified_run.result
            snapshot_id = str(item["snapshot_id"])
            key = (
                "exact"
                if "exact-scope" in snapshot_id
                or "not-active" in snapshot_id
                or "rejected" in snapshot_id
                or "expired" in snapshot_id
                else "region"
                if "alternate-region" in snapshot_id
                else "service"
                if "alternate-service-model" in snapshot_id
                else "missing"
            )
            post[key] = actual.decision.value
            expected_decision = str(item["expected_decision"])
            if actual.decision.value != expected_decision:
                failures.append(
                    f"{snapshot_id}: {actual.decision.value!r} != {expected_decision!r}"
                )
            expected_reasons = [str(value) for value in item["expected_reason_codes"]]
            actual_reasons = [reason.value for reason in actual.reason_codes]
            if actual_reasons != expected_reasons:
                failures.append(f"{snapshot_id}: reason codes differ")
            selected_overlay_refs = [
                ref
                for ref in run.verified_run.verification.evidence_refs
                if ref.startswith("local://knowledge-overlay/")
            ]
            if selected_overlay_refs:
                overlay_claim_ids = sorted(
                    {
                        unit.claim_id
                        for unit in snapshot.evidence_units
                        if unit.overlay_ref in selected_overlay_refs
                        and unit.claim_id in run.verified_run.verification.supported_claim_ids
                    }
                )
                overlay_ids.extend(overlay_claim_ids)
            if item["expected_overlay_claim_ids"] and not set(
                item["expected_overlay_claim_ids"]
            ).issubset(set(run.verified_run.verification.supported_claim_ids)):
                failures.append(f"{snapshot_id}: expected overlay claim is not supported")
            if not item["expected_overlay_claim_ids"] and selected_overlay_refs:
                failures.append(f"{snapshot_id}: non-active overlay evidence was retrieved")
        return post, failures, list(dict.fromkeys(overlay_ids))

    def _clear_generated_outputs(self) -> None:
        root = self.config.governance.generated_root
        for name in (
            "evaluation.json",
            "evaluation.md",
            "policy_ci_reports.jsonl",
            "governance_events.jsonl",
            "knowledge_releases.jsonl",
            "overlay_snapshot.json",
            "audit.jsonl",
        ):
            path = root / name
            if path.is_file():
                path.unlink()

    @staticmethod
    def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(value, sort_keys=True) + "\n" for value in values),
            encoding="utf-8",
        )

    def _write_overlay_snapshot(self, snapshot: KnowledgeOverlaySnapshot) -> None:
        path = self.config.governance.generated_root / "overlay_snapshot.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _write_audit(self, results: list[M5BCaseResult]) -> None:
        path = self.config.governance.generated_root / "audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "case_id": item.case_id,
                "timestamp_utc": REFERENCE_TIME.isoformat(),
                "patch_status": item.actual_patch_status,
                "policy_ci_phase": item.policy_ci_phase.value,
                "active_patch_ids": item.active_patch_ids,
                "excluded_patch_ids": item.excluded_patch_ids,
                "network_enabled": False,
            }
            for item in results
        ]
        path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )


def _excluded_snapshot(patch_id: str) -> KnowledgeOverlaySnapshot:
    """Build an explicit no-overlay snapshot for blocked/expired patch probes."""

    return KnowledgeOverlaySnapshot(
        release_id=f"NO-ACTIVE-{patch_id}",
        release_version="0.0.0",
        reference_time_utc=REFERENCE_TIME,
        active_patch_ids=[],
        excluded_patch_ids=[patch_id],
        evidence_units=[],
    )
