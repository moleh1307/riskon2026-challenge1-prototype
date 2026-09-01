"""Contracts for the natural-language event query planner."""

import json
from pathlib import Path

from riskon.config import load_milestone2_config
from riskon.event_runtime.query_planner import EventQueryPlanner
from riskon.models import QueryInput


def _planner(tmp_path: Path) -> EventQueryPlanner:
    registry = tmp_path / "event_aliases.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source": "event_corpus",
                "aliases": [
                    {
                        "canonical": "Strategic Asset Allocation",
                        "variants": ["SAA"],
                        "source_ref": "local://event-wiki/saa.html",
                        "extraction_rule": "PAGE_TITLE_PARENTHETICAL",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config = load_milestone2_config(Path("config/milestone2.toml"))
    return EventQueryPlanner.from_file(
        registry,
        page_titles=[
            "Suitability and Appropriateness",
            "Strategic Asset Allocation (SAA)",
        ],
        config=config.query_planning,
    )


def test_event_planner_derives_terms_without_synthetic_vocabulary(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    plan = planner.plan(
        QueryInput(query="Why are Suitability and Appropriateness checks important?")
    )

    assert plan.canonical_terms
    assert "suitability" in plan.canonical_terms
    assert "appropriateness" in plan.canonical_terms
    assert plan.retrieval_skipped is False


def test_event_planner_preserves_acronyms_and_does_not_require_manual_terms(
    tmp_path: Path,
) -> None:
    planner = _planner(tmp_path)
    plan = planner.plan(QueryInput(query="Can a PoA provide instruction for OWN?"))

    assert plan.canonical_terms
    assert "poa" in plan.canonical_terms
    assert "own" in plan.canonical_terms
    assert plan.retrieval_skipped is False


def test_event_planner_expands_aliases_from_registry(tmp_path: Path) -> None:
    planner = _planner(tmp_path)
    plan = planner.plan(QueryInput(query="What explanation resolves an SAA alert?"))

    assert "strategic asset allocation" in plan.canonical_terms
