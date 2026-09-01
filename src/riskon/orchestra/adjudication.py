"""Deterministic claim adjudication and material-objection gating."""

from __future__ import annotations

from dataclasses import dataclass

from riskon.models import (
    AnswerClaim,
    Decision,
    Evidence,
    PipelineResult,
    PlannedVerifiedRun,
    QueryInput,
    ReasonCode,
    VerificationReport,
    VerificationStatus,
    VerifiedRun,
)
from riskon.orchestra.claim_builder import ClaimBuildResult
from riskon.orchestra.models import MaterialObjection
from riskon.orchestra.source_safety import LocalCorpus
from riskon.provenance import ProvenanceIndex
from riskon.verification import VerificationEngine


@dataclass(frozen=True)
class MaterialObjectionDecision:
    """Retained objection history and the answer gate decision."""

    objections: tuple[MaterialObjection, ...]
    open_material_objections: tuple[MaterialObjection, ...]

    @property
    def answer_allowed(self) -> bool:
        """Return whether no open material objection blocks an answer."""

        return not self.open_material_objections


class MaterialObjectionGate:
    """Apply the rule that one open material objection prohibits ANSWER."""

    def evaluate(self, objections: list[MaterialObjection]) -> MaterialObjectionDecision:
        """Retain all objections, including resolved history."""

        ordered = tuple(sorted(objections, key=lambda item: item.objection_id))
        open_material = tuple(
            item for item in ordered if item.materiality == "MATERIAL" and item.status == "OPEN"
        )
        return MaterialObjectionDecision(
            objections=ordered,
            open_material_objections=open_material,
        )


def evidence_for_refs(corpus: LocalCorpus, references: list[str]) -> list[Evidence]:
    """Convert admitted source units to the existing evidence model."""

    evidence: list[Evidence] = []
    for reference in sorted(set(references)):
        unit = corpus.resolve(reference)
        if unit is None or unit.section_id is None:
            continue
        section = corpus.section_for_reference(reference)
        if section is None:
            continue
        evidence.append(
            Evidence(
                section_id=unit.section_id,
                source_ref=unit.source_ref,
                title=section.title,
                heading_path=list(unit.heading_path),
                score=1.0,
                excerpt=unit.text,
                table_rows=[list(unit.row)] if unit.kind == "table_row" else [],
            )
        )
    return evidence


class ExistingM1Adjudicator:
    """Use the existing M1 verifier as the evidence-authority boundary."""

    def __init__(self, corpus: LocalCorpus, verifier: VerificationEngine) -> None:
        self.corpus = corpus
        self.verifier = verifier

    def verify_candidate(
        self,
        baseline: PlannedVerifiedRun,
        claims: list[AnswerClaim],
        evidence_refs: list[str],
    ) -> VerifiedRun:
        """Ask M1 to verify a deterministic evidence envelope before final assembly."""

        evidence = evidence_for_refs(self.corpus, evidence_refs)
        data = baseline.verified_run.result.model_dump(mode="python")
        if claims:
            verification_texts: list[str] = []
            seen_texts: set[str] = set()
            section_ids = {
                unit.section_id
                for reference in evidence_refs
                if (unit := self.corpus.resolve(reference)) is not None
                and unit.section_id is not None
            }
            for section_id in sorted(section_ids):
                for unit in self.corpus.provenance.units_for_section(section_id):
                    if unit.text and unit.text not in seen_texts:
                        verification_texts.append(unit.text)
                        seen_texts.add(unit.text)
            for claim in claims:
                if claim.text not in seen_texts:
                    verification_texts.append(claim.text)
                    seen_texts.add(claim.text)
            data.update(
                decision=Decision.ANSWER,
                answer="\n".join(verification_texts),
                clarifying_question=None,
                reason_codes=[],
                evidence=evidence,
                route=None,
                answer_confidence=1.0,
                routing_confidence=0.0,
            )
        else:
            reason_codes = list(baseline.verified_run.result.reason_codes)
            if not reason_codes:
                reason_codes = [ReasonCode.NO_EXPLICIT_SUPPORT]
            route = baseline.verified_run.result.route
            if route is None:
                route = self.verifier.router.route(
                    baseline.verified_run.result.detected_context,
                    reason_codes,
                )
            data.update(
                decision=Decision.ABSTAIN,
                answer=None,
                clarifying_question=None,
                reason_codes=reason_codes,
                evidence=evidence,
                route=route,
                answer_confidence=0.0,
                routing_confidence=route.routing_confidence,
            )
        provisional = PipelineResult.model_validate(data)
        request = QueryInput(
            query=baseline.query_plan.original_query,
            trace_id=baseline.verified_run.result.trace_id,
        )
        verifier = self.verifier
        if claims:
            verifier = self._candidate_authority_verifier(claims)
        return verifier.verify(request, provisional)

    def _candidate_authority_verifier(self, claims: list[AnswerClaim]) -> VerificationEngine:
        """Expose list-backed M4 claims as sentence units to the same M1 engine."""

        claim_by_section: dict[str, list[str]] = {}
        for claim in claims:
            for reference in claim.evidence_refs:
                unit = self.corpus.resolve(reference)
                if unit is not None and unit.section_id is not None:
                    claim_by_section.setdefault(unit.section_id, []).append(claim.text)

        sections = []
        for section in self.corpus.sections:
            copy = section.model_copy(deep=True)
            existing = set(copy.paragraphs)
            section_claims = {
                claim.claim_id: claim.text
                for claim in claims
                if any(
                    (unit := self.corpus.resolve(reference)) is not None
                    and unit.section_id == section.section_id
                    for reference in claim.evidence_refs
                )
            }
            copy.claims.update(section_claims)
            for text in claim_by_section.get(section.section_id, []):
                if text not in existing:
                    copy.paragraphs.append(text)
                    existing.add(text)
            sections.append(copy)
        provenance = ProvenanceIndex(
            sections,
            knowledge_root=self.corpus.knowledge_root,
            ref_style="m2",
        )
        return VerificationEngine(provenance, self.verifier.router, self.verifier.config)


