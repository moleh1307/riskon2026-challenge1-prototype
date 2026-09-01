"""Typed models for the frozen ER-C contract and generated manifest."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PitchSlideSkeleton(BaseModel):
    """One required slide slot in the twelve-slide deck."""

    model_config = ConfigDict(extra="forbid")

    slide_id: str
    slide_number: int = Field(ge=1, le=12)
    section: str
    kind: str
    required: bool


class PitchContract(BaseModel):
    """High-level ER-C deck and security contract."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    milestone: str
    deck: dict[str, Any]
    palette: dict[str, str]
    fonts: list[str]
    slides: list[PitchSlideSkeleton]
    required_slide_fields: list[str]
    security: dict[str, bool]


class SlideContent(BaseModel):
    """Audience-facing copy plus structured blocks for one slide."""

    model_config = ConfigDict(extra="allow")

    slide_id: str
    title: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    speaker_key_message: str = Field(min_length=1)
    timing_profile_visibility: dict[str, bool]


class SlideContentCatalog(BaseModel):
    """Complete ordered slide content catalog."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    slides: list[SlideContent]


class TimingProfile(BaseModel):
    """One duration profile, including its bounded live-demo allocation."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    label: str
    target_seconds: int = Field(ge=1)
    tolerance_seconds: int = Field(ge=0)
    official_duration_assumed: bool
    included_slides: list[int | str]
    slide_seconds: dict[str, int] = Field(default_factory=dict)
    demo_seconds: int = Field(ge=0)
    appendix_slides: list[int] = Field(default_factory=list)


class TimingCatalog(BaseModel):
    """Three frozen timing profiles."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    profiles: list[TimingProfile]


class DemoStep(BaseModel):
    """One bounded segment of the 90-second live demo."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    start_second: int = Field(ge=0)
    end_second: int = Field(gt=0)
    story_id: str
    show: list[str]
    say: str = Field(min_length=1)
    final_sentence: str | None = None


class LiveDemoContract(BaseModel):
    """Frozen live-demo flow and local source surfaces."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    duration_seconds: int = Field(gt=0)
    primary_bundle: str
    primary_surfaces: list[str]
    terminal_typing_required: bool
    steps: list[DemoStep]


class QAItem(BaseModel):
    """One audience question with a short recommended answer."""

    model_config = ConfigDict(extra="forbid")

    id: str
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    source_basis: str = Field(min_length=1)
    recommended_seconds: int = Field(ge=20, le=40)


class QABank(BaseModel):
    """The complete eighteen-topic Q&A bank."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    recommended_answer_seconds: list[int]
    items: list[QAItem]


class BackupScene(BaseModel):
    """One scene in the deterministic offline replay."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str
    title: str
    story_id: str
    required_fields: list[str]


class BackupContract(BaseModel):
    """Standalone backup-demo contract."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    standalone: bool
    source_bundle: str
    independent_of: list[str]
    controls: list[str]
    scenes: list[BackupScene]
    fallback_sentence: str


class MetricSource(BaseModel):
    """Metric value copied from a generated evaluator output."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    value: str
    status: str
    source: str = Field(min_length=1)
    matched: int | None = Field(default=None, ge=0)
    expected: int | None = Field(default=None, ge=0)


class MetricSnapshot(BaseModel):
    """Small validated view of the current dashboard metric source."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    metrics: list[MetricSource]
    network_enabled: bool


class PitchManifest(BaseModel):
    """Machine-readable ER-C build receipt."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    artifact: str
    status: str
    generated_files: list[str]
    slide_count: int
    main_slide_count: int
    appendix_slide_count: int
    timing_profile_count: int
    canonical_profile: str
    canonical_duration_seconds: int
    live_demo_seconds: int
    qa_topic_count: int
    backup_scene_count: int
    metric_source_count: int
    metric_source_expected: int
    hard_coded_evaluator_metric_count: int
    external_asset_count: int
    external_link_count: int
    absolute_path_leak_count: int
    real_name_or_contact_leak_count: int
    confidential_source_text_leak_count: int
    network_violation_count: int
    network_enabled: bool
