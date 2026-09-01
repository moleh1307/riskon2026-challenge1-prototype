"""Render the frozen Q&A items as concise presenter cues."""

from __future__ import annotations

from riskon.pitch.models import QAItem


def render_qa_item(item: QAItem) -> list[str]:
    """Render one Q&A item without changing its contract wording."""

    return [
        f"## {item.id} — {item.question}",
        "",
        f"**Recommended answer ({item.recommended_seconds}s):** {item.answer}",
        "",
        f"Source basis: {item.source_basis}",
        "",
    ]