def adjudicate(
    baseline: PlannedVerifiedRun,
    claim_build: ClaimBuildResult,
    evidence_refs: list[str],
    corpus: LocalCorpus,
    m1_adjudicator: ExistingM1Adjudicator,
    objection_gate: MaterialObjectionDecision,
) -> VerifiedRun:
    """Produce a new verified run without mutating the frozen baseline."""

    claims = list(claim_build.claims)
    m1_verified = m1_adjudicator.verify_candidate(baseline, claims, evidence_refs)
    evidence = evidence_for_refs(corpus, evidence_refs)
    allowed = (
        bool(claims)
        and not claim_build.conflicting_claim_ids
        and objection_gate.answer_allowed
        and m1_verified.verification.status is VerificationStatus.SUFFICIENT
        and m1_verified.result.decision is Decision.ANSWER
    )
    if allowed:
        result_data = baseline.verified_run.result.model_dump(mode="python")
        result_data.update(
            decision=Decision.ANSWER,
            answer="\n".join(claim.text for claim in claims),
            clarifying_question=None,
            reason_codes=[],
            evidence=evidence,
            route=None,
            answer_confidence=1.0,
            routing_confidence=0.0,
        )
        result = PipelineResult.model_validate(result_data)
        report_data = m1_verified.verification.model_dump(mode="python")
        report_data.update(
            status=VerificationStatus.SUFFICIENT,
            reason_codes=[],
            supported_claim_ids=[claim.claim_id for claim in claims],
            unsupported_claim_ids=[],
            missing_required_claim_ids=[],
            scope_mismatches=[],
            unresolved_required_references=[],
            unsupported_modalities=[],
            evidence_refs=sorted(set(evidence_refs)),
            explanation="Existing M1 verification accepted the deterministic candidate claims.",
        )
        report = VerificationReport.model_validate(report_data)
        report._claims = claims
        return VerifiedRun(result=result, verification=report)

    reasons = list(baseline.verified_run.result.reason_codes)
    if not reasons:
        reasons = list(m1_verified.result.reason_codes)
    if not reasons:
        reasons = [ReasonCode.NO_EXPLICIT_SUPPORT]
    route = baseline.verified_run.result.route or m1_verified.result.route
    if route is None:
        raise ValueError("M4B ABSTAIN requires an existing route")
    result_data = baseline.verified_run.result.model_dump(mode="python")
    result_data.update(
        decision=Decision.ABSTAIN,
        answer=None,
        clarifying_question=None,
        reason_codes=reasons,
        evidence=evidence,
        route=route,
        answer_confidence=0.0,
        routing_confidence=route.routing_confidence,
    )
    result = PipelineResult.model_validate(result_data)
    report_data = m1_verified.verification.model_dump(mode="python")
    report_data.update(
        status=VerificationStatus.INSUFFICIENT,
        reason_codes=reasons,
        supported_claim_ids=[],
        unsupported_claim_ids=[],
        missing_required_claim_ids=list(claim_build.conflicting_claim_ids),
        scope_mismatches=[],
        unresolved_required_references=[],
        unsupported_modalities=[],
        evidence_refs=sorted(set(evidence_refs)),
        explanation="An open material objection or unresolved evidence conflict prohibited ANSWER.",
    )
    report = VerificationReport.model_validate(report_data)
    report._claims = []
    return VerifiedRun(result=result, verification=report)
