"""Static leakage checks over the complete generated ER-C text package."""

from __future__ import annotations

import re

from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.validation import CONFIDENTIAL_MARKERS, NETWORK_PATTERN


def test_generated_text_contains_no_paths_contacts_or_confidential_markers(
    event_pitch_build: object,
) -> None:
    root = event_pitch_build.output_root  # type: ignore[attr-defined]
    for path in sorted(root.iterdir()):
        if path.suffix.lower() not in {".html", ".md", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"/(?:Users|Volumes|private/tmp|tmp)/", text)
        assert not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)
        assert not re.search(r"https?://", text)
        assert not NETWORK_PATTERN.search(text)
        assert not any(marker in text.casefold() for marker in CONFIDENTIAL_MARKERS)


def test_speaker_and_source_contracts_remain_role_based(event_pitch_catalog: PitchCatalog) -> None:
    assert event_pitch_catalog.speaker_assignments["real_names_hard_coded"] is False
    assert all("@" not in value for value in event_pitch_catalog.speaker_assignments["profiles"])
    assert event_pitch_catalog.contract.security["real_names_allowed"] is False
    assert event_pitch_catalog.contract.security["absolute_paths_allowed"] is False
