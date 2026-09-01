"""Contract freeze for the M4C counterfactual sentinel."""

import json
import tomllib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4C_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4c"
CONFIG_PATH = PROJECT_ROOT / "config" / "milestone4c.toml"

EXPECTED_VARIANTS = {
    "M4-035": [
        {
            "variant_id": "M4-035-CF-01",
            "dimension": "region",
            "operation": "REPLACE",
            "from_value": "REGION_BETA",
            "to_value": "REGION_ALPHA",
            "expectation_rule_id": "EXACT_SCOPE_REPLACED",
            "expected_decision": "ABSTAIN",
            "expected_reason_codes": ["SCOPE_MISMATCH"],
            "actual_fixture_ref": (
                "local://synthetic-m4c/counterfactual-runs/M4-035-region-alpha.planned.json"
            ),
        },
        {
            "variant_id": "M4-035-CF-02",
            "dimension": "service_model",
            "operation": "REPLACE",
            "from_value": "SERVICE_BASIC",
            "to_value": "SERVICE_PLUS",
            "expectation_rule_id": "EXACT_SCOPE_REPLACED",
            "expected_decision": "ABSTAIN",
            "expected_reason_codes": ["SCOPE_MISMATCH"],
            "actual_fixture_ref": (
                "local://synthetic-m4c/counterfactual-runs/M4-035-service-plus.planned.json"
            ),
        },
        {
            "variant_id": "M4-035-CF-03",
            "dimension": "region",
            "operation": "REMOVE",
            "from_value": "REGION_BETA",
            "to_value": None,
            "expectation_rule_id": "REQUIRED_CONTEXT_REMOVED",
            "expected_decision": "CLARIFY",
            "expected_reason_codes": ["MISSING_REQUIRED_CONTEXT"],
            "actual_fixture_ref": (
                "local://synthetic-m4c/counterfactual-runs/M4-035-region-removed.planned.json"
            ),
        },
    ],
    "M4-036": [
        {
            "variant_id": "M4-036-CF-01",
            "dimension": "service_model",
            "operation": "REPLACE",
            "from_value": "SERVICE_BASIC",
            "to_value": "SERVICE_PLUS",
            "expectation_rule_id": "EXACT_SCOPE_REPLACED",
            "expected_decision": "ABSTAIN",
            "expected_reason_codes": ["SCOPE_MISMATCH"],
            "actual_fixture_ref": (
                "local://synthetic-m4c/counterfactual-runs/M4-036-service-plus.planned.json"
            ),
        }
    ],
}


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object for contract assertions."""

    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_m4c_config_is_closed_and_points_to_m4b() -> None:
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert set(config) == {"base", "orchestra", "evaluation", "security"}
    assert config["base"] == {"config": "config/milestone4b.toml"}
    assert set(config["orchestra"]) == {"m4c"}
    assert config["orchestra"]["m4c"] == {
        "evaluation_cases": "data/synthetic/m4c/evaluation_cases.json",
        "execution_policy": "data/synthetic/m4c/counterfactual_execution_policy.json",
        "context_value_registry": "data/synthetic/m4c/context_value_registry.json",
        "fixture_catalog": "data/synthetic/m4c/counterfactual_fixture_catalog.json",
        "worker_selection_extension": "data/synthetic/m4c/worker_selection_extension.json",
        "fixture_root": "data/synthetic/m4c/counterfactual_runs",
        "fixture_backend": "FROZEN_COUNTERFACTUAL_FIXTURE_V1",
        "runtime_backend": "LOCAL_PLANNED_PIPELINE_V1",
        "maximum_parallel_variants": 3,
        "maximum_counterfactual_depth": 1,
        "implemented_dimensions": ["region", "service_model"],
        "generated_root": "data/generated/m4c",
    }
    assert config["evaluation"] == {
        "included_cases": ["M4-035", "M4-036"],
        "expected_cases": 2,
        "expected_counterfactual_variants": 4,
        "expected_safe_transition_passes": 3,
        "expected_scope_leaks": 1,
        "expected_final_answers": 1,
        "expected_final_abstentions": 1,
        "expected_brm_queue_routes": 1,
        "expected_worker_tasks": 7,
    }
    assert config["security"] == {
        "network_enabled": False,
        "counterfactual_routing_enabled": False,
        "recursive_orchestration_enabled": False,
        "agent_to_agent_citation_enabled": False,
    }


def test_m4c_case_contract_is_exact_and_case_ids_do_not_drive_variants() -> None:
    document = load_json(M4C_ROOT / "evaluation_cases.json")
    assert set(document) == {"schema_version", "milestone", "cases"}
    assert document["schema_version"] == "1.0"
    assert document["milestone"] == "M4C_COUNTERFACTUAL_SENTINEL"
    cases = document["cases"]
    assert [case["id"] for case in cases] == ["M4-035", "M4-036"]

    for case in cases:
        assert set(case) == {
            "id",
            "m4_contract_ref",
            "baseline_fixture_ref",
            "runner_backend",
            "expected_agent_roles",
            "expected_task_count",
            "variants",
            "expected_material_objections",
            "expected_final",
            "expected_route",
        }
        assert "query" not in case
        assert case["runner_backend"] == "FROZEN_COUNTERFACTUAL_FIXTURE_V1"
        assert case["baseline_fixture_ref"] == (
            f"local://synthetic-m4/upstream-runs/{case['id']}.planned.json"
        )
        assert case["variants"] == EXPECTED_VARIANTS[case["id"]]
        assert case["expected_task_count"] == len(case["expected_agent_roles"])

    assert cases[0]["expected_agent_roles"] == [
        "EVIDENCE_SCOUT",
        "SCOPE_SENTINEL",
        "COUNTERFACTUAL_SENTINEL",
    ]
    assert cases[1]["expected_agent_roles"] == [
        "EVIDENCE_SCOUT",
        "SCOPE_SENTINEL",
        "SKEPTIC",
        "COUNTERFACTUAL_SENTINEL",
    ]


def test_m4c_policy_registry_extension_and_fixture_catalog_are_closed() -> None:
    policy = load_json(M4C_ROOT / "counterfactual_execution_policy.json")
    assert set(policy) == {
        "schema_version",
        "base_policy_ref",
        "fixture_backend",
        "runtime_backend",
        "implemented_dimensions",
        "maximum_variants_per_case",
        "maximum_parallel_variants",
        "maximum_dimensions_changed_per_variant",
        "variant_precedence",
        "recursive_orchestration_enabled",
        "counterfactual_routing_enabled",
        "expectation_rules",
    }
    assert policy["schema_version"] == "1.0"
    assert policy["base_policy_ref"] == "local://synthetic-m4/counterfactual_policy.json"
    assert policy["fixture_backend"] == "FROZEN_COUNTERFACTUAL_FIXTURE_V1"
    assert policy["runtime_backend"] == "LOCAL_PLANNED_PIPELINE_V1"
    assert policy["implemented_dimensions"] == ["region", "service_model"]
    assert policy["maximum_variants_per_case"] == 3
    assert policy["maximum_parallel_variants"] == 3
    assert policy["maximum_dimensions_changed_per_variant"] == 1
    assert policy["variant_precedence"] == [
        "region:REPLACE",
        "service_model:REPLACE",
        "region:REMOVE",
    ]
    assert policy["recursive_orchestration_enabled"] is False
    assert policy["counterfactual_routing_enabled"] is False
    assert [rule["rule_id"] for rule in policy["expectation_rules"]] == [
        "EXACT_SCOPE_REPLACED",
        "REQUIRED_CONTEXT_REMOVED",
    ]
    assert policy["expectation_rules"][0]["expected_decision"] == "ABSTAIN"
    assert policy["expectation_rules"][0]["expected_reason_code"] == "SCOPE_MISMATCH"
    assert policy["expectation_rules"][1]["expected_decision"] == "CLARIFY"
    assert policy["expectation_rules"][1]["expected_reason_code"] == ("MISSING_REQUIRED_CONTEXT")

    registry = load_json(M4C_ROOT / "context_value_registry.json")
    assert set(registry) == {"schema_version", "dimensions"}
    assert registry["schema_version"] == "1.0"
    assert [item["dimension"] for item in registry["dimensions"]] == [
        "region",
        "service_model",
    ]
    assert registry["dimensions"][0]["values"] == ["REGION_ALPHA", "REGION_BETA"]
    assert registry["dimensions"][1]["values"] == ["SERVICE_BASIC", "SERVICE_PLUS"]
    for item in registry["dimensions"]:
        assert set(item) == {"dimension", "values", "replacements"}
        assert len(item["values"]) == 2
        assert len(item["replacements"]) == 2
        assert all(
            replacement["from"] != replacement["to"]
            and replacement["from"] in item["values"]
            and replacement["to"] in item["values"]
            for replacement in item["replacements"]
        )

    extension = load_json(M4C_ROOT / "worker_selection_extension.json")
    assert extension == {
        "schema_version": "1.0",
        "extends": "local://synthetic-m4b/worker-selection-policy.json",
        "backend": "DETERMINISTIC_WORKER_V1",
        "implemented_roles": ["COUNTERFACTUAL_SENTINEL"],
    }

    catalog = load_json(M4C_ROOT / "counterfactual_fixture_catalog.json")
    assert set(catalog) == {"schema_version", "fixture_origin", "backend", "fixtures"}
    assert catalog["schema_version"] == "1.0"
    assert catalog["fixture_origin"] == "SYNTHETIC_COUNTERFACTUAL_RUN_V1"
    assert catalog["backend"] == "FROZEN_COUNTERFACTUAL_FIXTURE_V1"
    assert [item["variant_id"] for item in catalog["fixtures"]] == [
        "M4-035-CF-01",
        "M4-035-CF-02",
        "M4-035-CF-03",
        "M4-036-CF-01",
    ]
