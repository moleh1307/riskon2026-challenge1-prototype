"""Render human-readable scripts and runbooks from the ER-C contracts."""

from __future__ import annotations

from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.qa_renderer import render_qa_item


def _profile_total(catalog: PitchCatalog, profile_id: str) -> int:
    """Calculate a profile's declared speaking time."""

    profile = catalog.profile(profile_id)
    return sum(profile.slide_seconds.values()) + profile.demo_seconds


def render_timing_script(catalog: PitchCatalog, profile_id: str) -> str:
    """Render one modular speaker script with its exact timing budget."""

    profile = catalog.profile(profile_id)
    lines = [
        f"# RiskON Orchestra — {profile.profile_id} speaker script",
        "",
        f"> Target: {profile.target_seconds} seconds (±{profile.tolerance_seconds}); "
        "official duration not assumed.",
        "> Message: We do not confuse retrieval with permission to answer.",
        "",
    ]
    for slide_ref in profile.included_slides:
        if slide_ref == "APPENDIX_SELECTED":
            lines.extend(
                [
                    "## Appendix — audience-selected depth",
                    "",
                    f"**{profile.slide_seconds['APPENDIX_SELECTED']} seconds**",
                    "Choose one appendix slide according to the audience question.",
                    "",
                ]
            )
            continue
        slide_number = int(slide_ref)
        if slide_number == 5:
            lines.extend(_live_demo_lines(catalog))
            continue
        slide = catalog.slide(slide_number)
        seconds = profile.slide_seconds.get(str(slide_number), 0)
        if seconds <= 0:
            continue
        lines.extend(
            [
                f"## Slide {slide_number} — {slide.title}",
                "",
                f"**{seconds} seconds**",
                slide.speaker_key_message,
                "",
            ]
        )
    lines.extend(
        [
            "## Timing check",
            "",
            f"Declared total: {_profile_total(catalog, profile_id)} seconds.",
            "",
        ]
    )
    return "\n".join(lines)


def _live_demo_lines(catalog: PitchCatalog) -> list[str]:
    """Render the live demo block used by every timing profile."""

    lines = ["## Live demo — 90 seconds", ""]
    for step in catalog.live_demo.steps:
        lines.extend(
            [
                f"### {step.start_second:02d}–{step.end_second:02d}s — {step.story_id}",
                "",
                f"Show: {'; '.join(step.show)}",
                f"Say: {step.say}",
                "",
            ]
        )
        if step.final_sentence:
            lines.extend([f"Final sentence: {step.final_sentence}", ""])
    return lines


def render_live_demo_script(catalog: PitchCatalog) -> str:
    """Render the event-day 90-second live-demo cue sheet."""

    lines = [
        "# RiskON Orchestra — 90-second live demo",
        "",
        "> Primary surfaces: the frozen local demo index and dashboard.",
        "> No terminal typing is required in the primary demo.",
        "",
    ]
    lines.extend(_live_demo_lines(catalog))
    return "\n".join(lines)


def render_qa_bank(catalog: PitchCatalog) -> str:
    """Render the eighteen-question Q&A bank."""

    lines = [
        "# RiskON Orchestra — Q&A bank",
        "",
        "> Keep answers between 20 and 40 seconds. Use the honest capability boundary when "
        "asked about AI, confidence or production scale.",
        "",
    ]
    for item in catalog.qa_bank.items:
        lines.extend(render_qa_item(item))
    return "\n".join(lines)


def render_one_page_summary(catalog: PitchCatalog) -> str:
    """Render a compact presenter-facing summary of the package."""

    return "\n".join(
        [
            "# RiskON Orchestra — one-page summary",
            "",
            "## The problem",
            "Finding a relevant page does not prove that the answer is valid for the "
            "question's scope.",
            "",
            "## The product decision",
            "The system chooses ANSWER, CLARIFY, ABSTAIN or ROUTE according to evidence, "
            "context and risk.",
            "",
            "## The proof",
            "Bounded workers investigate independently; a material objection blocks unsafe "
            "release; governed patches require Policy CI and separate human approval.",
            "",
            "## The demo",
            "Show a zero-worker answer, challenge a scope-sensitive answer, then show governed "
            "evolution from abstention to an approved overlay.",
            "",
            "## The honest boundary",
            "The orchestration is real and the worker backend is deterministic. The demo does "
            "not claim a model-driven autonomous swarm, calibrated probabilities or "
            "production-scale performance.",
            "",
            f"Canonical profile: {catalog.profile('5_MIN').target_seconds} seconds.",
            "",
        ]
    )
