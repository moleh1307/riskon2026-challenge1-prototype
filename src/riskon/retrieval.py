"""Deterministic TF-IDF section retrieval."""

from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]

from riskon.models import RetrievalHit, Section


class SectionRetriever:
    """Index heading-scoped sections with the fixed M0 retrieval contract."""

    def __init__(
        self,
        sections: list[Section],
        top_k: int = 5,
        minimum_score: float = 0.10,
        ngram_range: tuple[int, int] = (1, 2),
    ) -> None:
        if not sections:
            raise ValueError("At least one section is required")
        self.sections = sections
        self.top_k = top_k
        self.minimum_score = minimum_score
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=ngram_range,
            norm="l2",
        )
        self._matrix: Any = self.vectorizer.fit_transform(section.text for section in sections)

    def retrieve(self, query: str) -> list[RetrievalHit]:
        """Return top-k candidates with stable score/section-id ordering."""

        if not query.strip():
            return []
        query_vector = self.vectorizer.transform([query])
        raw_scores = (self._matrix @ query_vector.T).toarray().ravel()
        ranked = sorted(
            enumerate(raw_scores),
            key=lambda item: (-float(item[1]), self.sections[item[0]].section_id),
        )
        hits: list[RetrievalHit] = []
        for index, raw_score in ranked[: self.top_k]:
            section = self.sections[index]
            hits.append(
                RetrievalHit(
                    section_id=section.section_id,
                    source_ref=section.source_ref,
                    title=section.title,
                    heading_path=section.heading_path,
                    score=float(raw_score),
                    excerpt=section.text,
                    table_rows=[row for table in section.tables for row in table.rows],
                )
            )
        return hits

    def relevant(self, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        """Filter candidates through the configured minimum score."""

        return [hit for hit in hits if hit.score >= self.minimum_score]
