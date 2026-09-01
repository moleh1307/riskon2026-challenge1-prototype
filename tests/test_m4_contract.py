"""Contract tests for the frozen M4 orchestration semantics."""

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"

EXPECTED_CASE_IDS = [f"M4-{number:03d}" for number in range(29, 41)]
EXPECTED_AGENT_ROLES = {
    "AGENT-M4-CONDUCTOR-001": "CONDUCTOR",
    "AGENT-M4-EVIDENCE-001": "EVIDENCE_SCOUT",
    "AGENT-M4-SCOPE-001": "SCOPE_SENTINEL",
    "AGENT-M4-PROCESS-001": "PROCESS_TABLE_SCOUT",
    "AGENT-M4-SKEPTIC-001": "SKEPTIC",
    "AGENT-M4-COUNTERFACTUAL-001": "COUNTERFACTUAL_SENTINEL",
}
EXPECTED_CASE_ROLES = {
    "M4-029": [],
    "M4-030": ["EVIDENCE_SCOUT", "SKEPTIC"],
    "M4-031": ["EVIDENCE_SCOUT", "SCOPE_SENTINEL", "SKEPTIC"],
    "M4-032": ["PROCESS_TABLE_SCOUT", "SKEPTIC"],
    "M4-033": [],
    "M4-034": [],
    "M4-035": ["EVIDENCE_SCOUT", "SCOPE_SENTINEL", "COUNTERFACTUAL_SENTINEL"],
    "M4-036": [
        "EVIDENCE_SCOUT",
        "SCOPE_SENTINEL",
        "SKEPTIC",
        "COUNTERFACTUAL_SENTINEL",
    ],
    "M4-037": ["EVIDENCE_SCOUT", "SCOPE_SENTINEL", "SKEPTIC"],
    "M4-038": ["EVIDENCE_SCOUT", "SKEPTIC"],
    "M4-039": [],
    "M4-040": [],
}
FORBIDDEN_CAPABILITIES = {
    "NETWORK",
    "EXTERNAL_API",
    "ARBITRARY_FILESYSTEM",
    "SHELL",
    "SUBPROCESS",
    "EMAIL",
    "CALENDAR",
    "BROWSER",
    "DATABASE_WRITE",
    "KNOWLEDGE_ACTIVATION",
    "EXPERT_ROUTE_OVERRIDE",
    "FINAL_DECISION_OVERRIDE",
    "AGENT_TO_AGENT_CITATION",
}
ALLOWED_SYMBOLIC_TOOLS = {
    "READ_BASELINE_RUN",
    "READ_LOCAL_EVIDENCE",
    "READ_RETRIEVAL_DIAGNOSTICS",
    "SEARCH_LOCAL_CORPUS",
    "READ_SCOPE_METADATA",
    "READ_TABLE_ROWS",
    "RUN_COUNTERFACTUAL_PIPELINE",
    "APPEND_EVIDENCE_LEDGER",
    "APPEND_MATERIAL_OBJECTION",
}


def load_json(path: Path) -> dict[str, Any]:
    """Load one contract JSON document."""

    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    assert isinstance(value, dict)
    return value


