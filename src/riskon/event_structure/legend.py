"""Page-declared meanings for raw Confluence icon states."""

from __future__ import annotations

from lxml.html import HtmlElement  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from riskon.event_structure.icons import EMOTICON_TAG, IMAGE_TAG, icons_in

MIN_LEGEND_ENTRIES = 2
MAX_MEANING_CHARS = 60
MIN_MEANING_LETTERS = 3


class LegendEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    icon: str
    meaning: str


class Legend(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_id: str
    entries: list[LegendEntry] = Field(default_factory=list)
    conflicts: dict[str, list[str]] = Field(default_factory=dict)

    def meaning_of(self, icon: str) -> str | None:
        if icon in self.conflicts:
            return None
        return next((entry.meaning for entry in self.entries if entry.icon == icon), None)

    @property
    def is_empty(self) -> bool:
        return not self.entries


def _text_after(node: HtmlElement) -> str:
    parts: list[str] = [node.tail or ""]
    for sibling in node.itersiblings():
        tag = sibling.tag if isinstance(sibling.tag, str) else ""
        if tag in (EMOTICON_TAG, IMAGE_TAG) or icons_in(sibling):
            break
        parts.append(sibling.text_content() or "")
        parts.append(sibling.tail or "")
    return " ".join(" ".join(parts).split())


def extract_legend(root: HtmlElement, page_id: str) -> Legend:
    """Recognise an icon run outside tables; conflicts remain unresolved."""

    declared: dict[str, list[str]] = {}
    for container in root.iter():
        if not isinstance(container.tag, str) or container.tag == "table":
            continue
        if next(container.iterancestors("table"), None) is not None:
            continue
        run: list[tuple[str, str]] = []
        for child in container.iter():
            if not isinstance(child.tag, str) or child.tag not in (EMOTICON_TAG, IMAGE_TAG):
                continue
            if next(child.iterancestors("table"), None) is not None:
                continue
            icons = icons_in(child)
            if not icons:
                continue
            meaning = _text_after(child)
            if (
                meaning
                and len(meaning) <= MAX_MEANING_CHARS
                and sum(character.isalpha() for character in meaning) >= MIN_MEANING_LETTERS
            ):
                run.append((icons[0].name, meaning))
        if len(run) >= MIN_LEGEND_ENTRIES:
            for icon, meaning in run:
                declared.setdefault(icon, [])
                if meaning not in declared[icon]:
                    declared[icon].append(meaning)
    return Legend(
        page_id=page_id,
        entries=[
            LegendEntry(icon=icon, meaning=meanings[0])
            for icon, meanings in sorted(declared.items())
            if len(meanings) == 1
        ],
        conflicts={icon: meanings for icon, meanings in declared.items() if len(meanings) > 1},
    )
