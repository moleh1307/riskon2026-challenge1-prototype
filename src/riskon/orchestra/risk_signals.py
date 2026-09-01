"""Deterministic automatic risk-signal detection for M4D."""

from __future__ import annotations

from collections import defaultdict

from riskon.models import Decision, PlannedVerifiedRun, QueryInput, QueryIntent
from riskon.orchestra.models import ActivationProfile, RiskAssessment, RiskSignal
from riskon.orchestra.runtime_policy import RuntimePolicy
from riskon.orchestra.source_safety import SourceSafetyReport


class OrchestraRiskSignalDetector:
    """Derive activation signals from structured runtime state only."""

    _human_first = {
        "APPROVAL_REQUIRED",
        "TECHNICAL_FAILURE",
        "UNSUPPORTED_MODALITY",
        "UNRESOLVED_REQUIRED_REFERENCE",
    }
    _full_orchestra = {
        "SCOPE_SENSITIVE",
        "JURISDICTION_SENSITIVE",
        "SERVICE_MODEL_SENSITIVE",
        "SOLICITATION_SENSITIVE",
        "WORKFLOW_STAGE_SENSITIVE",
        "CONTRADICTORY_SOURCES",
        "COUNTERFACTUAL_REQUIRED",
    }
    _dual_check = {
        "CRITICAL_CONTROL_RISK",
        "TABLE_DEPENDENT",
        "REQUIRED_REFERENCE",
        "MULTI_PART_QUERY",
        "LOW_RETRIEVAL_MARGIN",
        "PROMPT_INJECTION_SIGNAL",
    }

    def __init__(
        self,
        policy: RuntimePolicy,
        *,
        implemented_dimensions: tuple[str, ...] = (),
    ) -> None:
        self.policy = policy
        self.implemented_dimensions = tuple(implemented_dimensions)

    def assess(
        self,
        request: QueryInput,
        baseline: PlannedVerifiedRun,
        source_safety: SourceSafetyReport,
    ) -> RiskAssessment:
        """Return policy-ordered signals and provenance for one planned baseline."""

        sources: dict[str, set[str]] = defaultdict(set)

        def add(signal: str, detail: str | None = None) -> None:
            rule = self.policy.rule(signal)
            sources[signal].add(rule.source)
            if detail:
                sources[signal].add(detail)

        result = baseline.verified_run.result
        reasons = {reason.value for reason in result.reason_codes}
        if result.decision is Decision.CLARIFY:
            add("BASELINE_CLARIFY", "baseline.decision")
        for signal in (
            "MISSING_REQUIRED_CONTEXT",
            "AMBIGUOUS_ACRONYM",
            "APPROVAL_REQUIRED",
            "TECHNICAL_FAILURE",
            "UNSUPPORTED_MODALITY",
            "UNRESOLVED_REQUIRED_REFERENCE",
        ):
            if signal in reasons:
                add(signal, f"baseline.reason_codes:{signal}")

        evidence_text = self._evidence_text(baseline)
        context = {key.lower(): value.strip() for key, value in request.context.items()}

        if self._has_contradiction(baseline):
            add("CONTRADICTORY_SOURCES", "verification_and_retrieval")
        if context.get("region") and self._scope_value_present(
            context["region"], evidence_text, "region"
        ):
            add("SCOPE_SENSITIVE", "structured_context_and_evidence:region")
        if context.get("jurisdiction") and self._scope_value_present(
            context["jurisdiction"], evidence_text, "jurisdiction"
        ):
            add("JURISDICTION_SENSITIVE", "structured_context_and_evidence:jurisdiction")
        if context.get("service_model") and self._scope_value_present(
            context["service_model"], evidence_text, "service_model"
        ):
            add("SERVICE_MODEL_SENSITIVE", "structured_context_and_evidence:service_model")
        if context.get("solicitation_type") or (
            "solicitation_type" in baseline.query_plan.required_context_fields
        ):
            add("SOLICITATION_SENSITIVE", "structured_context_and_plan")
        if context.get("workflow_stage") or (
            "workflow_stage" in baseline.query_plan.required_context_fields
        ):
            add("WORKFLOW_STAGE_SENSITIVE", "structured_context_and_plan")

        if self._critical_claim_exists(baseline):
            add("CRITICAL_CONTROL_RISK", "claims_and_verification")
        if baseline.query_plan.intent is QueryIntent.CONFIGURATION_LOOKUP or self._has_table_ref(
            baseline
        ):
            add("TABLE_DEPENDENT", "query_plan_and_evidence")
        if baseline.verified_run.verification.missing_required_claim_ids:
            add("REQUIRED_REFERENCE", "verification.missing_required_claim_ids")
        if len(baseline.query_plan.subqueries) > 1:
            add("MULTI_PART_QUERY", "query_plan.subqueries")
        if (
            self._low_margin(baseline)
            and not self._has_explicit_support(baseline)
            and "UNRESOLVED_REQUIRED_REFERENCE" not in reasons
        ):
            add("LOW_RETRIEVAL_MARGIN", "retrieval_diagnostics")
        if any(
            item.diagnostic_code == "SOURCE_INSTRUCTION_IGNORED"
            for item in source_safety.diagnostics
        ):
            add("PROMPT_INJECTION_SIGNAL", "source_safety:SOURCE_INSTRUCTION_IGNORED")

        if (
            result.decision is Decision.ANSWER
            and ({"SCOPE_SENSITIVE", "SERVICE_MODEL_SENSITIVE"} & set(sources))
            and any(
                dimension in self.implemented_dimensions
                for dimension, signal in (
                    ("region", "SCOPE_SENSITIVE"),
                    ("service_model", "SERVICE_MODEL_SENSITIVE"),
                )
                if signal in sources
            )
        ):
            add("COUNTERFACTUAL_REQUIRED", "runtime_policy")

        signals = self.policy.validate_signals(
            [
                RiskSignal(str(signal))
                for signal in self.policy.risk_signal_order
                if str(signal) in sources
            ]
        )
        profile, reason = self._select_profile(result.decision, signals)
        signal_sources = {str(signal): tuple(sorted(sources[str(signal)])) for signal in signals}
        return RiskAssessment(
            risk_signals=signals,
            signal_sources=signal_sources,
            selected_activation_profile=profile,
            profile_reason=reason,
        )

    def _select_profile(
        self,
        decision: Decision,
        signals: tuple[RiskSignal, ...],
    ) -> tuple[ActivationProfile, str]:
        values = {str(signal) for signal in signals}
        if decision is Decision.CLARIFY or values & {
            "BASELINE_CLARIFY",
            "MISSING_REQUIRED_CONTEXT",
            "AMBIGUOUS_ACRONYM",
        }:
            return ActivationProfile.SHORT_CIRCUIT_CLARIFY, "clarification precedence"
        if decision is Decision.ABSTAIN and values & self._human_first:
            return ActivationProfile.HUMAN_FIRST, "human-first abstention precedence"
        if values & self._full_orchestra:
            return ActivationProfile.FULL_ORCHESTRA, "full-orchestra risk signal"
        if values & self._dual_check:
            return ActivationProfile.DUAL_CHECK, "dual-check risk signal"
        if decision is Decision.ANSWER and not values:
            return ActivationProfile.FAST_PATH, "answer with no detected risk signal"
        if decision is Decision.ABSTAIN:
            return ActivationProfile.HUMAN_FIRST, "safe abstention fallback"
        return ActivationProfile.DUAL_CHECK, "bounded safety review for non-empty risk state"

    @staticmethod
    def _evidence_text(baseline: PlannedVerifiedRun) -> str:
        values: list[str] = []
        for item in baseline.verified_run.result.evidence:
            values.extend((item.title, item.excerpt, *item.heading_path))
            values.extend(value for row in item.table_rows for value in row)
        for section in baseline.verified_run.result.retrieved_sections:
            values.extend((section.title, section.excerpt, *section.heading_path))
            values.extend(value for row in section.table_rows for value in row)
        return " ".join(values)

    @staticmethod
    def _scope_value_present(value: str, text: str, dimension: str) -> bool:
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if not normalized:
            return False
        candidates = {normalized, normalized.replace("_", " ")}
        if dimension == "region" and not normalized.startswith("region_"):
            candidates.update({f"region_{normalized}", f"region {normalized}"})
        if dimension == "service_model" and not normalized.startswith("service_"):
            candidates.update({f"service_{normalized}", f"service {normalized}"})
        lowered = text.lower()
        return any(candidate in lowered for candidate in candidates)

    @staticmethod
    def _critical_claim_exists(baseline: PlannedVerifiedRun) -> bool:
        report = baseline.verified_run.verification
        if any(claim.critical for claim in report.claims):
            return True
        text = " ".join(
            [
                baseline.verified_run.result.answer or "",
                *[claim_id for claim_id in report.supported_claim_ids],
            ]
        ).lower()
        return any(
            phrase in text
            for phrase in ("must not", "do not proceed", "cannot", "required", "override")
        )

    @staticmethod
    def _has_table_ref(baseline: PlannedVerifiedRun) -> bool:
        refs = [
            *baseline.verified_run.verification.evidence_refs,
            *(item.source_ref for item in baseline.verified_run.result.evidence),
            *(item.source_ref for item in baseline.verified_run.result.retrieved_sections),
        ]
        return any("#table-" in ref or ":row-" in ref for ref in refs)

    @staticmethod
    def _low_margin(baseline: PlannedVerifiedRun) -> bool:
        totals: dict[str, float] = defaultdict(float)
        for entry in baseline.retrieval_diagnostics.entries:
            totals[entry.candidate_ref] += entry.rrf_contribution
        if len(totals) < 2:
            return False
        top = sorted(totals.values(), reverse=True)
        return (top[0] - top[1]) < 0.015

    @staticmethod
    def _has_explicit_support(baseline: PlannedVerifiedRun) -> bool:
        report = baseline.verified_run.verification
        return bool(report.supported_claim_ids or report.claims)

    @staticmethod
    def _has_contradiction(baseline: PlannedVerifiedRun) -> bool:
        report = baseline.verified_run.verification
        return bool(
            report.scope_mismatches or (report.supported_claim_ids and report.unsupported_claim_ids)
        )
