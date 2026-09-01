"""Load and validate the frozen ER-C source contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from riskon.config import EventPitchConfig
from riskon.pitch.errors import PitchContractError
from riskon.pitch.models import (
    BackupContract,
    LiveDemoContract,
    PitchContract,
    QABank,
    SlideContent,
    SlideContentCatalog,
    TimingCatalog,
    TimingProfile,
)


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object and fail with a pitch-specific error."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PitchContractError(f"Unable to load pitch contract {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise PitchContractError(f"Pitch contract {path.name} must contain a JSON object")
    return raw


class PitchCatalog:
    """All typed ER-C contracts loaded from repository-local JSON."""

    def __init__(
        self,
        config: EventPitchConfig,
        contract: PitchContract,
        content: SlideContentCatalog,
        timing: TimingCatalog,
        live_demo: LiveDemoContract,
        qa_bank: QABank,
        backup: BackupContract,
        presentation_copy: dict[str, Any],
        speaker_assignments: dict[str, Any],
    ) -> None:
        self.config = config
        self.contract = contract
        self.content = content
        self.timing = timing
        self.live_demo = live_demo
        self.qa_bank = qa_bank
        self.backup = backup
        self.presentation_copy = presentation_copy
        self.speaker_assignments = speaker_assignments
        self.validate()

    @classmethod
    def from_config(cls, config: EventPitchConfig) -> PitchCatalog:
        """Read every ER-C contract file and build one validated catalog."""

        paths = config.runtime
        contract = PitchContract.model_validate(_load_json(paths.pitch_contract))
        content = SlideContentCatalog.model_validate(_load_json(paths.slide_content))
        timing = TimingCatalog.model_validate(_load_json(paths.timing_profiles))
        live_demo = LiveDemoContract.model_validate(_load_json(paths.live_demo_script))
        qa_bank = QABank.model_validate(_load_json(paths.qa_bank))
        backup = BackupContract.model_validate(_load_json(paths.backup_demo_contract))
        presentation_copy = _load_json(paths.presentation_copy)
        speaker_assignments = _load_json(paths.speaker_assignments)
        return cls(
            config,
            contract,
            content,
            timing,
            live_demo,
            qa_bank,
            backup,
            presentation_copy,
            speaker_assignments,
        )

    def validate(self) -> None:
        """Enforce the cross-file ER-C contract invariants."""

        expected_ids = [f"S{index:02d}" for index in range(1, 13)]
        contract_ids = [slide.slide_id for slide in self.contract.slides]
        content_ids = [slide.slide_id for slide in self.content.slides]
        if contract_ids != expected_ids or content_ids != expected_ids:
            raise PitchContractError("ER-C slide IDs must be the ordered S01..S12 set")
        if len(self.contract.slides) != self.config.deck.total_slide_count:
            raise PitchContractError("ER-C slide count does not match configuration")
        if sum(slide.section == "main" for slide in self.contract.slides) != 8:
            raise PitchContractError("ER-C must have exactly eight main slides")
        if sum(slide.section == "appendix" for slide in self.contract.slides) != 4:
            raise PitchContractError("ER-C must have exactly four appendix slides")
        required = set(self.contract.required_slide_fields)
        for slide in self.content.slides:
            if not required <= set(slide.model_dump(mode="json")):
                raise PitchContractError(f"Slide {slide.slide_id} omits a required content field")
        profile_ids = [profile.profile_id for profile in self.timing.profiles]
        if profile_ids != ["3_MIN", "5_MIN", "7_MIN"]:
            raise PitchContractError("ER-C timing profiles must remain 3_MIN, 5_MIN and 7_MIN")
        canonical = self.profile("5_MIN")
        if sum(canonical.slide_seconds.values()) + canonical.demo_seconds != 300:
            raise PitchContractError("Canonical 5_MIN timing must total 300 seconds")
        if self.live_demo.duration_seconds != self.config.timing.live_demo_seconds:
            raise PitchContractError("Live demo duration does not match config")
        if len(self.live_demo.steps) != 3:
            raise PitchContractError("Live demo must contain exactly three bounded steps")
        cursor = 0
        for step in self.live_demo.steps:
            if step.start_second != cursor or step.end_second <= step.start_second:
                raise PitchContractError("Live demo steps must be contiguous and increasing")
            cursor = step.end_second
        if cursor != self.live_demo.duration_seconds:
            raise PitchContractError("Live demo steps must end at the declared duration")
        if len(self.qa_bank.items) != 18:
            raise PitchContractError("ER-C Q&A bank must contain eighteen topics")
        if len(self.backup.scenes) != 6 or not self.backup.standalone:
            raise PitchContractError("ER-C backup demo must contain six standalone scenes")
        if self.speaker_assignments.get("real_names_hard_coded") is not False:
            raise PitchContractError("Speaker assignments must remain role-based")

    def slide(self, slide_number: int) -> SlideContent:
        """Return one slide by its one-based number."""

        if slide_number < 1 or slide_number > len(self.content.slides):
            raise PitchContractError(f"Unknown ER-C slide number: {slide_number}")
        return self.content.slides[slide_number - 1]

    def profile(self, profile_id: str) -> TimingProfile:
        """Return a timing profile by ID."""

        for profile in self.timing.profiles:
            if profile.profile_id == profile_id:
                return profile
        raise PitchContractError(f"Unknown ER-C timing profile: {profile_id}")

    def metric_ids(self) -> list[str]:
        """Return the evaluator metric IDs required on slide seven."""

        raw = self.slide(7).model_dump(mode="json").get("metric_ids")
        if not isinstance(raw, list) or not all(isinstance(value, str) for value in raw):
            raise PitchContractError("Slide S07 metric_ids must be a list of strings")
        return raw
