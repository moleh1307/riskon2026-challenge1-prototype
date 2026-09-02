"""Deterministic M2 multi-channel retrieval and context filtering."""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]

from riskon.config import M2RetrievalConfig
from riskon.models import (
    QueryIntent,
    QueryPlan,
    RetrievalChannel,
    RetrievalDiagnostics,
    Section,
)
from riskon.provenance import ProvenanceIndex, ProvenanceUnit
from riskon.retrieval_diagnostics import (
    ChannelObservation,
    build_diagnostics,
)


@dataclass(frozen=True)
class RetrievalCandidate:
    """One section, table row, or local attachment candidate."""

    candidate_ref: str
    section_id: str | None
    source_ref: str
    title: str
    heading_path: tuple[str, ...]
    excerpt: str
    table_rows: tuple[tuple[str, ...], ...]
    unit_refs: tuple[str, ...]
    claim_ids: tuple[str, ...]
    scope: tuple[tuple[str, str], ...]
    is_table_row: bool
    is_attachment: bool

    @property
    def scope_dict(self) -> dict[str, str]:
        return dict(self.scope)


@dataclass(frozen=True)
class HybridRetrievalResult:
    """Final M2 candidates by subquery plus selected answer evidence."""

    final_candidates: dict[str, tuple[RetrievalCandidate, ...]]
    selected_candidates: tuple[RetrievalCandidate, ...]
    diagnostics: RetrievalDiagnostics


