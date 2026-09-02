"""Deterministic aliases derived only from the local event corpus."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from riskon.event_structure.acronyms import Glossary
from riskon.models import Section


class EventAlias(BaseModel):
    """One corpus-derived canonical phrase and its local variants."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical: str = Field(min_length=1)
    variants: list[str] = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    extraction_rule: str = Field(min_length=1)


class EventAliasRegistry(BaseModel):
    """Versioned, safe-to-serialize event alias registry."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    source: str
    aliases: list[EventAlias]

    @classmethod
    def from_file(cls, path: Path) -> EventAliasRegistry:
        """Load an event alias registry without accepting unknown fields."""

        resolved = path.expanduser().resolve()
        try:
            registry = cls.model_validate_json(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValidationError, ValueError) as exc:
            raise ValueError("Event alias registry could not be read") from exc
        if registry.schema_version != "1.0" or registry.source != "event_corpus":
            raise ValueError("Event alias registry schema is not recognized")
        return registry


_PHRASE_WORD = r"(?:[A-Za-z][A-Za-z'’/-]*|&)"
_PHRASE = rf"{_PHRASE_WORD}(?:\s+{_PHRASE_WORD}){{0,8}}"
_ACRONYM = r"[A-Z][A-Z&]{1,9}"
_TITLE_FORWARD = re.compile(
    rf"(?P<canonical>{_PHRASE})\s*"
    rf"\((?P<variant>{_ACRONYM})(?![A-Za-z])\)"
)
_TITLE_REVERSE = re.compile(
    rf"(?P<variant>{_ACRONYM})(?![A-Za-z])\s*"
    rf"\((?P<canonical>{_PHRASE})\)"
)
_HYPHEN_FORWARD = re.compile(
    rf"^\s*(?P<variant>{_ACRONYM})(?![A-Za-z])\s*[-–—]\s*"
    rf"(?P<canonical>{_PHRASE})"
)
_HYPHEN_REVERSE = re.compile(
    rf"^\s*(?P<canonical>{_PHRASE})\s*[-–—]\s*"
    rf"(?P<variant>{_ACRONYM})(?![A-Za-z])"
)


@dataclass
class _AliasRecord:
    canonical: str | None = None
    variants: set[str] = field(default_factory=set)
    rules: set[str] = field(default_factory=set)


def build_event_alias_registry(sections: Sequence[Section]) -> EventAliasRegistry:
    """Extract acronym relationships from titles and same-source text."""

    records: dict[tuple[str, str], _AliasRecord] = defaultdict(_AliasRecord)
    by_source: dict[str, list[Section]] = defaultdict(list)
    for section in sections:
        by_source[section.source_ref].append(section)

    for source_ref, source_sections in sorted(by_source.items()):
        titles = list(dict.fromkeys(section.title for section in source_sections))
        for title in titles:
            _collect_matches(records, source_ref, title, "PAGE_TITLE_PARENTHETICAL")
        for section in source_sections:
            for value in (*section.heading_path, section.text):
                for fragment in _fragments(value):
                    for rule, pattern in (
                        ("TEXT_PARENTHETICAL", _TITLE_FORWARD),
                        ("TEXT_REVERSE_PARENTHETICAL", _TITLE_REVERSE),
                        ("TEXT_HYPHEN", _HYPHEN_FORWARD),
                        ("TEXT_REVERSE_HYPHEN", _HYPHEN_REVERSE),
                    ):
                        _collect_matches(
                            records,
                            source_ref,
                            fragment,
                            rule,
                            pattern=pattern,
                        )

    aliases: list[EventAlias] = []
    for (canonical_key, source_ref), record in sorted(
        records.items(),
        key=lambda item: (item[0][0], item[0][1]),
    ):
        canonical = record.canonical or canonical_key
        variants = sorted(
            record.variants,
            key=lambda value: (-len(value), value.casefold()),
        )
        if not variants:
            continue
        aliases.append(
            EventAlias(
                canonical=canonical,
                variants=variants,
                source_ref=source_ref,
                extraction_rule="|".join(sorted(record.rules)),
            )
        )
    return EventAliasRegistry(
        schema_version="1.0",
        source="event_corpus",
        aliases=aliases,
    )


def write_event_alias_registry(registry: EventAliasRegistry, path: Path) -> Path:
    """Write only derived alias metadata under the ignored event output root."""

    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(
            registry.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return resolved


def merge_verified_glossary_aliases(
    registry: EventAliasRegistry,
    glossary: Glossary,
    source_refs_by_page: dict[str, str],
) -> EventAliasRegistry:
    """Add only unique, verified structural expansions to the existing alias registry.

    Colliding acronyms are deliberately omitted.  The structural glossary remains
    available on ``LocalCorpus.structural`` so callers can surface the ambiguity instead
    of silently selecting one expansion.
    """

    aliases = list(registry.aliases)
    existing = {
        (alias.canonical.casefold(), alias.source_ref, variant.casefold())
        for alias in aliases
        for variant in alias.variants
    }
    for entry in glossary.unique_verified():
        source_ref = source_refs_by_page.get(entry.pages[0], "") if entry.pages else ""
        if not source_ref:
            continue
        key = (entry.expansion.casefold(), source_ref, entry.acronym.casefold())
        if key in existing:
            continue
        aliases.append(
            EventAlias(
                canonical=entry.expansion,
                variants=[entry.acronym],
                source_ref=source_ref,
                extraction_rule="STRUCTURAL_VERIFIED_GLOSSARY",
            )
        )
        existing.add(key)
    return registry.model_copy(update={"aliases": aliases})


def _collect_matches(
    records: dict[tuple[str, str], _AliasRecord],
    source_ref: str,
    text: str,
    rule: str,
    *,
    pattern: re.Pattern[str] | None = None,
) -> None:
    active_pattern = pattern or _TITLE_FORWARD
    for match in active_pattern.finditer(text):
        canonical = _clean_phrase(match.group("canonical"))
        variant = _clean_variant(match.group("variant"))
        if not _valid_pair(canonical, variant):
            continue
        key = (canonical.casefold(), source_ref)
        record = records[key]
        record.canonical = canonical
        record.variants.update(_variant_forms(variant))
        record.rules.add(rule)


def _clean_phrase(value: str) -> str:
    return " ".join(value.replace("–", "-").replace("—", "-").split()).strip(" \"'*-:;,.")


def _clean_variant(value: str) -> str:
    value = value.replace("–", "-").replace("—", "-")
    value = re.sub(r"\s*&\s*", "&", value)
    return " ".join(value.split())


def _variant_forms(value: str) -> set[str]:
    forms = {value}
    if "&" in value:
        forms.add(value.replace("&", " & "))
    if "-" in value:
        forms.add(value.replace("-", " - "))
    return {" ".join(form.split()) for form in forms}


def _valid_pair(canonical: str, variant: str) -> bool:
    letters = sum(character.isalpha() for character in variant)
    variant_letters = "".join(character for character in variant if character.isalpha())
    common_words = {
        "ALL",
        "AND",
        "ARE",
        "BUY",
        "FOR",
        "IN",
        "IS",
        "IT",
        "NOT",
        "ON",
        "OR",
        "THE",
        "TO",
        "USE",
    }
    return (
        len(canonical) >= 3
        and letters >= 2
        and letters <= 10
        and bool(re.fullmatch(r"[A-Za-z& -]+", variant))
        and canonical.casefold() != variant.casefold()
        and variant_letters.upper() not in common_words
        and _initialism_matches(canonical, variant)
    )


def _initialism_matches(canonical: str, variant: str) -> bool:
    words = re.findall(r"[A-Za-z]+", canonical)
    variant_letters = "".join(character for character in variant if character.isalpha())
    initials = "".join(word[0] for word in words).upper()
    if len(words) < 2:
        return False
    return variant_letters.upper() == initials


def _fragments(value: str) -> list[str]:
    fragments = re.split(r"(?<=[.!?;:])\s+|\s*\n\s*|\s*\|\s*", value)
    return [fragment.strip(" \t•-") for fragment in fragments if fragment.strip(" \t•-")]
