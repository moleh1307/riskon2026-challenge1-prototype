"""M2 multi-channel retrieval and fusion tests."""

import json
from pathlib import Path

from riskon.models import QueryInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = PROJECT_ROOT / "data" / "synthetic" / "m2" / "evaluation_cases.json"


def _case(case_id: str) -> dict[str, object]:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    return next(case for case in payload["cases"] if case["id"] == case_id)


def _retrieve(m2_pipeline, case_id: str):
    case = _case(case_id)
    request = QueryInput(query=case["query"], context=case["input_context"])
    plan = m2_pipeline._m2_planner.plan(request)
    context = m2_pipeline._m2_planner.context_values(request, plan)
    return plan, m2_pipeline._m2_retriever.retrieve(plan, context)


def test_fixed_word_and_character_channels_are_configured_exactly(m2_pipeline) -> None:
    retriever = m2_pipeline._m2_retriever
    assert retriever._word_vectorizer.analyzer == "word"
    assert retriever._word_vectorizer.lowercase is True
    assert retriever._word_vectorizer.stop_words == "english"
    assert retriever._word_vectorizer.ngram_range == (1, 2)
    assert retriever._word_vectorizer.norm == "l2"
    assert retriever._char_vectorizer.analyzer == "char_wb"
    assert retriever._char_vectorizer.ngram_range == (3, 5)
    assert retriever._char_vectorizer.norm == "l2"


def test_typo_acronym_scope_and_definition_queries_choose_expected_top1(m2_pipeline) -> None:
    expected = {
        "M2-013": "local://synthetic-m2/emitter_density_workflows.html#section-interactive-session",
        "M2-014": "local://synthetic-m2/acronym_registry.html#section-advisory-review-code",
        "M2-015": "local://synthetic-m2/control_delta_region_beta.html#section-service-basic",
        "M2-020": "local://synthetic-m2/suitable_proposal_definition.html#section-definition",
    }
    for case_id, expected_ref in expected.items():
        plan, retrieval = _retrieve(m2_pipeline, case_id)
        subquery = plan.subqueries[0] if plan.subqueries else plan.normalised_query
        assert retrieval.final_candidates[subquery][0].candidate_ref == expected_ref


def test_rrf_order_is_deterministic(m2_pipeline) -> None:
    plan, first = _retrieve(m2_pipeline, "M2-015")
    _, second = _retrieve(m2_pipeline, "M2-015")
    first_refs = [item.candidate_ref for item in first.final_candidates[plan.normalised_query]]
    second_refs = [item.candidate_ref for item in second.final_candidates[plan.normalised_query]]
    assert first_refs == second_refs
    assert first.diagnostics == second.diagnostics