class HybridRetriever:
    """Fuse exact, word, character, and table-row channels with deterministic RRF."""

    def __init__(
        self,
        sections: list[Section],
        provenance: ProvenanceIndex,
        config: M2RetrievalConfig,
    ) -> None:
        if not sections:
            raise ValueError("At least one M2 section is required")
        self.sections = sections
        self.provenance = provenance
        self.config = config
        self.candidates = self._build_candidates()
        self._candidate_by_ref = {item.candidate_ref: item for item in self.candidates}
        self._section_candidates = [item for item in self.candidates if not item.is_table_row]
        self._word_vectorizer = TfidfVectorizer(
            analyzer="word",
            lowercase=config.word_tfidf.lowercase,
            stop_words=config.word_tfidf.stop_words,
            ngram_range=(config.word_tfidf.ngram_min, config.word_tfidf.ngram_max),
            norm="l2",
        )
        self._char_vectorizer = TfidfVectorizer(
            analyzer=config.char_tfidf.analyzer or "char_wb",
            lowercase=config.char_tfidf.lowercase,
            ngram_range=(config.char_tfidf.ngram_min, config.char_tfidf.ngram_max),
            norm="l2",
        )
        documents = [self._document(item) for item in self.candidates]
        self._word_matrix = self._word_vectorizer.fit_transform(documents)
        self._char_matrix = self._char_vectorizer.fit_transform(documents)

    def retrieve(self, plan: QueryPlan, context: dict[str, str]) -> HybridRetrievalResult:
        """Return fused candidates and a complete channel-level diagnostic trace."""

        subqueries = plan.subqueries or [plan.normalised_query]
        if not plan.canonical_terms:
            return HybridRetrievalResult(
                final_candidates={subquery: () for subquery in subqueries},
                selected_candidates=(),
                diagnostics=RetrievalDiagnostics(),
            )
        all_observations: list[ChannelObservation] = []
        all_rrf: dict[tuple[str, RetrievalChannel, str], float] = {}
        all_final_ranks: dict[tuple[str, str], int] = {}
        all_included: set[tuple[str, str]] = set()
        all_exclusions: dict[tuple[str, str], str] = {}
        final_by_subquery: dict[str, tuple[RetrievalCandidate, ...]] = {}
        selected: list[RetrievalCandidate] = []

        for subquery in subqueries:
            channel_results: dict[RetrievalChannel, list[tuple[RetrievalCandidate, float]]] = {}
            candidate_conflicts: set[str] = set()
            for channel in plan.retrieval_channels:
                scored = self._score_channel(channel, subquery)
                ranked = sorted(
                    scored,
                    key=lambda item: (-item[1], item[0].candidate_ref),
                )
                ranked = [(candidate, score) for candidate, score in ranked if score > 0.0]
                channel_results[channel] = ranked
                for rank, (candidate, score) in enumerate(ranked, start=1):
                    all_observations.append(
                        ChannelObservation(
                            plan_id=plan.plan_id,
                            subquery=subquery,
                            channel=channel,
                            candidate_ref=candidate.candidate_ref,
                            channel_rank=rank,
                            raw_score=float(score),
                        )
                    )
                    if self._context_conflict(candidate, plan, context, subquery):
                        candidate_conflicts.add(candidate.candidate_ref)

            fused: dict[str, float] = {}
            for channel, ranked in channel_results.items():
                weight = self._weight(channel)
                for rank, (candidate, _score) in enumerate(ranked, start=1):
                    if candidate.candidate_ref in candidate_conflicts:
                        all_exclusions[(subquery, candidate.candidate_ref)] = "CONTEXT_CONFLICT"
                        continue
                    contribution = weight / (self.config.rrf_k + rank)
                    key = (subquery, channel, candidate.candidate_ref)
                    all_rrf[key] = contribution
                    fused[candidate.candidate_ref] = (
                        fused.get(candidate.candidate_ref, 0.0) + contribution
                    )

            row_candidates = [
                self._candidate_by_ref[ref]
                for ref in fused
                if self._candidate_by_ref[ref].is_table_row
            ]
            if plan.intent is QueryIntent.CONFIGURATION_LOOKUP and row_candidates:
                allowed_refs = {candidate.candidate_ref for candidate in row_candidates}
                for ref in list(fused):
                    if ref not in allowed_refs:
                        all_exclusions[(subquery, ref)] = "DUPLICATE_EVIDENCE"
                        del fused[ref]

            fused_ranked = sorted(
                ((self._candidate_by_ref[ref], score) for ref, score in fused.items()),
                key=lambda item: (-item[1], item[0].candidate_ref),
            )
            final = tuple(candidate for candidate, _score in fused_ranked[: self.config.top_k])
            final_by_subquery[subquery] = final
            for rank, candidate in enumerate(final, start=1):
                final_key = (subquery, candidate.candidate_ref)
                all_final_ranks[final_key] = rank
                all_included.add(final_key)

            for candidate, _score in fused_ranked[self.config.top_k :]:
                all_final_ranks[(subquery, candidate.candidate_ref)] = len(all_final_ranks) + 1
                all_exclusions.setdefault((subquery, candidate.candidate_ref), "NOT_SELECTED_TOP_K")
            for observation in all_observations:
                if observation.subquery != subquery:
                    continue
                diagnostic_key = (subquery, observation.candidate_ref)
                if observation.raw_score <= 0.0:
                    all_exclusions.setdefault(diagnostic_key, "BELOW_CHANNEL_THRESHOLD")
                elif diagnostic_key not in all_included and diagnostic_key not in all_exclusions:
                    all_exclusions[diagnostic_key] = "NOT_SELECTED_TOP_K"

            if plan.intent is QueryIntent.CONFIGURATION_LOOKUP:
                selected_refs = {item.candidate_ref for item in selected}
                selected.extend(
                    candidate
                    for candidate in final
                    if candidate.is_table_row and candidate.candidate_ref not in selected_refs
                )
            elif final:
                if final[0].candidate_ref not in {item.candidate_ref for item in selected}:
                    selected.append(final[0])

        diagnostics = build_diagnostics(
            all_observations,
            rrf_contributions=all_rrf,
            final_ranks=all_final_ranks,
            included=all_included,
            exclusion_reasons=all_exclusions,
        )
        return HybridRetrievalResult(
            final_candidates=final_by_subquery,
            selected_candidates=tuple(selected),
            diagnostics=diagnostics,
        )

    def _build_candidates(self) -> list[RetrievalCandidate]:
        candidates: list[RetrievalCandidate] = []
        for section in self.sections:
            section_ref = self.provenance.section_ref(section)
            units = self.provenance.units_for_section(section.section_id)
            candidates.append(
                RetrievalCandidate(
                    candidate_ref=section_ref,
                    section_id=section.section_id,
                    source_ref=section.source_ref,
                    title=section.title,
                    heading_path=tuple(section.heading_path),
                    excerpt=section.text,
                    table_rows=tuple(tuple(row) for table in section.tables for row in table.rows),
                    unit_refs=tuple(unit.ref for unit in units),
                    claim_ids=tuple(unit.claim_id for unit in units if unit.claim_id is not None),
                    scope=tuple(sorted(section.scope.items())),
                    is_table_row=False,
                    is_attachment=False,
                )
            )
            address = self.provenance.section_address(section.section_id)
            if address is None:
                continue
            for row_ref in (*address.table_row_refs, *address.structural_row_refs):
                unit = self.provenance.resolve(row_ref)
                if unit is None:
                    continue
                candidates.append(self._candidate_from_unit(unit, section))

        for unit in self.provenance.units.values():
            if unit.kind != "attachment":
                continue
            candidates.append(
                RetrievalCandidate(
                    candidate_ref=unit.ref,
                    section_id=None,
                    source_ref=unit.source_ref,
                    title=unit.filename,
                    heading_path=tuple(unit.heading_path),
                    excerpt=unit.text,
                    table_rows=(),
                    unit_refs=(unit.ref,),
                    claim_ids=(),
                    scope=tuple(sorted(unit.scope.items())),
                    is_table_row=False,
                    is_attachment=True,
                )
            )
        return candidates

    @staticmethod
    def _candidate_from_unit(unit: ProvenanceUnit, section: Section) -> RetrievalCandidate:
        return RetrievalCandidate(
            candidate_ref=unit.ref,
            section_id=section.section_id,
            source_ref=section.source_ref,
            title=section.title,
            heading_path=tuple(section.heading_path),
            excerpt=unit.text,
            table_rows=(tuple(unit.row),),
            unit_refs=(unit.ref,),
            claim_ids=(unit.claim_id,) if unit.claim_id else (),
            scope=tuple(sorted(unit.scope.items())),
            is_table_row=True,
            is_attachment=False,
        )

    def _score_channel(
        self,
        channel: RetrievalChannel,
        query: str,
    ) -> list[tuple[RetrievalCandidate, float]]:
        if channel is RetrievalChannel.EXACT:
            return [
                (candidate, self._exact_score(candidate, query))
                for candidate in self._section_candidates
            ]
        if channel is RetrievalChannel.TABLE_ROW:
            return [
                (candidate, self._exact_score(candidate, query))
                for candidate in self.candidates
                if candidate.is_table_row
            ]
        if channel is RetrievalChannel.WORD_TFIDF:
            matrix = self._word_matrix
            vector = self._word_vectorizer.transform([query])
        else:
            matrix = self._char_matrix
            vector = self._char_vectorizer.transform([query])
        scores = (matrix @ vector.T).toarray().ravel()
        return [
            (candidate, float(scores[index])) for index, candidate in enumerate(self.candidates)
        ]

    @staticmethod
    def _document(candidate: RetrievalCandidate) -> str:
        return " ".join(
            [
                candidate.title,
                " ".join(candidate.heading_path),
                candidate.excerpt,
                " ".join(" ".join(row) for row in candidate.table_rows),
            ]
        ).lower()

    def _exact_score(self, candidate: RetrievalCandidate, query: str) -> float:
        lowered_query = query.lower()
        lowered_document = self._document(candidate)
        score = 0.0
        if lowered_query in lowered_document:
            score += 10.0
        query_terms = [term for term in lowered_query.replace("?", "").split() if len(term) > 2]
        for term in query_terms:
            if term in lowered_document:
                score += 0.25
        if candidate.is_attachment:
            score *= 0.8
        if candidate.heading_path:
            score += sum(
                1.0 for term in query_terms if term in " ".join(candidate.heading_path).lower()
            )
        return score

    def _context_conflict(
        self,
        candidate: RetrievalCandidate,
        plan: QueryPlan,
        context: dict[str, str],
        subquery: str,
    ) -> bool:
        scope = candidate.scope_dict
        for field, expected in context.items():
            actual = scope.get(field)
            if actual is not None and actual.upper() != expected.upper():
                return True
        lowered = subquery.lower()
        if "session" in lowered and scope.get("workflow_stage") == "OVERNIGHT_MONITORING":
            return True
        if "active" in lowered and scope.get("state") == "INACTIVE":
            return True
        if plan.intent is QueryIntent.ALERT_RESOLUTION and "interactive session" in lowered:
            if scope.get("workflow_stage") == "OVERNIGHT_MONITORING":
                return True
        return False

    def _weight(self, channel: RetrievalChannel) -> float:
        weights = self.config.channel_weights
        return {
            RetrievalChannel.EXACT: weights.exact,
            RetrievalChannel.TABLE_ROW: weights.table_row,
            RetrievalChannel.WORD_TFIDF: weights.word_tfidf,
            RetrievalChannel.CHAR_TFIDF: weights.char_tfidf,
        }[channel]
