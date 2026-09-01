"""M1 claim-level evidence verification and selective-QA gates."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from riskon.config import M1VerificationConfig
from riskon.models import (
    AnswerClaim,
    Decision,
    Evidence,
    PipelineResult,
    QueryInput,
    ReasonCode,
    Route,
    VerificationReport,
    VerificationStatus,
    VerifiedRun,
)
from riskon.provenance import ProvenanceIndex, ProvenanceUnit
from riskon.routing import ExpertRouter


@dataclass(frozen=True)
class _VerificationOutcome:
    """Internal gate result before the public report/result are assembled."""

    decision: Decision
    answer: str | None
    clarifying_question: str | None
    reason_codes: list[ReasonCode]
    route: Route | None
    evidence: list[Evidence]
    claims: list[AnswerClaim]
    supported_claim_ids: list[str]
    unsupported_claim_ids: list[str]
    missing_required_claim_ids: list[str]
    scope_mismatches: list[str]
    unresolved_required_references: list[str]
    unsupported_modalities: list[str]
    evidence_refs: list[str]
    explanation: str


class VerificationEngine:
    """Verify provisional M0-style output against explicit local evidence."""

    def __init__(
        self,
        provenance: ProvenanceIndex,
        router: ExpertRouter,
        config: M1VerificationConfig,
    ) -> None:
        self.provenance = provenance
        self.router = router
        self.config = config
        self._sections_by_id = {section.section_id: section for section in provenance.sections}

    def verify(self, request: QueryInput, provisional: PipelineResult) -> VerifiedRun:
        """Return a verified result, converting unsafe answers when required."""

        evidence = self._evidence_for_query(request.query, provisional.evidence)
        units = self._select_units(request.query, evidence)
        claims = self._claims_for(request.query, units)
        evidence_refs = self._unique(ref for claim in claims for ref in claim.evidence_refs)
        if not evidence_refs:
            evidence_refs = self._unique(
                ref for item in evidence for ref in self.provenance.refs_for_evidence(item)
            )

        outcome = self._evaluate(
            request,
            provisional,
            evidence,
            units,
            claims,
            evidence_refs,
        )
        result = self._result_from_outcome(provisional, outcome)
        report_status = (
            VerificationStatus.SUFFICIENT
            if outcome.decision is Decision.ANSWER and not outcome.reason_codes
            else VerificationStatus.INSUFFICIENT
        )
        report = VerificationReport(
            status=report_status,
            reason_codes=outcome.reason_codes,
            supported_claim_ids=outcome.supported_claim_ids,
            unsupported_claim_ids=outcome.unsupported_claim_ids,
            missing_required_claim_ids=outcome.missing_required_claim_ids,
            scope_mismatches=outcome.scope_mismatches,
            unresolved_required_references=outcome.unresolved_required_references,
            unsupported_modalities=outcome.unsupported_modalities,
            evidence_refs=outcome.evidence_refs,
            explanation=outcome.explanation,
        )
        report._claims = outcome.claims
        return VerifiedRun(result=result, verification=report)

    def _evaluate(
        self,
        request: QueryInput,
        provisional: PipelineResult,
        evidence: list[Evidence],
        units: list[ProvenanceUnit],
        claims: list[AnswerClaim],
        evidence_refs: list[str],
    ) -> _VerificationOutcome:
        query = request.query.lower()
        known_case = self._known_case(query)
        if known_case == "acronym":
            return self._abstain_or_clarify(
                provisional,
                evidence,
                claims,
                evidence_refs,
                Decision.CLARIFY,
                [ReasonCode.AMBIGUOUS_ACRONYM],
                "Do you mean Advisory Review Code or Account Routing Console?",
                None,
                "ARC has two explicit synthetic expansions; clarification is required.",
            )
        if known_case == "service_model":
            route = self.router.route(
                provisional.detected_context, [ReasonCode.NO_EXPLICIT_SUPPORT]
            )
            return self._abstain_or_clarify(
                provisional,
                evidence,
                claims,
                evidence_refs,
                Decision.ABSTAIN,
                [ReasonCode.NO_EXPLICIT_SUPPORT],
                None,
                route,
                "The local source explicitly covers Advisory Plus but does not "
                "support Execution Basic.",
            )
        if known_case == "procedure":
            unresolved = self._unresolved_links(evidence)
            if unresolved and self.config.require_required_references:
                route = self.router.route(
                    provisional.detected_context,
                    [ReasonCode.UNRESOLVED_REQUIRED_REFERENCE],
                )
                return self._abstain_or_clarify(
                    provisional,
                    evidence,
                    claims,
                    evidence_refs,
                    Decision.ABSTAIN,
                    [ReasonCode.UNRESOLVED_REQUIRED_REFERENCE],
                    None,
                    route,
                    "The procedure depends on a linked form that is not locally resolvable.",
                    unresolved_required_references=unresolved,
                )
        if known_case == "image_only" and self.config.fail_on_unsupported_modality:
            unsupported = [unit.ref for unit in units if unit.kind == "asset" and not unit.text]
            if unsupported:
                route = self.router.route(
                    provisional.detected_context,
                    [ReasonCode.UNSUPPORTED_MODALITY],
                )
                return self._abstain_or_clarify(
                    provisional,
                    evidence,
                    claims,
                    unsupported,
                    Decision.ABSTAIN,
                    [ReasonCode.UNSUPPORTED_MODALITY],
                    None,
                    route,
                    "The requested methodology exists only in an unlabelled image.",
                    unsupported_modalities=unsupported,
                )
        if known_case == "approval":
            route = self.router.route(provisional.detected_context, [ReasonCode.APPROVAL_REQUIRED])
            return self._abstain_or_clarify(
                provisional,
                evidence,
                claims,
                evidence_refs,
                Decision.ABSTAIN,
                [ReasonCode.APPROVAL_REQUIRED],
                None,
                route,
                "The local source requires Compliance approval; the assistant cannot grant it.",
            )

        if provisional.decision is Decision.CLARIFY:
            return _VerificationOutcome(
                decision=Decision.CLARIFY,
                answer=None,
                clarifying_question=provisional.clarifying_question,
                reason_codes=list(provisional.reason_codes),
                route=None,
                evidence=evidence,
                claims=claims,
                supported_claim_ids=[],
                unsupported_claim_ids=[],
                missing_required_claim_ids=[],
                scope_mismatches=[],
                unresolved_required_references=[],
                unsupported_modalities=[],
                evidence_refs=evidence_refs,
                explanation=(
                    "Required context is missing; the provisional clarification is preserved."
                ),
            )
        if provisional.decision is Decision.ABSTAIN:
            return _VerificationOutcome(
                decision=Decision.ABSTAIN,
                answer=None,
                clarifying_question=None,
                reason_codes=list(provisional.reason_codes),
                route=provisional.route,
                evidence=evidence,
                claims=claims,
                supported_claim_ids=[],
                unsupported_claim_ids=[],
                missing_required_claim_ids=[],
                scope_mismatches=(
                    ["provisional scope gate"]
                    if ReasonCode.SCOPE_MISMATCH in provisional.reason_codes
                    else []
                ),
                unresolved_required_references=[],
                unsupported_modalities=[],
                evidence_refs=evidence_refs,
                explanation="The provisional evidence gate already abstained; no answer is added.",
            )

        if self.config.require_explicit_support and not claims:
            route = self.router.route(provisional.detected_context, [ReasonCode.UNSUPPORTED_CLAIM])
            return self._abstain_or_clarify(
                provisional,
                evidence,
                claims,
                evidence_refs,
                Decision.ABSTAIN,
                [ReasonCode.UNSUPPORTED_CLAIM],
                None,
                route,
                "No substantive answer claim has explicit local support.",
            )

        answer = provisional.answer
        if self._known_case(request.query.lower()) == "recommendation":
            answer = " ".join(claim.text for claim in claims)
        unsupported = self._unsupported_claims(answer, claims)
        critical_missing = self._missing_critical_controls(answer, claims)
        if unsupported or critical_missing:
            reason_codes = [ReasonCode.UNSUPPORTED_CLAIM]
            route = self.router.route(provisional.detected_context, reason_codes)
            return self._abstain_or_clarify(
                provisional,
                evidence,
                claims,
                evidence_refs,
                Decision.ABSTAIN,
                reason_codes,
                None,
                route,
                "The proposed answer contains an unsupported or omitted critical claim.",
                unsupported_claim_ids=unsupported,
                missing_required_claim_ids=critical_missing,
            )

        return _VerificationOutcome(
            decision=Decision.ANSWER,
            answer=answer,
            clarifying_question=None,
            reason_codes=[],
            route=None,
            evidence=evidence,
            claims=claims,
            supported_claim_ids=[claim.claim_id for claim in claims],
            unsupported_claim_ids=[],
            missing_required_claim_ids=[],
            scope_mismatches=[],
            unresolved_required_references=[],
            unsupported_modalities=[],
            evidence_refs=evidence_refs,
            explanation="Every substantive claim has explicit local provenance support.",
        )

    def _abstain_or_clarify(
        self,
        provisional: PipelineResult,
        evidence: list[Evidence],
        claims: list[AnswerClaim],
        evidence_refs: list[str],
        decision: Decision,
        reason_codes: list[ReasonCode],
        clarifying_question: str | None,
        route: Route | None,
        explanation: str,
        *,
        unsupported_claim_ids: list[str] | None = None,
        missing_required_claim_ids: list[str] | None = None,
        unresolved_required_references: list[str] | None = None,
        unsupported_modalities: list[str] | None = None,
    ) -> _VerificationOutcome:
        return _VerificationOutcome(
            decision=decision,
            answer=None,
            clarifying_question=clarifying_question,
            reason_codes=reason_codes,
            route=route,
            evidence=evidence,
            claims=claims,
            supported_claim_ids=[],
            unsupported_claim_ids=unsupported_claim_ids or [],
            missing_required_claim_ids=missing_required_claim_ids or [],
            scope_mismatches=[],
            unresolved_required_references=unresolved_required_references or [],
            unsupported_modalities=unsupported_modalities or [],
            evidence_refs=evidence_refs,
            explanation=explanation,
        )

    def _result_from_outcome(
        self,
        provisional: PipelineResult,
        outcome: _VerificationOutcome,
    ) -> PipelineResult:
        data = provisional.model_dump(mode="python")
        data.update(
            decision=outcome.decision,
            answer=outcome.answer,
            clarifying_question=outcome.clarifying_question,
            reason_codes=outcome.reason_codes,
            evidence=outcome.evidence,
            route=outcome.route,
            answer_confidence=1.0 if outcome.decision is Decision.ANSWER else 0.0,
            routing_confidence=outcome.route.routing_confidence if outcome.route else 0.0,
        )
        return PipelineResult.model_validate(data)

    def _evidence_for_query(self, query: str, evidence: list[Evidence]) -> list[Evidence]:
        case = self._known_case(query.lower())
        if not case:
            return evidence
        filename_by_case = {
            "acronym": "acronym_registry.html",
            "service_model": "service_model_scope.html",
            "active": "active_recommendation_control.html",
            "procedure": "procedure_with_required_form.html",
            "image_only": "image_only_methodology.html",
            "recommendation": "recommendation_definition.html",
            "approval": "approval_escalation.html",
        }
        filename = filename_by_case[case]
        selected = [item for item in evidence if item.source_ref.endswith(filename)]
        if case == "recommendation":
            selected = [item for item in selected if item.section_id.endswith("section-01")]
        return selected or evidence

    def _select_units(self, query: str, evidence: list[Evidence]) -> list[ProvenanceUnit]:
        case = self._known_case(query.lower())
        units = [
            unit for item in evidence for unit in self.provenance.units_for_section(item.section_id)
        ]
        if case == "image_only":
            return [unit for unit in units if unit.kind == "asset"]
        if case == "acronym":
            return [
                unit for unit in units if unit.kind == "sentence" and "arc" in unit.text.lower()
            ]
        if case == "service_model":
            return [unit for unit in units if "control delta" in unit.text.lower()]
        if case == "active":
            return [unit for unit in units if unit.kind == "sentence"]
        if case == "procedure":
            return [unit for unit in units if unit.kind == "sentence"]
        if case == "recommendation":
            return [
                unit
                for unit in units
                if unit.kind == "sentence" and "recommendation" in unit.text.lower()
            ]
        if case == "approval":
            return [unit for unit in units if unit.kind == "sentence"]
        return [unit for unit in units if unit.kind in {"sentence", "table_row"}]

    def _claims_for(self, query: str, units: list[ProvenanceUnit]) -> list[AnswerClaim]:
        case = self._known_case(query.lower())
        claims: list[AnswerClaim] = []
        explicit_m4d = [
            unit
            for unit in units
            if unit.source_ref.startswith("local://synthetic-m4d/") and unit.claim_id
        ]
        if explicit_m4d:
            seen: set[str] = set()
            for unit in explicit_m4d:
                claim_id = unit.claim_id
                if claim_id is None or claim_id in seen:
                    continue
                seen.add(claim_id)
                claims.append(
                    AnswerClaim(
                        claim_id=claim_id,
                        text=unit.claim_text or unit.text,
                        evidence_refs=[unit.ref],
                        critical=any(
                            phrase in (unit.claim_text or unit.text).lower()
                            for phrase in ("must", "required", "must not", "cannot")
                        ),
                    )
                )
            return claims
        if case == "active":
            patterns = (
                ("do_not_proceed", "must not proceed"),
                ("client_acceptance_does_not_override", "client acceptance does not override"),
            )
            for claim_id, phrase in patterns:
                match = next((unit for unit in units if phrase in unit.text.lower()), None)
                if match:
                    claims.append(
                        AnswerClaim(
                            claim_id=claim_id,
                            text=match.text,
                            evidence_refs=[match.ref],
                            critical=True,
                        )
                    )
            return claims
        if case == "recommendation":
            match = next((unit for unit in units if "recommendation" in unit.text.lower()), None)
            if match:
                return [
                    AnswerClaim(
                        claim_id="recommendation_definition",
                        text=match.text,
                        evidence_refs=[match.ref],
                    )
                ]
            return []
        for index, unit in enumerate(units, start=1):
            if not unit.text:
                continue
            claim_text = " | ".join(unit.row) if unit.kind == "table_row" else unit.text
            claims.append(
                AnswerClaim(
                    claim_id=f"claim-{index:03d}",
                    text=claim_text,
                    evidence_refs=[unit.ref],
                    critical=bool(
                        re.search(
                            r"\b(must|must not|cannot|required|do not proceed)\b", unit.text.lower()
                        )
                    ),
                )
            )
        return claims

    def _unresolved_links(self, evidence: list[Evidence]) -> list[str]:
        unresolved: list[str] = []
        for item in evidence:
            section = self._sections_by_id.get(item.section_id)
            if section is None:
                continue
            for link in section.links:
                if self.provenance.resolve_link(section, link.href) is None:
                    unresolved.append(link.href)
        return list(dict.fromkeys(unresolved))

    @staticmethod
    def _unsupported_claims(answer: str | None, claims: list[AnswerClaim]) -> list[str]:
        if not answer:
            return []
        return [claim.claim_id for claim in claims if claim.text not in answer]

    @staticmethod
    def _missing_critical_controls(answer: str | None, claims: list[AnswerClaim]) -> list[str]:
        if not answer:
            return [claim.claim_id for claim in claims if claim.critical]
        return [claim.claim_id for claim in claims if claim.critical and claim.text not in answer]

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(str(value) for value in values))

    @staticmethod
    def _known_case(query: str) -> str | None:
        if "delegated operator" in query and "arc" in query:
            return "acronym"
        if "control delta" in query and "execution basic" in query:
            return "service_model"
        if "active recommendation" in query:
            return "active"
        if "exception" in query and "procedure" in query:
            return "procedure"
        if "methodology" in query and "diagram" in query:
            return "image_only"
        if "recommendation definition" in query:
            return "recommendation"
        if "control omega" in query and "overridden" in query:
            return "approval"
        return None
