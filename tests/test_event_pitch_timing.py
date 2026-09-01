"""Timing-profile and speaker-script tests for ER-C."""

from __future__ import annotations

import pytest

from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.errors import PitchContractError
from riskon.pitch.script_builder import render_live_demo_script, render_timing_script


@pytest.mark.parametrize("profile_id", ["3_MIN", "5_MIN", "7_MIN"])
def test_every_timing_profile_renders_its_declared_total(
    event_pitch_catalog: PitchCatalog, profile_id: str
) -> None:
    profile = event_pitch_catalog.profile(profile_id)
    expected = sum(profile.slide_seconds.values()) + profile.demo_seconds
    rendered = render_timing_script(event_pitch_catalog, profile_id)
    assert f"Declared total: {expected} seconds." in rendered
    assert f"Target: {profile.target_seconds} seconds" in rendered
    assert "## Live demo — 90 seconds" in rendered


def test_three_minute_script_uses_only_main_slides(event_pitch_catalog: PitchCatalog) -> None:
    rendered = render_timing_script(event_pitch_catalog, "3_MIN")
    assert "## Slide 1 —" in rendered
    assert "## Slide 8 —" in rendered
    assert "## Slide 6 —" not in rendered
    assert "Appendix — audience-selected depth" not in rendered


def test_seven_minute_script_exposes_optional_appendix(event_pitch_catalog: PitchCatalog) -> None:
    rendered = render_timing_script(event_pitch_catalog, "7_MIN")
    assert "## Slide 8 —" in rendered
    assert "## Appendix — audience-selected depth" in rendered


def test_live_demo_script_has_contiguous_cues(event_pitch_catalog: PitchCatalog) -> None:
    rendered = render_live_demo_script(event_pitch_catalog)
    assert "### 00–12s — ERB-001" in rendered
    assert "### 12–55s — ERB-003" in rendered
    assert "### 55–90s — ERB-005" in rendered
    assert "Many agents investigate. Evidence decides. Humans approve." in rendered
    assert "No terminal typing is required" in rendered


def test_unknown_profile_is_a_contract_error(event_pitch_catalog: PitchCatalog) -> None:
    with pytest.raises(PitchContractError, match="Unknown ER-C timing profile"):
        render_timing_script(event_pitch_catalog, "1_MIN")
