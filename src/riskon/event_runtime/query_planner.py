"""Natural-language query planning for the external event corpus."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from riskon.config import M2QueryPlanningConfig
from riskon.event_runtime.aliases import EventAlias, EventAliasRegistry
from riskon.models import QueryInput, QueryPlan
from riskon.query_planning import QueryPlanner


class EventQueryPlanner:
    """Plan arbitrary event questions without importing the synthetic lexicon."""

    _stop_words = frozenset(
        {
            "a",
            "about",
            "all",
            "also",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "can",
            "could",
            "did",
            "does",
            "for",
            "from",
            "have",
            "has",
            "how",
            "i",
            "if",
            "in",
            "is",
            "it",
            "me",
            "my",
            "of",
            "on",
            "or",
            "please",
            "should",
            "that",
            "the",
            "these",
            "this",
            "to",
            "what",
            "when",
            "where",
            "which",
            "why",
            "with",
            "would",
            "you",
            "your",
        }
    )
    _common_acronym_words = frozenset(
        {
            "all",
            "and",
            "are",
            "buy",
            "for",
            "in",
            "is",
            "it",
            "not",
            "on",
            "or",
            "the",
            "to",
            "use",
        }
    )

    def __init__(
        self,
        aliases: Sequence[EventAlias],
        page_titles: Sequence[str],
        config: M2QueryPlanningConfig,
    ) -> None:
        self.aliases = tuple(aliases)
        self.page_titles = tuple(
            dict.fromkeys(title.strip() for title in page_titles if title.strip())
        )
        self.config = config

    @classmethod
    def from_file(
        cls,
        path: Path,
        *,
        page_titles: Sequence[str],
        config: M2QueryPlanningConfig,
    ) -> EventQueryPlanner:
        """Load corpus-derived aliases and bind the manifest title vocabulary."""

        registry = EventAliasRegistry.from_file(path)
        return cls(registry.aliases, page_titles, config)

    @classmethod
    def from_aliases(
        cls,
        aliases: Sequence[EventAlias | dict[str, object]],
        *,
        page_titles: Sequence[str],
        config: M2QueryPlanningConfig,
    ) -> EventQueryPlanner:
        """Construct a planner from already validated local aliases."""

        parsed = [
            item if isinstance(item, EventAlias) else EventAlias.model_validate(item)
            for item in aliases
        ]
        return cls(parsed, page_titles, config)

    def plan(self, request: QueryInput) -> QueryPlan:
        """Build an event plan while retaining retrieval despite missing context."""

        normalised = self._normalise(request.query)
        matched_titles = self._matching_titles(request.query, normalised)
        intent = QueryPlanner._intent(normalised)
        required_fields = QueryPlanner._required_context_fields(intent)
        supplied_context = self._context_values(request, normalised)
        missing_fields = [field for field in required_fields if field not in supplied_context]
        subqueries = QueryPlanner([], self.config)._decompose(normalised)
        channels = QueryPlanner._channels(intent)
        canonical_terms = self._canonical_terms(
            request.query,
            normalised,
            matched_titles,
        )
        plan_id = QueryPlanner._plan_id(
            request,
            normalised,
            intent,
            canonical_terms,
            required_fields,
            missing_fields,
            subqueries,
            channels,
            False,
        )
        return QueryPlan(
            plan_id=plan_id,
            original_query=request.query,
            normalised_query=normalised,
            intent=intent,
            canonical_terms=canonical_terms,
            required_context_fields=required_fields,
            missing_context_fields=missing_fields,
            subqueries=subqueries,
            retrieval_channels=channels,
            retrieval_skipped=False,
        )

    def context_values(self, request: QueryInput, plan: QueryPlan) -> dict[str, str]:
        """Expose normalized event context for structure-aware filtering."""

        return self._context_values(request, plan.normalised_query)

    def _normalise(self, query: str) -> str:
        result = _normalise_punctuation(query)
        for alias in sorted(
            self.aliases,
            key=lambda item: max((len(value) for value in item.variants), default=0),
            reverse=True,
        ):
            replacement = alias.canonical
            variants = [
                variant
                for variant in [*alias.variants, alias.canonical]
                if variant == alias.canonical or _usable_acronym(variant)
            ]
            for variant in sorted(
                variants,
                key=len,
                reverse=True,
            ):
                result = _replace_phrase(result, variant, replacement)
        return " ".join(result.split())

    def _canonical_terms(
        self,
        original_query: str,
        normalised_query: str,
        matched_titles: Sequence[str],
    ) -> list[str]:
        terms: list[str] = []

        def add(value: str) -> None:
            cleaned = " ".join(value.casefold().split())
            if cleaned and cleaned not in terms:
                terms.append(cleaned)

        for alias in self.aliases:
            variants = [variant for variant in alias.variants if _usable_acronym(variant)]
            phrases = [alias.canonical, *variants]
            if any(_contains_phrase(original_query, phrase) for phrase in phrases):
                add(alias.canonical)
                for variant in variants:
                    if _contains_phrase(original_query, variant):
                        add(variant)
        for title in matched_titles:
            add(title)
        for token in self._meaningful_tokens(original_query):
            add(token)
        for token in self._meaningful_tokens(normalised_query):
            add(token)
        if not terms:
            add(normalised_query or original_query or "query")
        return terms

    def _matching_titles(self, original_query: str, normalised_query: str) -> list[str]:
        query_tokens = set(self._meaningful_tokens(f"{original_query} {normalised_query}"))
        query_phrase = _phrase_text(normalised_query)
        matches: list[tuple[float, int, str]] = []
        for index, title in enumerate(self.page_titles):
            title_phrase = _phrase_text(title)
            title_tokens = set(self._meaningful_tokens(title))
            overlap = len(query_tokens & title_tokens)
            exact = bool(title_phrase and title_phrase in query_phrase)
            if not exact and overlap < 2:
                continue
            score = 100.0 if exact else 10.0 + overlap / max(len(title_tokens), 1)
            matches.append((score, index, title))
        matches.sort(key=lambda item: (-item[0], item[1], item[2].casefold()))
        return [title for _score, _index, title in matches[:8]]

    @staticmethod
    def _context_values(request: QueryInput, query: str) -> dict[str, str]:
        del query
        return {
            key.strip().casefold(): _normalise_context(value)
            for key, value in request.context.items()
            if key.strip() and value.strip()
        }

    def _meaningful_tokens(self, text: str) -> list[str]:
        tokens: list[str] = []
        for raw in re.findall(r"[A-Za-z]+(?:&[A-Za-z]+)?", text):
            letters = sum(character.isalpha() for character in raw)
            if letters < 3:
                continue
            token = raw.casefold()
            if token in self._stop_words:
                continue
            if token not in tokens:
                tokens.append(token)
        return tokens


def _replace_phrase(text: str, phrase: str, replacement: str) -> str:
    pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)", re.IGNORECASE)
    return pattern.sub(replacement, text)


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.IGNORECASE))


def _normalise_punctuation(text: str) -> str:
    return re.sub(r"[‐‑‒–—]", "-", text)


def _normalise_context(value: str) -> str:
    return " ".join(value.strip().upper().replace("-", "_").split()).replace(" ", "_")


def _phrase_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9&]+", text.casefold()))


def _usable_acronym(value: str) -> bool:
    letters = "".join(character for character in value if character.isalpha())
    return (
        (len(letters) >= 3 or "&" in value)
        and letters.casefold() not in EventQueryPlanner._common_acronym_words
        and bool(re.fullmatch(r"[A-Za-z& -]+", value))
    )
