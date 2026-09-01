"""Defensive redaction for content crossing into the static demo surface."""

from __future__ import annotations

import re
import unicodedata

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_RE = re.compile(
    r"<\s*(?:script|style)[^>]*>.*?<\s*/\s*(?:script|style)\s*>", re.DOTALL | re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]*>")
_URL_RE = re.compile(r"(?i)\bhttps?://[^\s<>\"']+")
_ABSOLUTE_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])/(?:Users|Volumes|private|tmp|var)/[^\s<>\"']*")
_SOURCE_INSTRUCTION_RE = re.compile(
    r"(?i)\b(?:ignore|disregard)\s+(?:all\s+)?(?:previous|earlier)\s+instructions\b"
    r"|\b(?:system|developer|assistant)\s+message\s*:"
    r"|\bprompt\s+injection\b"
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_text(value: str, *, maximum_characters: int | None = None) -> str:
    """Return display text with tags, URLs, paths, and source instructions removed."""

    text = unicodedata.normalize("NFKC", str(value))
    text = _BLOCK_RE.sub(" ", text)
    text = _COMMENT_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = _SOURCE_INSTRUCTION_RE.sub("[source instruction omitted]", text)
    text = _URL_RE.sub("[external reference omitted]", text)
    text = _ABSOLUTE_PATH_RE.sub("[path omitted]", text)
    text = _CONTROL_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if maximum_characters is not None:
        if maximum_characters < 1:
            raise ValueError("maximum_characters must be positive")
        if len(text) > maximum_characters:
            text = text[: maximum_characters - 1].rstrip() + "…"
    return text


def sanitize_excerpt(value: str, maximum_characters: int = 280) -> str:
    """Sanitize a source excerpt under the ER-B evidence length cap."""

    return sanitize_text(value, maximum_characters=maximum_characters)


def sanitize_reference(value: str) -> str:
    """Allow only local synthetic provenance references in the rendered demo."""

    reference = sanitize_text(value)
    allowed_prefixes = (
        "local://synthetic-m4/",
        "local://synthetic-m4d/",
        "local://synthetic-m5a/",
        "local://knowledge-overlay/",
        "local://event-corpus/",
    )
    if reference.startswith(allowed_prefixes):
        return reference
    return "[local provenance omitted]"


def safe_scope(values: dict[str, object]) -> dict[str, str]:
    """Keep only scalar, non-empty structured context labels."""

    result: dict[str, str] = {}
    for key, value in values.items():
        if value is None or value == "":
            continue
        if isinstance(value, (str, int, float, bool)):
            result[sanitize_text(key)] = sanitize_text(str(value))
    return result
