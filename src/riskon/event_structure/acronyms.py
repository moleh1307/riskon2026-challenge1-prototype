"""Verified acronym expansions local to the event corpus."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from riskon.event_structure.ir import Document

EXPANSION_THEN_ACRONYM = re.compile(r"([A-Z][A-Za-z][A-Za-z&/\- ]{3,60}?)\s*\(([A-Z][A-Z&]{1,6})\)")
ACRONYM_THEN_EXPANSION = re.compile(
    r"\b([A-Z][A-Z&]{1,6})\b\s*[=:–-]\s*([A-Z][A-Za-z][A-Za-z&/\- ]{3,60})"
)
FILLER_WORDS = frozenset({"and", "of", "the", "for", "to", "in", "on", "&"})
Anchor = Literal["start", "end"]


def _letters(acronym: str) -> str:
    return "".join(character for character in acronym.upper() if character.isalpha())


def _initials(words: list[str]) -> str:
    return "".join(
        word[0].upper() for word in words if word[:1].isalpha() and word.lower() not in FILLER_WORDS
    )


def verify_expansion(acronym: str, candidate: str, anchor: Anchor = "end") -> str | None:
    target = _letters(acronym)
    if not target:
        return None
    matches = [match for match in re.finditer(r"[^\s/\u2010-\u2015-]+", candidate) if match.group()]
    tokens = [match.group() for match in matches]
    if anchor == "end":
        for start in range(len(tokens) - 1, -1, -1):
            run = tokens[start:]
            if not run or not run[0][:1].isalpha() or run[0].lower() in FILLER_WORDS:
                continue
            if _initials(run) == target:
                return candidate[matches[start].start() : matches[-1].end()]
        return None
    for stop in range(1, len(tokens) + 1):
        run = tokens[:stop]
        if _initials(run) == target:
            return candidate[matches[0].start() : matches[stop - 1].end()]
    return None


class AcronymEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    acronym: str
    expansion: str
    verified: bool
    occurrences: int = 0
    pages: list[str] = Field(default_factory=list)


class Glossary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entries: list[AcronymEntry] = Field(default_factory=list)

    def expansions(self, acronym: str) -> list[AcronymEntry]:
        return sorted(
            [entry for entry in self.entries if entry.acronym == acronym],
            key=lambda entry: -entry.occurrences,
        )

    def collisions(self) -> dict[str, list[str]]:
        by_acronym: dict[str, dict[str, str]] = defaultdict(dict)
        for entry in self.entries:
            if entry.verified:
                by_acronym[entry.acronym].setdefault(entry.expansion.casefold(), entry.expansion)
        return {
            acronym: sorted(expansions.values())
            for acronym, expansions in by_acronym.items()
            if len(expansions) > 1
        }

    def unique_verified(self) -> tuple[AcronymEntry, ...]:
        collisions = set(self.collisions())
        return tuple(
            entry for entry in self.entries if entry.verified and entry.acronym not in collisions
        )


def build_glossary(documents: list[Document]) -> Glossary:
    counts: dict[tuple[str, str, bool], Counter[str]] = defaultdict(Counter)
    for document in documents:
        for expansion, acronym in EXPANSION_THEN_ACRONYM.findall(document.text):
            candidate = expansion.strip()
            verified = verify_expansion(acronym, candidate)
            counts[(acronym, verified or candidate, verified is not None)][document.page_id] += 1
        for acronym, expansion in ACRONYM_THEN_EXPANSION.findall(document.text):
            verified = verify_expansion(acronym, expansion.strip(), anchor="start")
            if verified is not None:
                counts[(acronym, verified, True)][document.page_id] += 1
    entries = [
        AcronymEntry(
            acronym=acronym,
            expansion=expansion,
            verified=verified,
            occurrences=sum(pages.values()),
            pages=sorted(pages),
        )
        for (acronym, expansion, verified), pages in counts.items()
    ]
    entries.sort(key=lambda entry: (-entry.occurrences, entry.acronym, entry.expansion))
    return Glossary(entries=entries)
