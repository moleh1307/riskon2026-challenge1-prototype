"""ER-C contract-freeze tests: slide copy, timings, demo, Q&A and speaker shape."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PITCH_ROOT = ROOT / "data" / "synthetic" / "event_pitch"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_all_slides_have_required_fields_and_exact_main_story() -> None:
    content = _json(PITCH_ROOT / "slide_content.json")
    slides = content["slides"]
    assert len(slides) == 12
    required = {
        "slide_id",
        "title",
        "purpose",
        "source_label",
        "speaker_key_message",
        "timing_profile_visibility",
    }
    assert {slide["slide_id"] for slide in slides} == {f"S{index:02d}" for index in range(1, 13)}
    assert all(required <= set(slide) for slide in slides)
    assert slides[0]["title"] == "RiskON Orchestra"
    assert slides[0]["subtitle_lines"] == [
        "Many agents investigate.",
        "Evidence decides.",
        "Humans approve.",
    ]
    assert slides[1]["title"] == "Finding the page is not the same as finding the answer"
    assert [card["label"] for card in slides[1]["cards"]] == [
        "Front Office",
        "Experts",
        "The Bank",
    ]
    assert slides[2]["title"] == "One question. Four disciplined outcomes."
    assert [item["label"] for item in slides[2]["outcomes"]] == [
        "ANSWER",
        "CLARIFY",
        "ABSTAIN",
        "ROUTE",
    ]
    assert slides[3]["workers"] == [
        "Evidence Scout",
        "Scope Sentinel",
        "Process/Table Scout",
        "Skeptic",
        "Counterfactual Sentinel",
    ]
    assert slides[7]["final_statement"].startswith("RiskON does not simply know the answer")
    assert slides[11]["critical_wording"] == [
        "The orchestration and worker isolation are real.",
        (
            "The current worker backend is deterministic for reproducibility and "
            "confidential-data safety."
        ),
        "It is model-agnostic, but this demo does not claim a model-driven autonomous swarm.",
    ]


def test_timing_profiles_cover_three_five_and_seven_minutes() -> None:
    timing = _json(PITCH_ROOT / "timing_profiles.json")
    profiles = timing["profiles"]
    assert [profile["profile_id"] for profile in profiles] == ["3_MIN", "5_MIN", "7_MIN"]
    assert all(profile["official_duration_assumed"] is False for profile in profiles)
    assert all(profile["demo_seconds"] == 90 for profile in profiles)
    canonical = next(profile for profile in profiles if profile["profile_id"] == "5_MIN")
    assert canonical["target_seconds"] == 300
    assert canonical["slide_seconds"] == {
        "1": 15,
        "2": 30,
        "3": 35,
        "4": 40,
        "6": 30,
        "7": 25,
        "8": 35,
    }
    assert sum(canonical["slide_seconds"].values()) + canonical["demo_seconds"] == 300
    assert canonical["included_slides"] == list(range(1, 9))
    assert next(profile for profile in profiles if profile["profile_id"] == "7_MIN")[
        "appendix_slides"
    ] == [9, 10, 11, 12]


def test_live_demo_is_exactly_three_bounded_steps() -> None:
    demo = _json(PITCH_ROOT / "live_demo_script.json")
    assert demo["duration_seconds"] == 90
    assert demo["terminal_typing_required"] is False
    assert demo["steps"] == [
        {
            "step_id": "DEMO-001",
            "start_second": 0,
            "end_second": 12,
            "story_id": "ERB-001",
            "show": ["FAST_PATH", "ANSWER", "Agents activated: 0"],
            "say": (
                "A simple, explicit question should remain simple. The system finds "
                "sufficient evidence and activates no agents."
            ),
        },
        {
            "step_id": "DEMO-002",
            "start_second": 12,
            "end_second": 55,
            "story_id": "ERB-003",
            "show": [
                "Evidence Scout",
                "Scope Sentinel",
                "Counterfactual Sentinel",
                "Region Beta → Region Alpha: ANSWER → ABSTAIN",
                "Service Basic → Service Plus: ANSWER → ABSTAIN",
                "Region removed: ANSWER → CLARIFY",
            ],
            "say": (
                "For a scope-sensitive question, the Orchestra investigates from independent "
                "angles. It then changes one business fact at a time. The answer is released "
                "only because all three expected decision transitions pass."
            ),
        },
        {
            "step_id": "DEMO-003",
            "start_second": 55,
            "end_second": 90,
            "story_id": "ERB-005",
            "show": [
                "ABSTAIN",
                "Expert Resolution",
                "Proposed Knowledge Patch",
                "Policy CI",
                "Separate Human Approval",
                "Versioned Knowledge Release",
                "Active Overlay",
            ],
            "say": (
                "When the evidence is missing, the system abstains and creates a case capsule "
                "for the right expert. The expert response is not written directly into memory. "
                "It becomes a proposed knowledge patch, passes Policy CI and regression tests, "
                "receives separate human approval and enters a versioned release. The "
                "exact-scope question can then be answered, while neighbouring scopes still "
                "abstain or clarify."
            ),
            "final_sentence": "Many agents investigate. Evidence decides. Humans approve.",
        },
    ]


def test_backup_has_six_standalone_scenes_and_required_controls() -> None:
    backup = _json(PITCH_ROOT / "backup_demo_contract.json")
    assert backup["standalone"] is True
    assert backup["controls"] == ["ArrowLeft", "ArrowRight", "Space", "Home", "End"]
    assert backup["scenes"] == [
        {
            "scene_id": "SCENE-1",
            "title": "FAST_PATH",
            "story_id": "ERB-001",
            "required_fields": ["decision", "activation_profile", "answer", "evidence"],
        },
        {
            "scene_id": "SCENE-2",
            "title": "Full Orchestra task graph",
            "story_id": "ERB-003",
            "required_fields": ["agent_roles", "orchestra_activity", "decision"],
        },
        {
            "scene_id": "SCENE-3",
            "title": "Three counterfactual transitions",
            "story_id": "ERB-003",
            "required_fields": ["counterfactuals"],
        },
        {
            "scene_id": "SCENE-4",
            "title": "Safe abstention and expert route",
            "story_id": "ERB-004",
            "required_fields": ["decision", "route", "case_capsule_id"],
        },
        {
            "scene_id": "SCENE-5",
            "title": "Policy CI lifecycle",
            "story_id": "ERB-005",
            "required_fields": ["governance"],
        },
        {
            "scene_id": "SCENE-6",
            "title": "Evaluation metrics",
            "story_id": "DASHBOARD",
            "required_fields": ["metrics", "security"],
        },
    ]
    assert "deterministic offline replay" in backup["fallback_sentence"]


def test_qa_bank_has_all_required_topics_and_honest_confidence_answer() -> None:
    qa = _json(PITCH_ROOT / "qa_bank.json")
    items = qa["items"]
    assert len(items) == 18
    assert [item["id"] for item in items] == [f"QA-{index:02d}" for index in range(1, 19)]
    assert all(20 <= item["recommended_seconds"] <= 40 for item in items)
    assert all(item["question"] and item["answer"] and item["source_basis"] for item in items)
    assert "No. They are explicitly labelled deterministic heuristics." in items[9]["answer"]
    assert "never claim" not in " ".join(item["answer"].casefold() for item in items)
    assert "model-driven autonomous swarm" not in " ".join(item["answer"] for item in items)


def test_speaker_profiles_are_role_based_without_real_names() -> None:
    assignments = _json(PITCH_ROOT / "speaker_assignments.json")
    assert set(assignments["profiles"]) == {"2-speaker", "3-speaker", "4-speaker"}
    assert assignments["profiles"]["3-speaker"] == {
        "Speaker A": ["Slides 1–3: problem and decision design"],
        "Speaker B": ["Slide 4 + 90-second live demo"],
        "Speaker C": ["Slides 6–8: governed evolution, metrics and business value"],
    }
    assert assignments["appendix_owners"] == {
        "Speaker A": "business/problem",
        "Speaker B": "architecture/security",
        "Speaker C": "governance/evaluation",
    }
    assert assignments["real_names_hard_coded"] is False
