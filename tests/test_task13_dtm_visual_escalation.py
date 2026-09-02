"""Task 13 regression tests for DTM source limits and visual escalation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from riskon.event_runtime.corpus_loader import ingest_event_sections
from riskon.event_runtime.evidence_reasoning import (
    EventEvidenceReasoningRuntime,
    _build_source_limit_claim,
)
from riskon.event_runtime.evidence_reasoning_models import (
    ContextAssessment,
    EvidenceAnalysisOutput,
    EvidenceSufficiencyStatus,
    EvidenceUnit,
)
from riskon.event_runtime.structural_matrix import SourceGapWorker
from riskon.event_runtime.visual_scout import should_run_visual_scout
from riskon.event_structure.adapter import attach_structural_tables, build_structural_event_corpus
from riskon.models import ManifestEntry, QueryInput
from riskon.orchestra.source_safety import LocalCorpus
from riskon.provenance import ProvenanceIndex


def _corpus(
    tmp_path: Path,
    *,
    with_missing_matrix_asset: bool = False,
    with_explicit_trade_basic_rule: bool = False,
) -> LocalCorpus:
    matrix = (
        "<h2>DTM Matrix</h2><p><ac:image><ri:attachment "
        'ri:filename="missing-dtm-matrix.png"/></ac:image></p>'
        if with_missing_matrix_asset
        else ""
    )
    explicit = (
        "<p>The JB DTM applies to Trade Basic Service Models.</p>"
        if with_explicit_trade_basic_rule
        else ""
    )
    source = tmp_path / "dtm.html"
    source.write_text(
        "<html><body>"
        "<h2>Application</h2><p>DTM overview.</p>"
        "<h2>Scope</h2><p>The JB DTM applies to all Advisory Service Models "
        "and for all solicitation types.</p>"
        f"{explicit}{matrix}"
        "</body></html>",
        encoding="utf-8",
    )
    entry = ManifestEntry(
        filename="dtm.html",
        title="JB Distributor Target Market Concept",
        url="local://event-wiki/dtm.html",
        source_path=str(source),
    )
    structural = build_structural_event_corpus([entry])
    sections = attach_structural_tables(ingest_event_sections([entry]), structural)
    return LocalCorpus(
        sections=tuple(sections),
        provenance=ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2"),
        knowledge_root=tmp_path,
        structural=structural,
    )


def _retrieval(source_ref: str) -> SimpleNamespace:
    candidate = SimpleNamespace(source_ref=source_ref, unit_refs=())
    return SimpleNamespace(
        hybrid_page_refs=(source_ref,),
        selected_candidates=(candidate,),
        deterministic_result=SimpleNamespace(selected_candidates=(candidate,)),
    )


def _runtime(corpus: LocalCorpus) -> EventEvidenceReasoningRuntime:
    return EventEvidenceReasoningRuntime(corpus, object(), object(), object())  # type: ignore[arg-type]


def test_no_direct_text_support_does_not_trigger_visual_scout() -> None:
    analysis = EvidenceAnalysisOutput(
        evidence_sufficiency=EvidenceSufficiencyStatus.NO_DIRECT_SUPPORT,
        material_claims=[],
        unresolved_issues=["The selected text does not support the requested extension."],
    )
    unit = EvidenceUnit(
        evidence_ref="local://event-wiki/dtm.html#section-scope:sentence-1",
        kind="sentence",
        source_ref="local://event-wiki/dtm.html",
        title="DTM",
        filename="dtm.html",
        text="The JB DTM applies to Advisory Service Models.",
    )

    assert not should_run_visual_scout(analysis, [unit])


def test_visual_required_missing_asset_is_preserved_but_unrelated_gap_is_ignored(
    tmp_path: Path,
) -> None:
    corpus = _corpus(tmp_path, with_missing_matrix_asset=True)
    runtime = _runtime(corpus)
    retrieval = _retrieval("local://event-wiki/dtm.html")
    scope = next(section for section in corpus.sections if section.heading_path[-1] == "Scope")
    matrix = next(
        section for section in corpus.sections if section.heading_path[-1] == "DTM Matrix"
    )
    scope_unit = corpus.provenance.resolve(corpus.provenance.section_ref(scope))
    matrix_unit = corpus.provenance.resolve(corpus.provenance.section_ref(matrix))
    assert scope_unit is not None
    assert matrix_unit is not None

    assert not runtime._source_package_asset_unavailable(
        retrieval,
        evidence_units=[runtime._evidence_unit(scope_unit, scope_unit.text, False)],
    )
    assert runtime._source_package_asset_unavailable(
        retrieval,
        evidence_units=[runtime._evidence_unit(matrix_unit, matrix_unit.text, False)],
    )
    assert (
        SourceGapWorker(corpus)
        .evaluate(
            ["local://event-wiki/dtm.html"],
            relevant_evidence_refs=[matrix_unit.ref],
        )
        .firewall_code
        == "SOURCE_PACKAGE_ASSET_UNAVAILABLE"
    )


def test_category_a_only_yields_a_valid_source_limit_claim(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    runtime = _runtime(corpus)
    request = QueryInput(query="Does DTM also apply for Trade Basic Service Model?")
    claim_and_unit = _build_source_limit_claim(
        request,
        _retrieval("local://event-wiki/dtm.html"),
        corpus,
    )

    assert claim_and_unit is not None
    claim, source_unit = claim_and_unit
    validation = runtime._validate_claims(
        request,
        ContextAssessment(intent="APPLICABILITY"),
        EvidenceAnalysisOutput(
            evidence_sufficiency=EvidenceSufficiencyStatus.SUFFICIENT,
            material_claims=[claim],
            unresolved_issues=[],
        ),
        [runtime._evidence_unit(source_unit, source_unit.text, False)],
    )

    assert validation.valid_claims == [claim]
    assert validation.unsupported_claim_count == 0
    assert "does not establish" in claim.claim_text
    assert "Trade Basic must not be mapped to Advisory" in claim.claim_text


def test_explicit_trade_basic_rule_blocks_source_limit_fallback(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path, with_explicit_trade_basic_rule=True)
    request = QueryInput(query="Does DTM also apply for Trade Basic Service Model?")

    assert (
        _build_source_limit_claim(request, _retrieval("local://event-wiki/dtm.html"), corpus)
        is None
    )


def test_missing_authority_does_not_create_a_source_limit_claim(tmp_path: Path) -> None:
    source = tmp_path / "unrelated.html"
    source.write_text(
        "<html><body><h2>Unrelated</h2><p>This page discusses advisory service models.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    entry = ManifestEntry(
        filename="unrelated.html",
        title="Unrelated",
        url="local://event-wiki/unrelated.html",
        source_path=str(source),
    )
    structural = build_structural_event_corpus([entry])
    sections = attach_structural_tables(ingest_event_sections([entry]), structural)
    corpus = LocalCorpus(
        sections=tuple(sections),
        provenance=ProvenanceIndex(sections, knowledge_root=tmp_path, ref_style="m2"),
        knowledge_root=tmp_path,
        structural=structural,
    )

    assert (
        _build_source_limit_claim(
            QueryInput(query="Does DTM also apply for Trade Basic Service Model?"),
            _retrieval("local://event-wiki/unrelated.html"),
            corpus,
        )
        is None
    )
