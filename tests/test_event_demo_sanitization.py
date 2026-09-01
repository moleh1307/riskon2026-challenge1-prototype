"""ER-B text and provenance sanitization tests."""

from __future__ import annotations

import pytest

from riskon.demo.sanitization import sanitize_excerpt, sanitize_reference, sanitize_text


def test_injection_markup_is_removed_before_html_rendering() -> None:
    value = "</script><script>alert('x')</script> safe text"
    sanitized = sanitize_excerpt(value)
    assert "<script" not in sanitized.casefold()
    assert "alert('x')" not in sanitized
    assert "safe text" in sanitized


def test_external_urls_and_absolute_paths_are_redacted() -> None:
    value = "See https://example.test/doc at /Users/melih/private.txt"
    sanitized = sanitize_text(value)
    assert "https://" not in sanitized
    assert "/Users/" not in sanitized
    assert "external reference omitted" in sanitized
    assert "path omitted" in sanitized


def test_only_local_synthetic_references_are_allowed() -> None:
    assert sanitize_reference("local://synthetic-m4d/a.html") == "local://synthetic-m4d/a.html"
    assert sanitize_reference("https://example.test/a") == "[local provenance omitted]"
    assert sanitize_reference("/Users/melih/a.html") == "[local provenance omitted]"


def test_sanitization_enforces_positive_and_bounded_lengths() -> None:
    with pytest.raises(ValueError, match="maximum_characters must be positive"):
        sanitize_text("content", maximum_characters=0)
    assert sanitize_text("abcdef", maximum_characters=4) == "abc…"
