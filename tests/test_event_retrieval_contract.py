"""Contracts for event-only retrieval and manifest title handling."""

from pathlib import Path

from riskon.config import load_milestone2_config
from riskon.event_runtime.corpus_loader import ingest_event_sections
from riskon.event_runtime.query_planner import EventQueryPlanner
from riskon.event_runtime.retrieval import EventHybridRetriever
from riskon.models import ManifestEntry, QueryInput
from riskon.provenance import ProvenanceIndex
from riskon.query_planning import M4DQueryPlanner


def _event_components(tmp_path: Path) -> tuple[EventQueryPlanner, EventHybridRetriever]:
    source = tmp_path / "guidance.html"
    source.write_text(
        "<html><head><title>HTML implementation title</title></head>"
        "<body><h1>Suitability guidance</h1>"
        "<p>Suitability and appropriateness checks apply before advice.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    entries = [
        ManifestEntry(
            filename="guidance.html",
            title="Suitability and Appropriateness",
            url="local://event-wiki/guidance.html",
            source_path=str(source),
        )
    ]
    sections = ingest_event_sections(entries)
    provenance = ProvenanceIndex(
        sections,
        knowledge_root=tmp_path,
        ref_style="m2",
    )
    config = load_milestone2_config(Path("config/milestone2.toml"))
    planner = EventQueryPlanner.from_aliases(
        aliases=[],
        page_titles=[section.title for section in sections],
        config=config.query_planning,
    )
    return planner, EventHybridRetriever(list(sections), provenance, config.retrieval)


def test_natural_language_event_query_retrieves_without_manual_canonical_term(
    tmp_path: Path,
) -> None:
    planner, retriever = _event_components(tmp_path)
    request = QueryInput(query="Why are suitability and appropriateness checks important?")
    plan = planner.plan(request)

    result = retriever.retrieve(plan, planner.context_values(request, plan))

    assert plan.canonical_terms
    assert result.selected_candidates
    assert result.selected_candidates[0].title == "Suitability and Appropriateness"


def test_manifest_title_is_canonical_and_html_title_is_not_used(tmp_path: Path) -> None:
    planner, retriever = _event_components(tmp_path)
    del planner

    assert retriever.candidates[0].title == "Suitability and Appropriateness"
    assert retriever.candidates[0].title != "HTML implementation title"


def test_event_fix_does_not_replace_the_synthetic_m4d_planner(tmp_path: Path) -> None:
    config = load_milestone2_config(Path("config/milestone2.toml"))
    planner, _retriever = _event_components(tmp_path)
    synthetic = M4DQueryPlanner.from_file(config.alias_registry, config.query_planning)

    assert not isinstance(planner, M4DQueryPlanner)
    assert (
        "synthetic stability marker"
        in synthetic.plan(QueryInput(query="synthetic stability marker")).canonical_terms
    )


def test_production_event_runtime_has_no_golden_case_literals() -> None:
    source_root = Path("src/riskon/event_runtime")
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_root.glob("*.py"))

    for forbidden in (
        "G-01",
        "E-01",
        "Issuer Concentration Risk",
        "Consolidated Product Risk",
        "expected_source",
    ):
        assert forbidden not in source


def test_event_data_remains_untracked() -> None:
    import subprocess

    private = subprocess.run(
        ["git", "ls-files", "data/private"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    generated = subprocess.run(
        ["git", "ls-files", "data/generated"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert private == []
    assert generated in ([], ["data/generated/.gitkeep"])
