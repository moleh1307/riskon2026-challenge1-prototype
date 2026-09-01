"""Extractive answer composition with no unsupported generation."""

from typing import Protocol

from riskon.models import Evidence


class AnswerComposer(Protocol):
    """Composable answer interface for later model-backed milestones."""

    def compose(self, query: str, evidence: list[Evidence]) -> str:
        """Compose a response from admitted evidence only."""


class ExtractiveAnswerComposer:
    """Return deterministic evidence excerpts and preserved table rows."""

    def compose(self, query: str, evidence: list[Evidence]) -> str:
        if not evidence:
            raise ValueError("Extractive answers require evidence")
        del query
        sections: list[str] = []
        for item in evidence:
            heading = " > ".join(item.heading_path) or "Introduction"
            block = f"[{item.title} — {heading}]\n{item.excerpt}"
            if item.table_rows:
                rows = "\n".join(" | ".join(row) for row in item.table_rows)
                block = f"{block}\nTable rows:\n{rows}"
            sections.append(block)
        return "\n\n".join(sections)
