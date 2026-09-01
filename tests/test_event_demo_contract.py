"""ER-B contract-freeze tests: fixtures and configuration only."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = ROOT / "data" / "synthetic" / "event_demo"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_event_demo_config_is_closed_and_local() -> None:
    raw = tomllib.loads((ROOT / "config" / "event_demo.toml").read_text(encoding="utf-8"))
    assert set(raw) == {"runtime", "rendering", "demo", "dashboard", "security"}
    assert raw["runtime"]["pipeline_config"] == "config/milestone5b.toml"
    assert raw["runtime"]["event_intake_config"] == "config/event_readiness.toml"
    assert raw["rendering"] == {
        "language": "en",
        "self_contained_html": True,
        "external_assets_enabled": False,
        "maximum_evidence_excerpt_characters": 280,
        "include_private_reasoning": False,
        "include_raw_source_html": False,
        "include_absolute_paths": False,
    }
    assert raw["security"] == {
        "network_enabled": False,
        "external_api_enabled": False,
        "telemetry_enabled": False,
        "local_server_enabled": False,
    }
    assert raw["demo"]["included_cases"] == [
        "ERB-001",
        "ERB-002",
        "ERB-003",
        "ERB-004",
        "ERB-005",
    ]


def test_demo_case_contract_has_exact_story_matrix() -> None:
    contract = _json(DEMO_ROOT / "demo_cases.json")
    assert contract["schema_version"] == "1.0"
    assert contract["milestone"] == "ER-B_THIN_LOCAL_DEMO"
    cases = contract["cases"]
    assert [case["id"] for case in cases] == [
        "ERB-001",
        "ERB-002",
        "ERB-003",
        "ERB-004",
        "ERB-005",
    ]
    assert [case["source_case_id"] for case in cases] == [
        "M4D-041",
        "M4D-042",
        "M4D-045",
        "M4D-043",
        "M5A-046",
    ]
    assert [case["expected_decision"] for case in cases] == [
        "ANSWER",
        "CLARIFY",
        "ANSWER",
        "ABSTAIN",
        "ANSWER",
    ]
    assert cases[1]["expected_clarifying_question"] == (
        "Do you mean Advisory Review Code or Account Routing Console?"
    )
    assert cases[2]["expected_agent_roles"] == [
        "EVIDENCE_SCOUT",
        "SCOPE_SENTINEL",
        "COUNTERFACTUAL_SENTINEL",
    ]
    assert cases[3]["expected_route"]["support_function"] == "BUSINESS_FRONT_SUPPORT"
    assert cases[4]["expected_governance_checks"]["policy_ci"] == {
        "matched": 11,
        "expected": 11,
    }


def test_dashboard_and_presentation_contracts_are_complete() -> None:
    dashboard = _json(DEMO_ROOT / "dashboard_contract.json")
    assert dashboard["decision_labels"] == ["ANSWER", "CLARIFY", "ABSTAIN"]
    metric_ids = [item["id"] for item in dashboard["metric_definitions"]]
    assert metric_ids == [
        "m0_m4d_regression",
        "m5b_governed_evolution",
        "policy_ci_checks",
        "counterfactual_transitions",
        "scope_violations",
        "unsupported_claims",
        "unsafe_routing",
        "automatic_approvals",
        "automatic_activations",
        "network_violations",
    ]
    assert len(dashboard["safety_metric_definitions"]) == 7

    copy = _json(DEMO_ROOT / "presentation_copy.json")
    assert copy["title"] == "RiskON Orchestra"
    assert copy["tagline"] == "Many agents investigate. Evidence decides. Humans approve."
    assert copy["status_chips"] == [
        "OFFLINE",
        "SYNTHETIC DEMO",
        "NO EXTERNAL API",
        "AUDIT ENABLED",
    ]
    assert copy["sections"] == [
        "Live Product Stories",
        "Evaluation Dashboard",
        "Architecture & Governance",
    ]
    assert [item["node"] for item in copy["architecture"]] == [
        "Question",
        "Event Corpus Adapter",
        "Query Planner",
        "Hybrid Retrieval",
        "Context & Scope Detection",
        "Risk-Adaptive Orchestra",
        "Evidence Constitution",
        "ANSWER / CLARIFY / ABSTAIN",
        "Expert Router",
        "Governed Knowledge Patch",
    ]
    assert copy["footer"] == [
        "Synthetic local demonstration for RiskON 2026.",
        "No real client or Bank data is included.",
        "This demo is not legal or investment advice.",
    ]


def test_context_presets_are_local_structured_inputs() -> None:
    contract = _json(DEMO_ROOT / "context_presets.json")
    assert contract["schema_version"] == "1.0"
    assert [item["id"] for item in contract["presets"]] == [
        "REGION_BETA_SERVICE_BASIC",
        "REGION_ALPHA_SERVICE_BASIC",
        "REGION_BETA_SERVICE_PLUS",
        "NO_CONTEXT",
    ]
    for preset in contract["presets"]:
        assert set(preset) == {"id", "label", "context"}
        assert all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in preset["context"].items()
        )
