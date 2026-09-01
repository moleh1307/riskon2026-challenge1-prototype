"""Q&A bank rendering tests for the event pitch."""

from __future__ import annotations

from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.qa_renderer import render_qa_item
from riskon.pitch.script_builder import render_qa_bank


def test_qa_renderer_preserves_one_item_verbatim(event_pitch_catalog: PitchCatalog) -> None:
    item = event_pitch_catalog.qa_bank.items[0]
    lines = render_qa_item(item)
    rendered = "\n".join(lines)
    assert item.id in rendered
    assert item.question in rendered
    assert item.answer in rendered
    assert item.source_basis in rendered
    assert f"{item.recommended_seconds}s" in rendered


def test_qa_bank_renders_all_eighteen_topics(event_pitch_catalog: PitchCatalog) -> None:
    rendered = render_qa_bank(event_pitch_catalog)
    for item in event_pitch_catalog.qa_bank.items:
        assert f"## {item.id} — {item.question}" in rendered
        assert f"Source basis: {item.source_basis}" in rendered
    assert rendered.count("## QA-") == 18


def test_qa_bank_is_bounded_and_honest(event_pitch_catalog: PitchCatalog) -> None:
    rendered = render_qa_bank(event_pitch_catalog)
    assert "between 20 and 40 seconds" in rendered
    assert "model-driven autonomous swarm" not in rendered
    assert "calibrated probabilities" in rendered
