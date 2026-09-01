"""TF-IDF retrieval contract tests."""

from pathlib import Path

from riskon.ingestion import load_synthetic_sections
from riskon.retrieval import SectionRetriever

DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def _retriever() -> SectionRetriever:
    return SectionRetriever(load_synthetic_sections(DATA_ROOT))


def test_retrieval_configuration_is_exact() -> None:
    retriever = _retriever()
    assert retriever.vectorizer.lowercase is True
    assert retriever.vectorizer.stop_words == "english"
    assert retriever.vectorizer.ngram_range == (1, 2)
    assert retriever.vectorizer.norm == "l2"
    assert retriever.top_k == 5


def test_direct_and_table_queries_choose_expected_page() -> None:
    retriever = _retriever()
    direct = retriever.retrieve("Product Familiarity Record delegated order giver")
    assert direct[0].source_ref == "local://synthetic/delegated_order_giver.html"
    table = retriever.retrieve("alert matrix control type rows")
    assert table[0].source_ref == "local://synthetic/alert_matrix.html"
    assert table[0].table_rows[0] == ["Concentration", "Open", "Manual review"]


def test_irrelevant_query_fails_minimum_evidence_gate() -> None:
    retriever = _retriever()
    hits = retriever.retrieve("zebra quantum telescope")
    assert hits[0].score < 0.10
    assert retriever.relevant(hits) == []
    assert retriever.retrieve("") == []


def test_ranking_is_deterministic() -> None:
    retriever = _retriever()
    first = [hit.model_dump(mode="json") for hit in retriever.retrieve("regional scope policy")]
    second = [hit.model_dump(mode="json") for hit in retriever.retrieve("regional scope policy")]
    assert first == second
