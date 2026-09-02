"""Event-only retrieval entry point over the frozen hybrid retriever."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence

from riskon.config import M2RetrievalConfig
from riskon.event_runtime.aliases import EventAlias
from riskon.event_structure.references import ReferenceGraph
from riskon.hybrid_retrieval import HybridRetriever, RetrievalCandidate
from riskon.models import RetrievalChannel, Section
from riskon.provenance import ProvenanceIndex


class EventHybridRetriever(HybridRetriever):
    """Keep event retrieval isolated from generic synthetic M2 behavior."""

    _stop_words = frozenset(
        {
            "a",
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

    def __init__(
        self,
        sections: list[Section],
        provenance: ProvenanceIndex,
        config: M2RetrievalConfig,
        *,
        aliases: Sequence[EventAlias] = (),
        reference_graph: ReferenceGraph | None = None,
        title_boost_enabled: bool = False,
        document_diversity_enabled: bool = False,
    ) -> None:
        self.aliases = tuple(aliases)
        self.title_boost_enabled = title_boost_enabled
        self.document_diversity_enabled = document_diversity_enabled
        self._alias_patterns = tuple(
            (
                re.compile(rf"(?<!\w){re.escape(variant)}(?!\w)", re.IGNORECASE),
                alias.canonical,
            )
            for alias in self.aliases
            for variant in sorted(alias.variants, key=len, reverse=True)
            if _usable_acronym(variant)
        )
        self._link_texts_by_section = {
            section.section_id: tuple(
                dict.fromkeys(link.text for link in section.links if link.text)
            )
            for section in sections
        }
        self._parent_sources_by_target = _build_parent_sources(sections, reference_graph)
        super().__init__(sections, provenance, config)
        self._source_anchor_refs = {
            source_ref: min(
                candidate.candidate_ref
                for candidate in self.candidates
                if candidate.source_ref == source_ref
            )
            for source_ref in {candidate.source_ref for candidate in self.candidates}
        }
        self._token_document_frequency = _document_frequency(self.candidates)
        self._candidate_title_text = {
            candidate.candidate_ref: self._expand_aliases(
                " ".join([candidate.title, *candidate.heading_path])
            )
            for candidate in self.candidates
        }
        self._title_signal_cache: dict[str, dict[str, float]] = {}
        self._link_signal_cache: dict[str, dict[str, float]] = {}
        self._graph_signal_cache: dict[str, dict[str, float]] = {}

    def _score_channel(
        self,
        channel: RetrievalChannel,
        query: str,
    ) -> list[tuple[RetrievalCandidate, float]]:
        scored = super()._score_channel(channel, query)
        if not self.title_boost_enabled:
            return scored
        scale = {
            RetrievalChannel.EXACT: 3.0,
            RetrievalChannel.TABLE_ROW: 3.0,
            RetrievalChannel.WORD_TFIDF: 0.22,
            RetrievalChannel.CHAR_TFIDF: 0.22,
        }[channel]
        signals = self._title_signals(query)
        link_signals = self._link_signals(query)
        graph_signals = self._graph_signals(query)
        boosted = [
            (
                candidate,
                score
                + scale * signals.get(candidate.candidate_ref, 0.0)
                + scale * link_signals.get(candidate.candidate_ref, 0.0)
                + scale * graph_signals.get(candidate.candidate_ref, 0.0),
            )
            for candidate, score in scored
        ]
        if not self.document_diversity_enabled or channel is RetrievalChannel.TABLE_ROW:
            return boosted
        best_by_source: dict[str, tuple[RetrievalCandidate, float]] = {}
        for candidate, score in boosted:
            if candidate.is_table_row:
                continue
            current = best_by_source.get(candidate.source_ref)
            if current is None or (score, candidate.candidate_ref) > (
                current[1],
                current[0].candidate_ref,
            ):
                best_by_source[candidate.source_ref] = (candidate, score)
        return list(best_by_source.values())

    def _link_signals(self, query: str) -> dict[str, float]:
        cached = self._link_signal_cache.get(query)
        if cached is not None:
            return cached
        query_tokens = self._ordered_tokens(self._expand_aliases(query))
        signals: dict[str, float] = {}
        for candidate in self.candidates:
            if candidate.is_table_row or candidate.candidate_ref != self._source_anchor_refs.get(
                candidate.source_ref
            ):
                continue
            best = 0.0
            for link_text in self._link_texts_by_section.get(candidate.section_id or "", ()):
                link_tokens = self._ordered_tokens(link_text)
                match = _longest_contiguous_match(link_tokens, query_tokens)
                if match >= 3:
                    best = max(best, 2.0)
                elif match == 2 and _specific_link_pair(
                    link_tokens,
                    query_tokens,
                    self._token_document_frequency,
                ):
                    best = max(best, 1.5)
            if best:
                signals[candidate.candidate_ref] = best
        self._link_signal_cache[query] = signals
        return signals

    def _graph_signals(self, query: str) -> dict[str, float]:
        cached = self._graph_signal_cache.get(query)
        if cached is not None:
            return cached
        title_signals = self._title_signals(query)
        source_title_signals: dict[str, float] = defaultdict(float)
        for candidate in self.candidates:
            source_title_signals[candidate.source_ref] = max(
                source_title_signals[candidate.source_ref],
                title_signals.get(candidate.candidate_ref, 0.0),
            )
        signals: dict[str, float] = {}
        for target, parents in self._parent_sources_by_target.items():
            target_title_signal = source_title_signals.get(target, 0.0)
            if target_title_signal < 2.0:
                continue
            support = max(
                (source_title_signals.get(parent, 0.0) for parent in parents),
                default=0.0,
            )
            if support < 2.0:
                continue
            anchor = self._source_anchor_refs.get(target)
            if anchor is not None:
                signals[anchor] = 0.5 * support
        self._graph_signal_cache[query] = signals
        return signals

    def _title_signals(self, query: str) -> dict[str, float]:
        cached = self._title_signal_cache.get(query)
        if cached is not None:
            return cached
        query_text = self._expand_aliases(query)
        query_phrase = _phrase_text(query_text)
        query_tokens = self._tokens(query_text)
        signals = {
            candidate_ref: self._title_signal_for_text(
                title_text,
                query_phrase,
                query_tokens,
            )
            for candidate_ref, title_text in self._candidate_title_text.items()
        }
        self._title_signal_cache[query] = signals
        return signals

    def _title_signal_for_text(
        self,
        title_text: str,
        query_phrase: str,
        query_tokens: set[str],
    ) -> float:
        title_phrase = _phrase_text(title_text)
        if not query_phrase or not title_phrase:
            return 0.0
        if title_phrase in query_phrase:
            return 100.0
        if query_phrase in title_phrase:
            return 80.0
        title_tokens = self._tokens(title_text)
        if not query_tokens or not title_tokens:
            return 0.0
        overlap = query_tokens & title_tokens
        if not overlap:
            return 0.0
        title_coverage = len(overlap) / len(title_tokens)
        query_coverage = len(overlap) / len(query_tokens)
        return 8.0 * title_coverage + 4.0 * query_coverage

    def _expand_aliases(self, value: str) -> str:
        result = value
        for pattern, canonical in self._alias_patterns:
            result = pattern.sub(canonical, result)
        return result

    def _tokens(self, value: str) -> set[str]:
        return set(self._ordered_tokens(value))

    def _ordered_tokens(self, value: str) -> list[str]:
        tokens: list[str] = []
        for token in re.findall(r"[A-Za-z0-9]+", value.casefold()):
            if len(token) < 3 or token in self._stop_words:
                continue
            singular = _singularise(token)
            if singular not in tokens:
                tokens.append(singular)
        return tokens


def _phrase_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _usable_acronym(value: str) -> bool:
    letters = "".join(character for character in value if character.isalpha())
    return len(letters) >= 3 or "&" in value


def _singularise(value: str) -> str:
    if len(value) > 4 and value.endswith("s"):
        return value[:-1]
    return value


def _build_parent_sources(
    sections: Sequence[Section],
    reference_graph: ReferenceGraph | None = None,
) -> dict[str, set[str]]:
    parents: dict[str, set[str]] = defaultdict(set)
    for section in sections:
        for link in section.links:
            match = re.search(r"(?:pageId=|/pages/)(\d+)", link.href)
            if match:
                target = f"local://event-wiki/{match.group(1)}.html"
                parents[target].add(section.source_ref)
    if reference_graph is not None:
        source_by_page = {
            section.filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]: section.source_ref
            for section in sections
        }
        for source_page, target_page in reference_graph.edges:
            source_ref = source_by_page.get(source_page)
            target_ref = source_by_page.get(target_page)
            if source_ref is not None and target_ref is not None:
                parents[target_ref].add(source_ref)
    return dict(parents)


def _document_frequency(candidates: Sequence[RetrievalCandidate]) -> dict[str, int]:
    terms_by_source: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        terms_by_source[candidate.source_ref].update(
            re.findall(r"[a-z0-9]+", HybridRetriever._document(candidate))
        )
    frequency: dict[str, int] = defaultdict(int)
    for terms in terms_by_source.values():
        for term in terms:
            frequency[term] += 1
    return dict(frequency)


def _longest_contiguous_match(left: Sequence[str], right: Sequence[str]) -> int:
    longest = 0
    for left_index in range(len(left)):
        for right_index in range(len(right)):
            length = 0
            while (
                left_index + length < len(left)
                and right_index + length < len(right)
                and left[left_index + length] == right[right_index + length]
            ):
                length += 1
            longest = max(longest, length)
    return longest


def _specific_link_pair(
    link_tokens: Sequence[str],
    query_tokens: Sequence[str],
    document_frequency: dict[str, int],
) -> bool:
    for link_index in range(len(link_tokens) - 1):
        for query_index in range(len(query_tokens) - 1):
            if (
                link_tokens[link_index : link_index + 2]
                != query_tokens[query_index : query_index + 2]
            ):
                continue
            return any(
                document_frequency.get(token, 10**9) <= 15
                for token in link_tokens[link_index : link_index + 2]
            )
    return False
