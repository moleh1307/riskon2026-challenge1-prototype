"""Cheap preflight checks for non-event and low-information questions."""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"[a-z0-9][a-z0-9&'/-]*", re.IGNORECASE)
_ARITHMETIC = re.compile(
    r"(?:what\s+is\s+(?:the\s+)?)?[\d\s()+\-*/x×÷?.]+",
    re.IGNORECASE,
)
_LOW_SIGNAL = frozenset(
    {
        "hello",
        "hi",
        "hey",
        "okay",
        "ok",
        "ping",
        "test",
        "testing",
        "deneme",
        "selam",
        "merhaba",
        "are you there",
        "is this working",
        "what can you do",
    }
)
_STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "all",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "of",
        "on",
        "or",
        "please",
        "should",
        "that",
        "the",
        "these",
        "this",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "would",
        "you",
        "your",
    }
)

GATE_MESSAGE = (
    "Please ask a specific question about the Julius Baer suitability material, "
    "for example about alerts, suitability, LoD, client classification, or support."
)


def question_gate_message(question: str, pipeline: Any | None = None) -> str | None:
    """Return a clarification message for obvious non-event input, if any."""

    normalized = " ".join(question.split()).casefold()
    if not normalized:
        return GATE_MESSAGE
    if _ARITHMETIC.fullmatch(normalized) or normalized in _LOW_SIGNAL:
        return GATE_MESSAGE

    question_terms = {
        token
        for token in _TOKEN.findall(normalized)
        if token not in _STOP_WORDS and len(token) >= 3
    }
    if not question_terms:
        return GATE_MESSAGE

    corpus_terms = _corpus_terms(pipeline)
    if corpus_terms and not question_terms.intersection(corpus_terms):
        return GATE_MESSAGE
    return None


def _corpus_terms(pipeline: Any | None) -> set[str]:
    """Build a small vocabulary from local titles and verified aliases only."""

    corpus = getattr(pipeline, "_m4d_corpus", None)
    sections = getattr(corpus, "sections", ())
    values: list[str] = [getattr(section, "title", "") for section in sections]
    retriever = getattr(pipeline, "_m4d_retriever", None)
    for alias in getattr(retriever, "aliases", ()):
        values.extend(
            [
                getattr(alias, "canonical", ""),
                *getattr(alias, "variants", []),
            ]
        )
    return {
        token
        for value in values
        for token in _TOKEN.findall(str(value).casefold())
        if token not in _STOP_WORDS and len(token) >= 3
    }
