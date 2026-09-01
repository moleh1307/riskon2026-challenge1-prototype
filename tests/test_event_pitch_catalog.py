"""Unit tests for the cross-file ER-C catalog."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

import pytest

from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.errors import PitchContractError


def test_catalog_loads_ordered_sources_and_resolves_lookup_helpers(
    event_pitch_catalog: PitchCatalog,
) -> None:
    assert [slide.slide_id for slide in event_pitch_catalog.contract.slides] == [
        f"S{index:02d}" for index in range(1, 13)
    ]
    assert event_pitch_catalog.slide(7).title.startswith("We evaluate")
    assert event_pitch_catalog.profile("5_MIN").target_seconds == 300
    assert len(event_pitch_catalog.metric_ids()) == 7


def test_catalog_rejects_unknown_slide_and_profile(event_pitch_catalog: PitchCatalog) -> None:
    with pytest.raises(PitchContractError, match="Unknown ER-C slide number"):
        event_pitch_catalog.slide(0)
    with pytest.raises(PitchContractError, match="Unknown ER-C timing profile"):
        event_pitch_catalog.profile("10_MIN")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: setattr(c.contract.slides[0], "slide_id", "BAD"),
        lambda c: setattr(c.content.slides[0], "slide_id", "BAD"),
        lambda c: c.contract.slides.pop(),
        lambda c: setattr(c.contract.slides[0], "section", "appendix"),
        lambda c: c.contract.required_slide_fields.append("missing"),
        lambda c: setattr(c.timing.profiles[0], "profile_id", "BAD"),
        lambda c: c.timing.profiles[1].slide_seconds.__setitem__("1", 16),
        lambda c: setattr(c.live_demo, "duration_seconds", 89),
        lambda c: c.live_demo.steps.pop(),
        lambda c: setattr(c.live_demo.steps[1], "start_second", 13),
        lambda c: c.qa_bank.items.pop(),
        lambda c: c.backup.scenes.pop(),
        lambda c: setattr(c.backup, "standalone", False),
        lambda c: c.speaker_assignments.__setitem__("real_names_hard_coded", True),
    ],
)
def test_catalog_rejects_cross_file_contract_mutations(
    event_pitch_catalog: PitchCatalog,
    mutation: Callable[[PitchCatalog], object],
) -> None:
    candidate = deepcopy(event_pitch_catalog)
    mutation(candidate)
    with pytest.raises(PitchContractError):
        candidate.validate()


def test_catalog_metric_ids_reject_non_string_extra_field(
    event_pitch_catalog: PitchCatalog,
) -> None:
    candidate = deepcopy(event_pitch_catalog)
    assert candidate.content.slides[6].__pydantic_extra__ is not None
    candidate.content.slides[6].__pydantic_extra__["metric_ids"] = "not-a-list"
    with pytest.raises(PitchContractError, match="metric_ids"):
        candidate.metric_ids()


def test_catalog_rejects_missing_input(event_pitch_config: object, tmp_path: Path) -> None:
    config = event_pitch_config  # type: ignore[assignment]
    runtime = config.runtime.model_copy(update={"pitch_contract": tmp_path / "missing.json"})  # type: ignore[attr-defined]
    broken = config.model_copy(update={"runtime": runtime})  # type: ignore[attr-defined]
    with pytest.raises(PitchContractError, match="Unable to load pitch contract"):
        PitchCatalog.from_config(broken)


def test_catalog_rejects_non_object_json(event_pitch_config: object, tmp_path: Path) -> None:
    contract = tmp_path / "not-an-object.json"
    contract.write_text("[]", encoding="utf-8")
    config = event_pitch_config  # type: ignore[assignment]
    runtime = config.runtime.model_copy(update={"pitch_contract": contract})  # type: ignore[attr-defined]
    broken = config.model_copy(update={"runtime": runtime})  # type: ignore[attr-defined]
    with pytest.raises(PitchContractError, match="must contain a JSON object"):
        PitchCatalog.from_config(broken)
