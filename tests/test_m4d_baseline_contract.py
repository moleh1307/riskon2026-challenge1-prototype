"""Frozen M4D baseline PlannedVerifiedRun wrappers."""

import json
from pathlib import Path
from typing import Any

from riskon.config import load_milestone4d_config
from riskon.models import PlannedVerifiedRun, QueryInput
from riskon.pipeline import RiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4D_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4d"
BASELINE_ROOT = M4D_ROOT / "baseline_runs"
FIXTURE_ORIGIN = "SYNTHETIC_M4D_BASELINE_V1"

EXPECTED = {
    "M4D-041": ("What is the Synthetic Stability Marker?", "ANSWER", []),
    "M4D-042": ("Can a delegated operator use ARC?", "CLARIFY", ["AMBIGUOUS_ACRONYM"]),
    "M4D-043": (
        "Where can I submit the Synthetic Atlas exception request?",
        "ABSTAIN",
        ["UNRESOLVED_REQUIRED_REFERENCE"],
    ),
    "M4D-044": (
        (
            "An active recommendation triggered the Synthetic Atlas Control. "
            "Can I proceed if the client accepts the risk?"
        ),
        "ANSWER",
        [],
    ),
    "M4D-045": (
        "Does Control Meridian apply to Service Basic in Region Beta?",
        "ANSWER",
        [],
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def semantic_dump(planned: PlannedVerifiedRun) -> dict[str, Any]:
    value = planned.model_dump(mode="json")
    value["verified_run"]["result"]["trace_id"] = "<trace>"
    return value


def test_all_m4d_baseline_wrappers_roundtrip_and_match_the_case_matrix() -> None:
    paths = sorted(BASELINE_ROOT.glob("M4D-*.planned.json"))
    assert [path.stem.removesuffix(".planned") for path in paths] == sorted(EXPECTED)
    for path in paths:
        case_id = path.name.removesuffix(".planned.json")
        wrapper = load_json(path)
        assert set(wrapper) == {
            "fixture_schema_version",
            "fixture_origin",
            "case_id",
            "query_input",
            "planned_verified_run",
        }
        assert wrapper["fixture_schema_version"] == "1.0"
        assert wrapper["fixture_origin"] == FIXTURE_ORIGIN
        assert wrapper["case_id"] == case_id
        query_input = QueryInput.model_validate(wrapper["query_input"])
        planned = PlannedVerifiedRun.model_validate(wrapper["planned_verified_run"])
        assert planned.model_dump(mode="json") == wrapper["planned_verified_run"]
        query, decision, reasons = EXPECTED[case_id]
        assert query_input.query == query
        assert planned.query_plan.original_query == query
        assert planned.query_plan.normalised_query == query
        assert planned.query_plan.plan_id.startswith("plan-")
        result = planned.verified_run.result
        assert result.decision.value == decision
        assert [reason.value for reason in result.reason_codes] == reasons
        if decision == "ANSWER":
            assert result.answer and result.route is None
            assert planned.verified_run.verification.status.value == "SUFFICIENT"
        elif decision == "CLARIFY":
            assert result.answer is None and result.clarifying_question and result.route is None
            assert planned.verified_run.verification.status.value == "INSUFFICIENT"
        else:
            assert result.answer is None and result.route is not None
            assert planned.verified_run.verification.status.value == "INSUFFICIENT"


def test_m4d_baselines_are_local_semantic_snapshots_and_not_case_logic() -> None:
    for path in sorted(BASELINE_ROOT.glob("M4D-*.planned.json")):
        wrapper = load_json(path)
        planned = PlannedVerifiedRun.model_validate(wrapper["planned_verified_run"])
        semantic = semantic_dump(planned)
        assert semantic["verified_run"]["result"]["trace_id"] == "<trace>"
        strings = json.dumps(semantic, ensure_ascii=False)
        assert "http://" not in strings and "https://" not in strings
        assert "/Users/" not in strings and "@" not in strings
        assert "Bank Julius Baer" not in strings
        result = semantic["verified_run"]["result"]
        for evidence in [*result["evidence"], *result["retrieved_sections"]]:
            assert evidence["source_ref"].startswith("local://synthetic-m4d/")
        assert all(
            ref.startswith("local://synthetic-m4d/")
            for ref in semantic["verified_run"]["verification"]["evidence_refs"]
        )


def test_m4d_baseline_semantic_comparison_contract_ignores_only_trace_identity() -> None:
    pipeline = RiskonPipeline.from_milestone4d_config(
        load_milestone4d_config(PROJECT_ROOT / "config" / "milestone4d.toml")
    )
    for path in sorted(BASELINE_ROOT.glob("M4D-*.planned.json")):
        wrapper = load_json(path)
        planned = PlannedVerifiedRun.model_validate(wrapper["planned_verified_run"])
        current = pipeline.run_planned(QueryInput.model_validate(wrapper["query_input"]))
        assert semantic_dump(planned) == semantic_dump(current)
