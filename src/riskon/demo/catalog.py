"""Load and validate the frozen ER-B presentation contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from riskon.config import EventDemoConfig
from riskon.demo.models import ContextPreset, DemoCase, ExpectedView


class DemoCatalog:
    """Repository-local catalog of stories, copy, presets, and expected views."""

    def __init__(
        self,
        config: EventDemoConfig,
        cases: tuple[DemoCase, ...],
        dashboard_contract: dict[str, Any],
        presentation_copy: dict[str, Any],
        context_presets: tuple[ContextPreset, ...],
        expected_views: dict[str, ExpectedView],
    ) -> None:
        self.config = config
        self.cases = cases
        self.dashboard_contract = dashboard_contract
        self.presentation_copy = presentation_copy
        self.context_presets = context_presets
        self.expected_views = expected_views
        self._cases_by_id = {case.id: case for case in cases}

    @classmethod
    def from_config(cls, config: EventDemoConfig) -> DemoCatalog:
        """Read all ER-B contracts and reject a partial or mismatched catalog."""

        demo_contract = _read_object(config.runtime.demo_cases)
        dashboard_contract = _read_object(config.runtime.dashboard_contract)
        presentation_copy = _read_object(config.runtime.presentation_copy)
        context_contract = _read_object(config.runtime.context_presets)
        if demo_contract.get("schema_version") != "1.0":
            raise ValueError("Unsupported ER-B demo case schema")
        if demo_contract.get("milestone") != "ER-B_THIN_LOCAL_DEMO":
            raise ValueError("Unexpected ER-B demo case milestone")
        if dashboard_contract.get("schema_version") != "1.0":
            raise ValueError("Unsupported ER-B dashboard contract schema")
        if dashboard_contract.get("milestone") != "ER-B_EVALUATION_DASHBOARD":
            raise ValueError("Unexpected ER-B dashboard milestone")
        if presentation_copy.get("schema_version") != "1.0":
            raise ValueError("Unsupported ER-B presentation-copy schema")
        if context_contract.get("schema_version") != "1.0":
            raise ValueError("Unsupported ER-B context-preset schema")

        raw_cases = demo_contract.get("cases")
        if not isinstance(raw_cases, list):
            raise ValueError("ER-B demo case contract must contain a cases list")
        cases = tuple(DemoCase.model_validate(item) for item in raw_cases)
        expected_ids = tuple(config.demo.included_cases)
        if tuple(case.id for case in cases) != expected_ids:
            raise ValueError("ER-B case order does not match the configured story set")
        if len({case.id for case in cases}) != len(cases):
            raise ValueError("ER-B case IDs must be unique")

        presets_raw = context_contract.get("presets")
        if not isinstance(presets_raw, list):
            raise ValueError("ER-B context contract must contain a presets list")
        presets = tuple(ContextPreset.model_validate(item) for item in presets_raw)
        if len({preset.id for preset in presets}) != len(presets):
            raise ValueError("ER-B context preset IDs must be unique")
        for preset in presets:
            if any(not key or not value for key, value in preset.context.items()):
                raise ValueError("ER-B context presets must contain non-empty strings")

        expected_views: dict[str, ExpectedView] = {}
        for case in cases:
            path = config.runtime.expected_views_root / f"{case.id}.view.json"
            view = ExpectedView.model_validate(_read_object(path))
            if view.case_id != case.id or view.source_case_id != case.source_case_id:
                raise ValueError(f"ER-B expected view does not match {case.id}")
            expected_views[case.id] = view
        return cls(
            config=config,
            cases=cases,
            dashboard_contract=dashboard_contract,
            presentation_copy=presentation_copy,
            context_presets=presets,
            expected_views=expected_views,
        )

    def case(self, case_id: str) -> DemoCase:
        """Return one configured case or raise a stable lookup error."""

        try:
            return self._cases_by_id[case_id]
        except KeyError as exc:
            raise KeyError(f"Unknown ER-B demo case: {case_id}") from exc

    def preset(self, preset_id: str) -> ContextPreset:
        """Return one configured context preset."""

        for preset in self.context_presets:
            if preset.id == preset_id:
                return preset
        raise KeyError(f"Unknown ER-B context preset: {preset_id}")


def _read_object(path: Path) -> dict[str, Any]:
    """Read one JSON object without allowing scalar contract files."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid ER-B JSON contract: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"ER-B JSON contract must be an object: {path.name}")
    return value
