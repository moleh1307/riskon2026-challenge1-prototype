"""Deterministic candidate-claim construction from ledger findings."""

from __future__ import annotations

from dataclasses import dataclass

from riskon.models import AnswerClaim
from riskon.orchestra.models import AgentFinding, FindingStance
from riskon.orchestra.source_safety import LocalCorpus, SourceSafetyContext
from riskon.orchestra.workers.base import unit_text


@dataclass(frozen=True)
class ClaimBuildResult:
    """Candidate claims plus deterministic safety/contradiction observations."""

    claims: tuple[AnswerClaim, ...]
    conflicting_claim_ids: tuple[str, ...]
    forbidden_evidence_refs: tuple[str, ...]


class DeterministicClaimBuilder:
    """Build claims only from SUPPORT findings and safe source references."""

    def __init__(self, corpus: LocalCorpus, safety: SourceSafetyContext) -> None:
        self.corpus = corpus
        self.safety = safety

    def build(self, findings: list[AgentFinding]) -> ClaimBuildResult:
        """Merge equivalent support findings and reject contradictory evidence."""

        grouped: dict[str, dict[str, object]] = {}
        forbidden_refs: set[str] = set()
        for finding in findings:
            if finding.stance is not FindingStance.SUPPORT:
                continue
            safe_refs: list[str] = []
            for reference in finding.evidence_refs:
                if not self.safety.policy.evidence_allowed(reference, self.safety.report):
                    forbidden_refs.add(reference)
                    continue
                if self.corpus.resolve(reference) is None:
                    continue
                safe_refs.append(reference)
            if not safe_refs:
                continue
            claim_text = unit_text(self.corpus, safe_refs[0], finding.claim_id)
            entry = grouped.setdefault(
                finding.claim_id,
                {"texts": set(), "refs": set(), "critical": False},
            )
            texts = entry["texts"]
            refs = entry["refs"]
            if isinstance(texts, set):
                texts.add(claim_text)
            if isinstance(refs, set):
                refs.update(safe_refs)
            entry["critical"] = bool(entry["critical"]) or finding.criticality == "CRITICAL"

        conflicting: list[str] = []
        claims: list[AnswerClaim] = []
        for claim_id in sorted(grouped):
            entry = grouped[claim_id]
            texts = entry["texts"]
            refs = entry["refs"]
            if not isinstance(texts, set) or not isinstance(refs, set):
                continue
            if len(texts) > 1:
                conflicting.append(claim_id)
                continue
            text = next(iter(texts), "")
            if not text:
                continue
            claims.append(
                AnswerClaim(
                    claim_id=claim_id,
                    text=text,
                    evidence_refs=sorted(refs),
                    critical=bool(entry["critical"]),
                )
            )
        return ClaimBuildResult(
            claims=tuple(claims),
            conflicting_claim_ids=tuple(conflicting),
            forbidden_evidence_refs=tuple(sorted(forbidden_refs)),
        )
