"""Tests for structured M4A human-first capsules."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from riskon.config import load_milestone4a_config
from riskon.models import PlannedVerifiedRun, RoutingContext
from riskon.orchestra.case_capsule import build_case_capsule
from riskon.orchestra.models import OrchestraContext, RiskSignal
from riskon.pipeline import RiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"


def fixture(case_id: str) -> PlannedVerifiedRun:
    """Load a frozen M4 planned fixture."""

    raw = json.loads((M4_ROOT / "upstream_runs" / f"{case_id}.planned.json").read_text())
    return PlannedVerifiedRun.model_validate(raw["planned_verified_run"])


def test_capsule_is_deterministic_structured_state_without_raw_text(tmp_path: Path) -> None:
    config = load_milestone4a_config(PROJECT_ROOT / "config" / "milestone4a.toml")
    orchestra = config.orchestra.model_copy(update={"generated_root": tmp_path / "m4a"})
    pipeline = RiskonPipeline.from_milestone4a_config(
        config.model_copy(update={"orchestra": orchestra})
    )
    planned = fixture("M4-039")
    result = planned.verified_run.result
    context = OrchestraContext(
        risk_signals=(RiskSignal("UNSUPPORTED_MODALITY"),),
        routing_context=RoutingContext(
            need_type=result.detected_context.need_type,
            reason_codes=list(result.reason_codes),
        ),
        routing_profile="default",
    )
    routed = pipeline.route_planned(planned, context.routing_context, "default")
    first = build_case_capsule(planned, routed)
    second = build_case_capsule(planned, routed)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.capsule_id == "m4a-capsule-m4-fixture-M4-039"
    assert first.evidence_refs == [
        "local://synthetic-m4/image_only_methodology.html#section-image-only-methodology"
    ]
    assert first.selected_expert_id is None
    assert first.queue_id == "QUEUE-BRM-ALPHA"
    payload = first.model_dump(mode="json")
    assert "excerpt" not in json.dumps(payload)
    assert "answer" not in json.dumps(payload)
    assert "/Users/" not in json.dumps(payload)
    assert "http://" not in json.dumps(payload)


def test_capsule_rejects_missing_route_and_nonlocal_evidence(tmp_path: Path) -> None:
    config = load_milestone4a_config(PROJECT_ROOT / "config" / "milestone4a.toml")
    orchestra = config.orchestra.model_copy(update={"generated_root": tmp_path / "m4a"})
    pipeline = RiskonPipeline.from_milestone4a_config(
        config.model_copy(update={"orchestra": orchestra})
    )
    planned = fixture("M4-034")
    result = planned.verified_run.result
    context = OrchestraContext(
        risk_signals=(RiskSignal("UNRESOLVED_REQUIRED_REFERENCE"),),
        routing_context=RoutingContext(
            need_type=result.detected_context.need_type,
            reason_codes=list(result.reason_codes),
        ),
        routing_profile="default",
    )
    not_routed = pipeline.route_planned(planned, context.routing_context, "default")
    not_routed.expert_route = None
    with pytest.raises(ValueError, match="requires an expert route"):
        build_case_capsule(planned, not_routed)

    capsule = build_case_capsule(
        planned,
        pipeline.route_planned(planned, context.routing_context, "capacity_stress"),
    )
    invalid = {**capsule.model_dump(mode="json"), "evidence_refs": ["https://bad.invalid"]}
    with pytest.raises(ValidationError, match="local M4 refs"):
        type(capsule).model_validate(invalid)
