"""Deterministic evidence gates for answer, clarification, and abstention."""

from riskon.models import (
    DetectedContext,
    Evidence,
    EvidenceCheck,
    ReasonCode,
    RetrievalHit,
)


class EvidenceChecker:
    """Apply M0's explicit minimum-score, context, and scope rules."""

    def __init__(self, minimum_score: float = 0.10) -> None:
        self.minimum_score = minimum_score

    def check(
        self,
        query: str,
        context: DetectedContext,
        hits: list[RetrievalHit],
    ) -> EvidenceCheck:
        relevant_hits = [hit for hit in hits if hit.score >= self.minimum_score]
        relevant_evidence = [self._evidence(hit) for hit in relevant_hits]
        reasons: list[ReasonCode] = []

        if context.missing_context:
            reasons.append(ReasonCode.MISSING_REQUIRED_CONTEXT)
        if context.need_type.value == "TECHNICAL_FAILURE":
            reasons.append(ReasonCode.TECHNICAL_FAILURE)

        if context.region == "REGION_BETA" and any(
            "region alpha only" in hit.excerpt.lower() for hit in relevant_hits
        ):
            reasons.append(ReasonCode.SCOPE_MISMATCH)

        lowered = query.lower()
        if any(
            term in lowered
            for term in ("open evidence", "evidence is unclear", "conflicting sources")
        ):
            reasons.append(ReasonCode.OPEN_EVIDENCE)

        if not relevant_hits and not reasons and not context.missing_context:
            reasons.append(ReasonCode.NO_RELEVANT_EVIDENCE)

        return EvidenceCheck(
            reason_codes=list(dict.fromkeys(reasons)),
            missing_context=context.missing_context,
            relevant_evidence=relevant_evidence,
        )

    @staticmethod
    def _evidence(hit: RetrievalHit) -> Evidence:
        return Evidence(
            section_id=hit.section_id,
            source_ref=hit.source_ref,
            title=hit.title,
            heading_path=hit.heading_path,
            score=hit.score,
            excerpt=hit.excerpt,
            table_rows=hit.table_rows,
        )
