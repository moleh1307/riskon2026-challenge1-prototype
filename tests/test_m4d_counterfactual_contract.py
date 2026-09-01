"""Frozen M4D counterfactual PlannedVerifiedRun wrappers."""

import json
from pathlib import Path
from typing import Any

from riskon.config import load_milestone4d_config
from riskon.models import PlannedVerifiedRun, QueryInput
from riskon.pipeline import RiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4D_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4d"
FIXTURE_ROOT = M4D_ROOT / "counterfactual_runs"
FIXTURE_ORIGIN = "SYNTHETIC_M4D_COUNTERFACTUAL_BASELINE_V1"

EXPECTED = {
    "M4D-045-region-alpha.planned.json": (
        "M4D-045",
        "M4D-045-region-alpha",
        "region",
        "REGION_ALPHA",
        "ABSTAIN",
        ["SCOPE_MISMATCH"],
    ),
    "M4D-045-service-plus.planned.json": (
        "M4D-045",
        "M4D-045-service-plus",
        "service_model",
        "SERVICE_PLUS",
        "ABSTAIN",
        ["SCOPE_MISMATCH"],
    ),
    "M4D-045-region-removed.planned.json": (
        "M4D-045",
        "M4D-045-region-removed",
        "region",
        None,
        "CLARIFY",
        ["MISSING_REQUIRED_CONTEXT"],
    ),
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_all_m4d_counterfactual_wrappers_roundtrip_and_match_transitions() -> None:
    paths = sorted(FIXTURE_ROOT.glob("M4D-*.planned.json"))
    assert [path.name for path in paths] == sorted(EXPECTED)
    for path in paths:
        wrapper = load_json(path)
        assert set(wrapper) == {
            "fixture_schema_version",
            "fixture_origin",
            "baseline_case_id",
            "variant_id",
            "query_input",
            "context_delta",
            "planned_verified_run",
        }
        baseline_case, variant_id, dimension, after, decision, reasons = EXPECTED[path.name]
        assert wrapper["fixture_schema_version"] == "1.0"
        assert wrapper["fixture_origin"] == FIXTURE_ORIGIN
        assert wrapper["baseline_case_id"] == baseline_case
        assert wrapper["variant_id"] == variant_id
        delta = wrapper["context_delta"]
        assert set(delta) == {"dimension", "before", "after"}
        assert delta["dimension"] == dimension
        assert delta["before"] == ("REGION_BETA" if dimension == "region" else "SERVICE_BASIC")
        assert delta["after"] == after
        query_input = QueryInput.model_validate(wrapper["query_input"])
        planned = PlannedVerifiedRun.model_validate(wrapper["planned_verified_run"])
        assert planned.model_dump(mode="json") == wrapper["planned_verified_run"]
        assert query_input.query == "Does Control Meridian apply to Service Basic in Region Beta?"
        assert planned.query_plan.original_query == query_input.query
        assert planned.query_plan.normalised_query == query_input.query
        assert planned.query_plan.plan_id.startswith("plan-")
        result = planned.verified_run.result
        assert result.decision.value == decision
        assert [reason.value for reason in result.reason_codes] == reasons
        if decision == "ABSTAIN":
            assert (
                result.route is not None
                and planned.verified_run.verification.status.value == "INSUFFICIENT"
            )
        else:
            assert result.route is None and result.clarifying_question
            assert planned.verified_run.verification.status.value == "INSUFFICIENT"


def test_m4d_counterfactual_provenance_is_local_and_query_is_preserved() -> None:
    for path in sorted(FIXTURE_ROOT.glob("M4D-*.planned.json")):
        wrapper = load_json(path)
        text = json.dumps(wrapper, ensure_ascii=False)
        assert "http://" not in text and "https://" not in text
        assert "/Users/" not in text and "@" not in text
        assert "Bank Julius Baer" not in text
        planned = wrapper["planned_verified_run"]
        result = planned["verified_run"]["result"]
        assert all(
            item["source_ref"].startswith("local://synthetic-m4d/")
            for item in [*result["evidence"], *result["retrieved_sections"]]
        )
        assert all(
            reference.startswith("local://synthetic-m4d/")
            for reference in planned["verified_run"]["verification"]["evidence_refs"]
        )


def test_m4d_counterfactual_snapshots_match_current_planned_semantics() -> None:
    pipeline = RiskonPipeline.from_milestone4d_config(
        load_milestone4d_config(PROJECT_ROOT / "config" / "milestone4d.toml")
    )
    for path in sorted(FIXTURE_ROOT.glob("M4D-*.planned.json")):
        wrapper = load_json(path)
        frozen = PlannedVerifiedRun.model_validate(wrapper["planned_verified_run"])
        current = pipeline.run_planned(QueryInput.model_validate(wrapper["query_input"]))
        frozen_value = frozen.model_dump(mode="json")
        current_value = current.model_dump(mode="json")
        frozen_value["verified_run"]["result"]["trace_id"] = "<trace>"
        current_value["verified_run"]["result"]["trace_id"] = "<trace>"
        assert frozen_value == current_value
