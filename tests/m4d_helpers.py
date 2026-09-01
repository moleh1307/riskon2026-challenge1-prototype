"""Shared fixtures and constructors for the M4D acceptance tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from riskon.config import Milestone4DConfig, load_milestone4d_config
from riskon.evaluation import M4DCase, M4DCaseSet
from riskon.models import PlannedVerifiedRun, QueryInput
from riskon.pipeline import M4DRiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4D_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4d"
M4D_CONFIG_PATH = PROJECT_ROOT / "config" / "milestone4d.toml"


def m4d_config(tmp_path: Path) -> Milestone4DConfig:
    """Load M4D and redirect only its generated output directory."""

    config = load_milestone4d_config(M4D_CONFIG_PATH)
    profile = config.orchestra.m4d.model_copy(update={"generated_root": tmp_path / "m4d"})
    orchestra = config.orchestra.model_copy(update={"m4d": profile})
    return config.model_copy(update={"orchestra": orchestra})


def case(case_id: str) -> M4DCase:
    """Read one frozen M4D evaluation case."""

    case_set = M4DCaseSet.model_validate_json(
        (M4D_ROOT / "evaluation_cases.json").read_text(encoding="utf-8")
    )
    return next(item for item in case_set.cases if item.id == case_id)


def request(case_id: str, *, trace_id: str | None = None) -> QueryInput:
    """Build a request from the closed-world case envelope."""

    value = case(case_id)
    return QueryInput(
        query=value.query,
        context=value.input_context,
        trace_id=trace_id or f"test-{case_id.lower()}",
    )


def baseline(case_id: str) -> PlannedVerifiedRun:
    """Read one frozen M4D planned baseline wrapper."""

    raw = json.loads(
        (M4D_ROOT / "baseline_runs" / f"{case_id}.planned.json").read_text(encoding="utf-8")
    )
    return PlannedVerifiedRun.model_validate(raw["planned_verified_run"])


def pipeline(tmp_path: Path) -> M4DRiskonPipeline:
    """Build an isolated M4D-enabled pipeline."""

    return M4DRiskonPipeline.from_milestone4d_config(m4d_config(tmp_path))


def semantic_run(value: Any) -> dict[str, Any]:
    """Drop only trace identity from a model dump for deterministic comparison."""

    dumped = value.model_dump(mode="json")
    if "final_verified_run" in dumped:
        dumped["final_verified_run"]["result"]["trace_id"] = "<trace>"
    if "baseline_run" in dumped:
        dumped["baseline_run"]["verified_run"]["result"]["trace_id"] = "<trace>"
    if "verified_run" in dumped:
        dumped["verified_run"]["result"]["trace_id"] = "<trace>"
    return dumped
