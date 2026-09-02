"""Confluence status-icon extraction; meanings belong to the page legend."""

from __future__ import annotations

from typing import Literal

from lxml.html import HtmlElement  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

EMOTICON_TAG = "ac:emoticon"
IMAGE_TAG = "ac:image"
URL_TAG = "ri:url"
ICON_URL_MARKER = "/icons/emoticons/"

KNOWN_EMOTICON_NAMES = frozenset(
    {
        "smile",
        "sad",
        "cheeky",
        "laugh",
        "wink",
        "thumbs-up",
        "thumbs-down",
        "information",
        "tick",
        "cross",
        "warning",
        "plus",
        "minus",
        "question",
        "light-on",
        "light-off",
        "yellow-star",
        "red-star",
        "green-star",
        "blue-star",
    }
)
KNOWN_IMAGE_ICON_NAMES = frozenset({"error", "check", "warning", "information", "tick"})
Encoding = Literal["emoticon", "emoji", "image"]


class Icon(BaseModel):
    """Raw icon state, including the encoding and source attribute."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    encoding: Encoding
    raw: str
    known: bool


def is_known(name: str, encoding: Encoding) -> bool:
    if encoding == "emoji":
        return True
    if encoding == "image":
        return name in KNOWN_IMAGE_ICON_NAMES
    return name in KNOWN_EMOTICON_NAMES


def _from_emoticon(element: HtmlElement) -> Icon | None:
    name = element.get("ac:name")
    if name is None:
        return None
    encoding: Encoding = "emoji" if element.get("ac:emoji-id") else "emoticon"
    return Icon(name=name, encoding=encoding, raw=name, known=is_known(name, encoding))


def _from_image(element: HtmlElement) -> Icon | None:
    url = next(
        (node.get("ri:value") for node in element.iter(URL_TAG) if node.get("ri:value")),
        None,
    )
    if url is None or ICON_URL_MARKER not in url:
        return None
    stem = url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    alt = (element.get("ac:alt") or "").strip()
    name = alt[1:-1] if alt.startswith("(") and alt.endswith(")") else stem
    return Icon(name=name, encoding="image", raw=alt or url, known=is_known(name, "image"))


def icons_in(element: HtmlElement) -> list[Icon]:
    """Return both Confluence encodings while ignoring ordinary content images."""

    found: list[Icon] = []
    for node in element.iter():
        if not isinstance(node.tag, str):
            continue
        if node.tag == EMOTICON_TAG:
            icon = _from_emoticon(node)
        elif node.tag == IMAGE_TAG:
            icon = _from_image(node)
        else:
            icon = None
        if icon is not None:
            found.append(icon)
    return found
