"""Unit tests for the typed ER-C models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from riskon.pitch.models import (
    BackupScene,
    DemoStep,
    MetricSource,
    PitchManifest,
    PitchSlideSkeleton,
    QAItem,
)


def test_models_accept_the_frozen_minimal_shapes() -> None:
    slide = PitchSlideSkeleton(
        slide_id="S01", slide_number=1, section="main", kind="title", required=True
    )
    step = DemoStep(
        step_id="DEMO-001",
        start_second=0,
        end_second=12,
        story_id="ERB-001",
        show=["ANSWER"],
        say="Keep the simple case simple.",
    )
    item = QAItem(
        id="QA-01",
        question="What does the prototype show?",
        answer="A bounded evidence gate.",
        source_basis="Contract",
        recommended_seconds=20,
    )
    scene = BackupScene(
        scene_id="SCENE-1", title="FAST_PATH", story_id="ERB-001", required_fields=[]
    )
    assert slide.slide_number == 1
    assert step.final_sentence is None
    assert item.recommended_seconds == 20
    assert scene.story_id == "ERB-001"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            PitchSlideSkeleton,
            {
                "slide_id": "S01",
                "slide_number": 0,
                "section": "main",
                "kind": "title",
                "required": True,
            },
        ),
        (
            DemoStep,
            {
                "step_id": "D",
                "start_second": 1,
                "end_second": 0,
                "story_id": "S",
                "show": [],
                "say": "x",
            },
        ),
        (
            QAItem,
            {
                "id": "Q",
                "question": "q",
                "answer": "a",
                "source_basis": "s",
                "recommended_seconds": 19,
            },
        ),
        (
            MetricSource,
            {"id": "m", "label": "M", "value": "0", "status": "PASS", "source": "s", "matched": -1},
        ),
    ],
)
def test_models_enforce_contract_ranges(model: type[object], payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model(**payload)  # type: ignore[call-arg]


def test_closed_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PitchSlideSkeleton(
            slide_id="S01",
            slide_number=1,
            section="main",
            kind="title",
            required=True,
            extra="forbidden",
        )
    with pytest.raises(ValidationError):
        QAItem(
            id="QA-01",
            question="q",
            answer="a",
            source_basis="s",
            recommended_seconds=20,
            extra="forbidden",
        )


def test_manifest_round_trips_generated_receipt(event_pitch_build: object) -> None:
    result = event_pitch_build  # type: ignore[assignment]
    manifest_path = result.manifest_path  # type: ignore[attr-defined]
    manifest = PitchManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assert manifest.status == "PASS"
    assert manifest.generated_files[-1] == "pitch_manifest.json"
    assert manifest.slide_count == 12
