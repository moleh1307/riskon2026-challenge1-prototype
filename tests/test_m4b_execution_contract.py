"""Contract freeze for the M4B bounded deterministic worker orchestra."""

import json
import tomllib
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"
M4B_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4b"
POLICY_PATH = M4B_ROOT / "worker_selection_policy.json"
CONFIG_PATH = PROJECT_ROOT / "config" / "milestone4b.toml"

CANONICAL_ROLE_ORDER = [
    "EVIDENCE_SCOUT",
    "SCOPE_SENTINEL",
    "PROCESS_TABLE_SCOUT",
    "SKEPTIC",
    "COUNTERFACTUAL_SENTINEL",
]

EXPECTED_SIGNAL_MAPPINGS = {
    "CRITICAL_CONTROL_RISK": ("EVIDENCE_SCOUT", "SKEPTIC"),
    "SCOPE_SENSITIVE": ("EVIDENCE_SCOUT", "SCOPE_SENTINEL", "SKEPTIC"),
    "JURISDICTION_SENSITIVE": ("EVIDENCE_SCOUT", "SCOPE_SENTINEL", "SKEPTIC"),
    "TABLE_DEPENDENT": ("PROCESS_TABLE_SCOUT", "SKEPTIC"),
    "CONTRADICTORY_SOURCES": ("EVIDENCE_SCOUT", "SCOPE_SENTINEL", "SKEPTIC"),
    "PROMPT_INJECTION_SIGNAL": ("EVIDENCE_SCOUT", "SKEPTIC"),
    "COUNTERFACTUAL_REQUIRED": ("COUNTERFACTUAL_SENTINEL",),
}

EXPECTED_CASE_GRAPH = {
    "M4-030": {
        "profile": "DUAL_CHECK",
        "discovery": ["EVIDENCE_SCOUT"],
        "challenge": ["SKEPTIC"],
        "tasks": 2,
    },
    "M4-031": {
        "profile": "FULL_ORCHESTRA",
        "discovery": ["EVIDENCE_SCOUT", "SCOPE_SENTINEL"],
        "challenge": ["SKEPTIC"],
        "tasks": 3,
    },
    "M4-032": {
        "profile": "DUAL_CHECK",
        "discovery": ["PROCESS_TABLE_SCOUT"],
        "challenge": ["SKEPTIC"],
        "tasks": 2,
    },
    "M4-037": {
        "profile": "FULL_ORCHESTRA",
        "discovery": ["EVIDENCE_SCOUT", "SCOPE_SENTINEL"],
        "challenge": ["SKEPTIC"],
        "tasks": 3,
    },
    "M4-038": {
        "profile": "DUAL_CHECK",
        "discovery": ["EVIDENCE_SCOUT"],
        "challenge": ["SKEPTIC"],
        "tasks": 2,
    },
}


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object for contract assertions."""

    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_worker_selection_policy_is_frozen() -> None:
    policy = load_json(POLICY_PATH)

    assert set(policy) == {
        "schema_version",
        "backend",
        "maximum_worker_depth",
        "maximum_parallel_discovery_workers",
        "maximum_challenge_rounds",
        "canonical_role_order",
        "signal_mappings",
    }
    assert policy["schema_version"] == "1.0"
    assert policy["backend"] == "DETERMINISTIC_WORKER_V1"
    assert policy["maximum_worker_depth"] == 1
    assert policy["maximum_parallel_discovery_workers"] == 3
    assert policy["maximum_challenge_rounds"] == 1
    assert policy["canonical_role_order"] == CANONICAL_ROLE_ORDER

    mappings = policy["signal_mappings"]
    assert isinstance(mappings, list)
    assert [item["risk_signal"] for item in mappings] == list(EXPECTED_SIGNAL_MAPPINGS)
    for mapping in mappings:
        assert set(mapping) == {"risk_signal", "required_agent_roles", "status"}
        signal = mapping["risk_signal"]
        assert mapping["required_agent_roles"] == list(EXPECTED_SIGNAL_MAPPINGS[signal])
        assert mapping["status"] == (
            "NOT_IMPLEMENTED" if signal == "COUNTERFACTUAL_REQUIRED" else "IMPLEMENTED"
        )
        assert all(role in CANONICAL_ROLE_ORDER for role in mapping["required_agent_roles"])


def test_m4b_config_is_closed_and_points_to_m4a() -> None:
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert set(config) == {"base", "orchestra", "evaluation", "security"}
    assert config["base"] == {"config": "config/milestone4a.toml"}
    assert set(config["orchestra"]) == {"m4b"}
    m4b = config["orchestra"]["m4b"]
    assert m4b == {
        "worker_selection_policy": "data/synthetic/m4b/worker_selection_policy.json",
        "worker_backend": "DETERMINISTIC_WORKER_V1",
        "implemented_roles": [
            "EVIDENCE_SCOUT",
            "SCOPE_SENTINEL",
            "PROCESS_TABLE_SCOUT",
            "SKEPTIC",
        ],
        "unsupported_roles": ["COUNTERFACTUAL_SENTINEL"],
        "maximum_worker_depth": 1,
        "maximum_parallel_discovery_workers": 3,
        "maximum_challenge_rounds": 1,
        "generated_root": "data/generated/m4b",
    }
    assert config["evaluation"] == {
        "included_cases": list(EXPECTED_CASE_GRAPH),
        "expected_cases": 5,
        "expected_dual_check": 3,
        "expected_full_orchestra_non_counterfactual": 2,
        "expected_worker_tasks": 12,
        "expected_recovered_answers": 3,
        "expected_final_abstentions": 1,
        "expected_injection_safe_answers": 1,
    }
    assert config["security"] == {
        "network_enabled": False,
        "agent_to_agent_citation_enabled": False,
        "recursive_delegation_enabled": False,
    }


def test_exact_m4b_task_graph_is_frozen() -> None:
    assert list(EXPECTED_CASE_GRAPH) == ["M4-030", "M4-031", "M4-032", "M4-037", "M4-038"]

    total_tasks = 0
    discovery_tasks = 0
    skeptic_tasks = 0
    for case in EXPECTED_CASE_GRAPH.values():
        assert case["challenge"] == ["SKEPTIC"]
        assert case["tasks"] == len(case["discovery"]) + len(case["challenge"])
        total_tasks += case["tasks"]
        discovery_tasks += len(case["discovery"])
        skeptic_tasks += len(case["challenge"])

    assert total_tasks == 12
    assert discovery_tasks == 7
    assert skeptic_tasks == 5


def test_m4b_cases_and_frozen_inputs_are_present() -> None:
    cases = load_json(M4_ROOT / "evaluation_cases.json")["cases"]
    case_map = {case["id"]: case for case in cases}
    assert set(EXPECTED_CASE_GRAPH).issubset(case_map)
    for case_id, expected in EXPECTED_CASE_GRAPH.items():
        assert case_map[case_id]["activation_profile"] == expected["profile"]
        assert case_map[case_id]["expected_agent_roles"] == (
            expected["discovery"] + expected["challenge"]
        )
        assert case_map[case_id]["expected_task_count"] == expected["tasks"]
        assert (M4_ROOT / "upstream_runs" / f"{case_id}.planned.json").is_file()
