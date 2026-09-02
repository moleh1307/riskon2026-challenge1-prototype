"""Declared-versus-inferred source metadata.

The adapter only proposes metadata from text.  It never turns a proposal into an
out-of-scope exclusion.  Explicit source declarations can be supplied separately and
are the only metadata allowed to answer a coverage question negatively.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_structure.ir import Document


class ScopeClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str
    declared: bool = False
    evidence: int = 0


class PageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str
    declared: bool = False
    document_type: str | None = None
    jurisdictions: list[ScopeClaim] = Field(default_factory=list)
    legal_entities: list[ScopeClaim] = Field(default_factory=list)
    booking_centres: list[ScopeClaim] = Field(default_factory=list)
    service_models: list[ScopeClaim] = Field(default_factory=list)
    effective_from: date | None = None
    superseded_by: str | None = None
    does_not_cover: list[str] = Field(default_factory=list)

    def scope_values(self) -> set[str]:
        return {
            claim.value
            for claims in (
                self.jurisdictions,
                self.legal_entities,
                self.booking_centres,
                self.service_models,
            )
            for claim in claims
        }

    def covers(self, value: str) -> bool | None:
        if value in self.does_not_cover:
            return False
        if value in self.scope_values():
            return True
        return False if self.declared else None


class TypeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_type: str
    hits: int


class MetadataProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: PageMetadata
    type_candidates: list[TypeCandidate] = Field(default_factory=list)
    years_mentioned: list[int] = Field(default_factory=list)

    @property
    def type_is_ambiguous(self) -> bool:
        return (
            len(self.type_candidates) >= 2
            and self.type_candidates[0].hits == self.type_candidates[1].hits
        )


TYPE_SIGNALS: dict[str, re.Pattern[str]] = {
    "refresher_training": re.compile(r"refresher training", re.I),
    "faq": re.compile(r"\bFAQ\b|frequently asked", re.I),
    "policy": re.compile(r"\bpolicy\b", re.I),
    "directive": re.compile(r"\bdirective\b", re.I),
    "guideline": re.compile(r"\bguidelines?\b", re.I),
    "manual": re.compile(r"\bmanual\b", re.I),
}
SCOPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "legal_entities": re.compile(r"\b(RML [A-Z]{2}|BJBE)\b"),
    "booking_centres": re.compile(r"\bBC ([A-Z]{2,3})\b"),
    "jurisdictions": re.compile(r"\b(FIDLEG|MiFID|Monaco|MC_Local)\b"),
    "service_models": re.compile(r"\b(Advice Premium|Advice Basic|Advice Light|Trade Basic)\b"),
}
DATE_MENTION = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d\d)\b"
)


def _claims(text: str, pattern: re.Pattern[str]) -> list[ScopeClaim]:
    counts = Counter(
        match if isinstance(match, str) else match[0] for match in pattern.findall(text)
    )
    return [
        ScopeClaim(value=value, declared=False, evidence=count)
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def propose_metadata(document: Document) -> MetadataProposal:
    text = document.text
    candidates = [
        TypeCandidate(document_type=name, hits=len(pattern.findall(text)))
        for name, pattern in TYPE_SIGNALS.items()
        if pattern.search(text)
    ]
    candidates.sort(key=lambda candidate: (-candidate.hits, candidate.document_type))
    metadata = PageMetadata(
        page_id=document.page_id,
        declared=False,
        legal_entities=_claims(text, SCOPE_PATTERNS["legal_entities"]),
        booking_centres=[
            ScopeClaim(value=f"BC {claim.value}", declared=False, evidence=claim.evidence)
            for claim in _claims(text, SCOPE_PATTERNS["booking_centres"])
        ],
        jurisdictions=_claims(text, SCOPE_PATTERNS["jurisdictions"]),
        service_models=_claims(text, SCOPE_PATTERNS["service_models"]),
    )
    proposal = MetadataProposal(
        metadata=metadata,
        type_candidates=candidates,
        years_mentioned=sorted({int(year) for _, year in DATE_MENTION.findall(text)}),
    )
    if candidates and not proposal.type_is_ambiguous:
        metadata.document_type = candidates[0].document_type
    return proposal


def explicit_metadata(
    page_id: str,
    *,
    jurisdictions: tuple[str, ...] = (),
    legal_entities: tuple[str, ...] = (),
    booking_centres: tuple[str, ...] = (),
    service_models: tuple[str, ...] = (),
    does_not_cover: tuple[str, ...] = (),
) -> PageMetadata:
    """Build metadata only for an explicit source/property declaration."""

    def claims(values: tuple[str, ...]) -> list[ScopeClaim]:
        return [ScopeClaim(value=value, declared=True, evidence=1) for value in values]

    return PageMetadata(
        page_id=page_id,
        declared=True,
        jurisdictions=claims(jurisdictions),
        legal_entities=claims(legal_entities),
        booking_centres=claims(booking_centres),
        service_models=claims(service_models),
        does_not_cover=list(does_not_cover),
    )
