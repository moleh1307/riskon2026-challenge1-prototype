"""Schema and safety contract for frozen M4C counterfactual fixtures."""

import json
from pathlib import Path
from typing import Any

from riskon.models import PlannedVerifiedRun

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4C_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4c"
FIXTURE_ROOT = M4C_ROOT / "counterfactual_runs"

EXPECTED = {
    "M4-035-region-alpha.planned.json": (
        "m4-fixture-M4-035",
        "M4-035-CF-01",
        "ABSTAIN",
        ["SCOPE_MISMATCH"],
    ),
    "M4-035-service-plus.planned.json": (
        "m4-fixture-M4-035",
        "M4-035-CF-02",
        "ABSTAIN",
        ["SCOPE_MISMATCH"],
    ),
    "M4-035-region-removed.planned.json": (
        "m4-fixture-M4-035",
        "M4-035-CF-03",
        "CLARIFY",
        ["MISSING_REQUIRED_CONTEXT"],
    ),
    "M4-036-service-plus.planned.json": ("m4-fixture-M4-036", "M4-036-CF-01", "ANSWER", []),
}


def load_json(path: Path) -> dict[str, Any]:
    """Load one fixture wrapper."""

    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def iter_strings(value: Any) -> list[str]:
    """Collect nested strings for local-only provenance checks."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in iter_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in iter_strings(child)]
    return []


def test_all_m4c_fixtures_have_exact_wrappers_and_model_roundtrips() -> None:
    paths = sorted(FIXTURE_ROOT.glob("*.planned.json"))
    assert [path.name for path in paths] == sorted(EXPECTED)
    for path in paths:
        wrapper = load_json(path)
        assert set(wrapper) == {
            "fixture_schema_version",
            "fixture_origin",
            "baseline_plan_id",
            "variant_id",
            "context_delta",
            "planned_verified_run",
        }
        baseline_plan_id, variant_id, decision, reasons = EXPECTED[path.name]
        assert wrapper["fixture_schema_version"] == "1.0"
        assert wrapper["fixture_origin"] == "SYNTHETIC_COUNTERFACTUAL_RUN_V1"
        assert wrapper["baseline_plan_id"] == baseline_plan_id
        assert wrapper["variant_id"] == variant_id
        assert set(wrapper["context_delta"]) == {"dimension", "before", "after"}

        planned = PlannedVerifiedRun.model_validate(wrapper["planned_verified_run"])
        assert planned.query_plan.plan_id == baseline_plan_id
        assert planned.query_plan.original_query == planned.query_plan.normalised_query
        assert planned.verified_run.result.decision.value == decision
        assert [reason.value for reason in planned.verified_run.result.reason_codes] == reasons
        assert planned.model_dump(mode="json") == wrapper["planned_verified_run"]

        if decision == "ANSWER":
            assert planned.verified_run.result.route is None
            assert planned.verified_run.verification.status.value == "SUFFICIENT"
        elif decision == "CLARIFY":
            assert planned.verified_run.result.route is None
            assert planned.verified_run.result.clarifying_question
            assert planned.verified_run.verification.status.value == "INSUFFICIENT"
        else:
            assert planned.verified_run.result.route is not None
            assert planned.verified_run.verification.status.value == "INSUFFICIENT"


def test_counterfactual_fixture_provenance_is_local_and_query_is_preserved() -> None:
    for path in sorted(FIXTURE_ROOT.glob("*.planned.json")):
        wrapper = load_json(path)
        strings = iter_strings(wrapper)
        assert all("http://" not in value and "https://" not in value for value in strings)
        assert all("/Users/" not in value and "@" not in value for value in strings)
        assert all(
            "://" not in value or value.startswith("local://synthetic-m4") for value in strings
        )
        planned = wrapper["planned_verified_run"]
        query_plan = planned["query_plan"]
        assert query_plan["original_query"] == (
            "Does the scoped rule apply to Region Beta with Service Basic?"
        )
        assert query_plan["normalised_query"] == query_plan["original_query"]
        result = planned["verified_run"]["result"]
        for item in result["evidence"] + result["retrieved_sections"]:
            assert item["source_ref"].startswith("local://synthetic-m4/")
        assert all(
            value.startswith("local://synthetic-m4/")
            for value in planned["verified_run"]["verification"]["evidence_refs"]
        )


def test_counterfactual_catalog_matches_fixture_wrappers() -> None:
    catalog = load_json(M4C_ROOT / "counterfactual_fixture_catalog.json")
    catalog_by_variant = {item["variant_id"]: item for item in catalog["fixtures"]}
    for path in sorted(FIXTURE_ROOT.glob("*.planned.json")):
        wrapper = load_json(path)
        item = catalog_by_variant[wrapper["variant_id"]]
        assert item["baseline_plan_id"] == wrapper["baseline_plan_id"]
        assert item["context_delta"] == wrapper["context_delta"]
        assert item["fixture_ref"] == ("local://synthetic-m4c/counterfactual-runs/" + path.name)
        result = wrapper["planned_verified_run"]["verified_run"]["result"]
        assert item["actual_decision"] == result["decision"]
        assert item["actual_reason_codes"] == result["reason_codes"]