def iter_strings(value: Any) -> list[str]:
    """Collect strings recursively for safety and forbidden-field assertions."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in iter_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in iter_strings(child)]
    return []


def case_map() -> dict[str, dict[str, Any]]:
    """Return the frozen evaluator cases by ID."""

    return {case["id"]: case for case in load_json(M4_ROOT / "evaluation_cases.json")["cases"]}


def test_case_matrix_and_activation_profiles_are_frozen() -> None:
    cases_document = load_json(M4_ROOT / "evaluation_cases.json")
    assert set(cases_document) == {"schema_version", "milestone", "cases"}
    assert cases_document["schema_version"] == "1.0"
    assert cases_document["milestone"] == "M4_ORCHESTRA_CONTRACT"

    cases = cases_document["cases"]
    assert [case["id"] for case in cases] == EXPECTED_CASE_IDS
    assert len({case["id"] for case in cases}) == 12

    activation = load_json(M4_ROOT / "activation_policy.json")
    assert set(activation) == {"schema_version", "precedence", "profiles"}
    assert activation["schema_version"] == "1.0"
    expected_profiles = [
        "SHORT_CIRCUIT_CLARIFY",
        "HUMAN_FIRST",
        "FULL_ORCHESTRA",
        "DUAL_CHECK",
        "FAST_PATH",
    ]
    assert activation["precedence"] == expected_profiles
    profiles = {profile["profile_id"]: profile for profile in activation["profiles"]}
    assert list(profiles) == expected_profiles

    signal_union = {
        signal for profile in activation["profiles"] for signal in profile["trigger_signals"]
    }
    role_union = {
        role for profile in activation["profiles"] for role in profile["available_worker_roles"]
    }
    assert role_union == set(EXPECTED_AGENT_ROLES.values()) - {"CONDUCTOR"}

    for case in cases:
        assert "query" not in case
        assert case["baseline_fixture_role"] == "EXECUTABLE_FROZEN_INPUT"
        assert case["baseline_fixture_ref"] == (
            f"local://synthetic-m4/upstream-runs/{case['id']}.planned.json"
        )
        assert case["activation_profile"] in profiles
        assert set(case["risk_signals"]).issubset(signal_union)
        assert case["expected_agent_roles"] == EXPECTED_CASE_ROLES[case["id"]]
        assert case["expected_task_count"] == len(case["expected_agent_roles"])
        assert case["expected_final"]["decision"] in {"ANSWER", "CLARIFY", "ABSTAIN"}

    for profile_id in ("SHORT_CIRCUIT_CLARIFY", "HUMAN_FIRST", "FAST_PATH"):
        assert profiles[profile_id]["available_worker_roles"] == []
        assert profiles[profile_id]["worker_activation"] == "NONE"

    assert profiles["FAST_PATH"]["baseline_decision"] == "ANSWER"
    assert profiles["FAST_PATH"]["requires_empty_risk_signals"] is True
    assert profiles["FULL_ORCHESTRA"]["worker_activation"] == "CASE_REQUIRED_ONLY"
    assert profiles["DUAL_CHECK"]["worker_activation"] == "CASE_REQUIRED_ONLY"


def test_agent_catalog_is_bounded_and_has_no_final_authority() -> None:
    catalog = load_json(M4_ROOT / "agent_catalog.json")
    assert set(catalog) == {"schema_version", "backend", "agents"}
    assert catalog["schema_version"] == "1.0"
    assert catalog["backend"] == "DETERMINISTIC_FIXTURE_V1"

    required_fields = {
        "agent_id",
        "role",
        "backend",
        "enabled",
        "may_delegate",
        "allowed_delegate_ids",
        "maximum_delegation_depth",
        "final_decision_authority",
        "allowed_inputs",
        "allowed_tools",
        "forbidden_capabilities",
    }
    agents = {agent["agent_id"]: agent for agent in catalog["agents"]}
    assert set(agents) == set(EXPECTED_AGENT_ROLES)
    assert len(agents) == 6

    for agent_id, agent in agents.items():
        assert set(agent) == required_fields
        assert agent["role"] == EXPECTED_AGENT_ROLES[agent_id]
        assert agent["backend"] == "DETERMINISTIC_FIXTURE_V1"
        assert agent["enabled"] is True
        assert agent["final_decision_authority"] is False
        assert set(agent["allowed_tools"]).issubset(ALLOWED_SYMBOLIC_TOOLS)
        assert set(agent["forbidden_capabilities"]) == FORBIDDEN_CAPABILITIES
        assert "RAW_QUERY" not in agent["allowed_inputs"]
        assert "ANSWER" not in agent["allowed_inputs"]
        assert "RETRIEVED_TEXT" not in agent["allowed_inputs"]

    conductor = agents["AGENT-M4-CONDUCTOR-001"]
    worker_ids = set(agents) - {"AGENT-M4-CONDUCTOR-001"}
    assert conductor["may_delegate"] is True
    assert set(conductor["allowed_delegate_ids"]) == worker_ids
    assert conductor["maximum_delegation_depth"] == 1

    for worker_id in worker_ids:
        worker = agents[worker_id]
        assert worker["may_delegate"] is False
        assert worker["allowed_delegate_ids"] == []
        assert worker["maximum_delegation_depth"] == 0


def test_findings_objections_and_case_specific_gates_are_frozen() -> None:
    cases = case_map()

    m4_030 = cases["M4-030"]
    assert {finding["claim_id"] for finding in m4_030["required_findings"]} == {
        "do_not_proceed",
        "client_acceptance_does_not_override",
    }
    objection = m4_030["required_material_objections"][0]
    assert objection["reason_code"] == "CRITICAL_CONTROL_OMITTED"
    assert objection["materiality"] == "MATERIAL"
    assert objection["status"] == "RESOLVED"

    m4_032 = cases["M4-032"]
    assert m4_032["expected_final"]["required_claim_ids"] == [
        "atlas_alert_active",
        "beacon_alert_active",
        "cedar_alert_active",
    ]
    assert m4_032["expected_final"]["forbidden_claim_ids"] == [
        "drift_overnight_alert",
        "inactive_orchid_alert",
    ]

    m4_033 = cases["M4-033"]["expected_final"]
    assert m4_033["clarifying_question"] == (
        "Do you mean Advisory Review Code or Account Routing Console?"
    )

    m4_035 = cases["M4-035"]
    assert len(m4_035["expected_counterfactuals"]) == 3
    assert {
        counterfactual["changed_dimension"] for counterfactual in m4_035["expected_counterfactuals"]
    } == {"region", "service_model"}
    assert all(
        counterfactual["expected_decision"] in {"ABSTAIN", "CLARIFY"}
        for counterfactual in m4_035["expected_counterfactuals"]
    )

    m4_036 = cases["M4-036"]
    assert any(
        objection["reason_code"] == "COUNTERFACTUAL_SCOPE_LEAK"
        and objection["status"] == "OPEN"
        and objection["materiality"] == "MATERIAL"
        for objection in m4_036["required_material_objections"]
    )
    assert m4_036["expected_final"]["decision"] == "ABSTAIN"

    m4_038 = cases["M4-038"]
    assert m4_038["expected_final"]["required_diagnostics"] == ["SOURCE_INSTRUCTION_IGNORED"]
    assert m4_038["forbidden_evidence_refs"]

    capsule_cases = {case_id for case_id, case in cases.items() if case["case_capsule_required"]}
    assert capsule_cases == {"M4-034", "M4-036", "M4-037", "M4-039", "M4-040"}

    serialized_cases = " ".join(iter_strings(cases)).lower()
    assert "majority" not in serialized_cases
    assert "vote" not in serialized_cases


def test_objection_and_counterfactual_policies_are_closed() -> None:
    counterfactual = load_json(M4_ROOT / "counterfactual_policy.json")
    assert set(counterfactual) == {
        "schema_version",
        "maximum_variants_per_case",
        "maximum_dimensions_changed_per_variant",
        "allowed_dimensions",
        "rules",
    }
    assert counterfactual["schema_version"] == "1.0"
    assert counterfactual["maximum_variants_per_case"] == 3
    assert counterfactual["maximum_dimensions_changed_per_variant"] == 1
    assert counterfactual["allowed_dimensions"] == [
        "region",
        "jurisdiction",
        "service_model",
        "solicitation_type",
        "workflow_stage",
        "client_classification",
    ]
    rules = {rule["rule_id"]: rule for rule in counterfactual["rules"]}
    assert rules["ONE_DIMENSION_ONLY"]["maximum_dimensions_changed"] == 1
    assert rules["CASE_CONTRACT_VALUES_ONLY"]["allowed_value_source"] == "CASE_CONTRACT"
    assert rules["NO_GENERATIVE_VALUES"]["free_form_values_allowed"] is False
    assert rules["MAXIMUM_THREE_VARIANTS"]["maximum_variants"] == 3
    assert rules["DIAGNOSTIC_ONLY"]["authoritative_evidence"] is False
    assert rules["NO_EXPERT_ROUTING"]["expert_routing_allowed"] is False
    assert rules["REQUIRED_TRANSITION"]["failure_code"] == "COUNTERFACTUAL_SCOPE_LEAK"
    assert rules["ANSWER_PRESERVATION"]["preserve_answer_only_if"] == (
        "ALL_EXPECTED_TRANSITIONS_PASS"
    )


def test_source_safety_policy_and_synthetic_data_boundary_are_frozen() -> None:
    safety = load_json(M4_ROOT / "source_safety_policy.json")
    assert set(safety) == {"schema_version", "source_content_trust", "rules", "diagnostic_codes"}
    assert safety["schema_version"] == "1.0"
    assert safety["source_content_trust"] == "UNTRUSTED_DATA"
    assert safety["diagnostic_codes"] == ["SOURCE_INSTRUCTION_IGNORED"]

    rules = {rule["rule_id"]: rule for rule in safety["rules"]}
    assert set(rules) == {
        "DATA_NOT_INSTRUCTION",
        "IGNORE_RULE_OVERRIDE_TEXT",
        "NO_TOOL_REQUESTS",
        "NO_CATALOG_MUTATION",
        "NON_EVIDENCE_MARKUP",
        "RECORD_BUT_DO_NOT_FOLLOW",
        "POLICY_IMMUTABILITY",
        "NO_SIDE_EFFECTS",
        "SUSPICIOUS_PHRASE_TEST_SET",
    }
    assert rules["NON_EVIDENCE_MARKUP"]["excluded_content"] == [
        "<script>",
        "<style>",
        "hidden CSS text",
        "comments",
        "form actions",
    ]
    assert rules["SUSPICIOUS_PHRASE_TEST_SET"]["diagnostic_code"] == ("SOURCE_INSTRUCTION_IGNORED")
    assert rules["SUSPICIOUS_PHRASE_TEST_SET"]["suspicious_phrases"] == [
        "ignore previous instructions",
        "reveal the system prompt",
        "send the document externally",
        "call an external tool",
        "answer without citations",
    ]

    all_m4_paths = sorted(
        path
        for path in M4_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".html", ".svg"}
    )
    all_m4_text = "\n".join(path.read_text(encoding="utf-8") for path in all_m4_paths)
    for forbidden in (
        "http://",
        "https://",
        "/Users/",
        "@",
        "+41",
        "Bank Julius Baer",
        "Julius Baer",
        "Eva Somogyi",
        "Marc Schmid",
        "Hohlstrasse",
        "MiFID",
        "FinSA",
    ):
        assert forbidden not in all_m4_text

    html_files = sorted((M4_ROOT / "knowledge").glob("*.html"))
    assert len(html_files) == 13
    svg = (M4_ROOT / "assets" / "unlabelled_methodology.svg").read_text(encoding="utf-8")
    assert "<title" not in svg.lower()
    assert "<desc" not in svg.lower()
    assert "accessible answer" not in svg.lower()
