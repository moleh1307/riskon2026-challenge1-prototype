"""Freeze the M3 routing contract before production code changes."""

import json
import re
from pathlib import Path

import pytest

from riskon.models import Decision, PlannedVerifiedRun

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M3_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m3"
EVALUATION_PATH = M3_ROOT / "evaluation_cases.json"
UPSTREAM_ROOT = M3_ROOT / "upstream_runs"
SUPPORT_MODEL_PATHS = [M3_ROOT / "support_model_v1.json", M3_ROOT / "support_model_v2.json"]
PROFILE_PATHS = [
    M3_ROOT / "expert_profiles_v1.json",
    M3_ROOT / "expert_profiles_capacity_stress.json",
    M3_ROOT / "expert_profiles_v2.json",
]
NETWORK_PATH = M3_ROOT / "network_edges.json"

ALLOWED_PROFILES = {"default", "capacity_stress", "support_v2"}
ALLOWED_NEED_TYPES = {
    "ROUTINE_PROCESS",
    "SYSTEM_GUIDANCE",
    "UNRESOLVED_REQUIRED_REFERENCE",
    "TECHNICAL_FAILURE",
    "COMPLEX_CASE",
    "SCOPE_MISMATCH",
    "UNSUPPORTED_MODALITY",
    "POLICY_INTERPRETATION",
    "NO_EXPLICIT_SUPPORT",
    "APPROVAL_REQUIRED",
}
ALLOWED_SUPPORT_FUNCTIONS = {
    "BUSINESS_FRONT_SUPPORT",
    "IT_SERVICE_DESK",
    "BRM_SUITABILITY_LEAD",
    "SUITABILITY_EXPERT_LEGAL",
    "SUITABILITY_EXPERT_COMPLIANCE",
}
ALLOWED_ROUTE_MODES = {"PERSON", "FUNCTIONAL_QUEUE"}
ALLOWED_CONFIDENCE_KINDS = {"DETERMINISTIC_ROUTING_HEURISTIC_V1"}
ALLOWED_EXCLUSION_REASONS = {
    "INACTIVE_PROFILE",
    "OUTSIDE_EFFECTIVE_WINDOW",
    "FUNCTION_MISMATCH",
    "MANDATE_MISMATCH",
    "JURISDICTION_CONFLICT",
    "REGION_CONFLICT",
    "SYSTEM_CONFLICT",
    "NOT_ACCEPTING_CASES",
}
REQUIRED_CASE_FIELDS = {
    "id",
    "source_scenario_id",
    "source_scenario_role",
    "upstream_fixture_ref",
    "routing_profile",
    "routing_context",
    "expected_legacy_route_function",
    "expected_route",
    "expected_candidates",
    "expected_explanation",
}
REQUIRED_ROUTING_CONTEXT_FIELDS = {
    "need_type",
    "reason_codes",
    "topics",
    "jurisdiction",
    "region",
    "system",
    "requester_team",
}
REQUIRED_ROUTE_FIELDS = {
    "support_function",
    "route_mode",
    "selected_expert_id",
    "queue_id",
    "support_model_version",
    "confidence_kind",
    "expected_fallback_reason",
}
REQUIRED_CANDIDATE_FIELDS = {
    "required_top3_ids",
    "forbidden_selected_ids",
    "required_exclusions",
}
REQUIRED_EXPLANATION_FIELDS = {
    "required_fields",
    "required_decisive_factors",
}
MANDATORY_EXPERT_FIELDS = {
    "expert_id",
    "display_name",
    "active",
    "effective_from",
    "effective_to",
    "support_function",
    "mandates",
    "topics",
    "jurisdictions",
    "regions",
    "systems",
    "network_node",
    "workload_ratio",
    "accepting_new_cases",
    "queue_id",
    "mandate_specificity",
}
ALLOWED_EXPLANATION_KEYS = {
    "function_reason",
    "hard_constraints_applied",
    "selected_candidate_factors",
    "alternative_candidates",
    "excluded_candidates",
    "fallback_reason",
}


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_path(ref: str) -> Path:
    prefix = "local://synthetic-m3/upstream-runs/"
    assert ref.startswith(prefix)
    return UPSTREAM_ROOT / ref.removeprefix(prefix)


def _source_ids() -> set[str]:
    m0 = _load_json(PROJECT_ROOT / "data" / "synthetic" / "scenarios.json")
    m1 = _load_json(PROJECT_ROOT / "data" / "synthetic" / "m1" / "evaluation_cases.json")
    return {str(item["id"]) for item in [*m0, *m1["cases"]]}


@pytest.fixture(scope="module")
def cases() -> list[dict[str, object]]:
    payload = _load_json(EVALUATION_PATH)
    assert payload["schema_version"] == "1.1"
    value = payload["cases"]
    assert isinstance(value, list)
    return value


def test_contract_contains_exactly_eight_cases(cases: list[dict[str, object]]) -> None:
    assert [case["id"] for case in cases] == [f"M3-{number:03d}" for number in range(21, 29)]
    assert len({case["id"] for case in cases}) == 8


def test_case_schema_is_closed_and_sources_are_real_fixtures(
    cases: list[dict[str, object]],
) -> None:
    source_ids = _source_ids()
    for case in cases:
        assert set(case) == REQUIRED_CASE_FIELDS
        assert case["source_scenario_id"] in source_ids
        assert case["source_scenario_role"] == "LINEAGE_ONLY"
        fixture_path = _fixture_path(str(case["upstream_fixture_ref"]))
        assert fixture_path.is_file()
        assert case["routing_profile"] in ALLOWED_PROFILES

        context = case["routing_context"]
        assert isinstance(context, dict)
        assert set(context) == REQUIRED_ROUTING_CONTEXT_FIELDS
        assert context["need_type"] in ALLOWED_NEED_TYPES
        assert set(context["reason_codes"]) <= ALLOWED_NEED_TYPES
        assert isinstance(context["topics"], list)

        expected_route = case["expected_route"]
        assert isinstance(expected_route, dict)
        assert set(expected_route) <= REQUIRED_ROUTE_FIELDS | {"routing_confidence"}
        assert REQUIRED_ROUTE_FIELDS <= set(expected_route)
        assert expected_route["support_function"] in ALLOWED_SUPPORT_FUNCTIONS
        assert expected_route["route_mode"] in ALLOWED_ROUTE_MODES
        assert expected_route["confidence_kind"] in ALLOWED_CONFIDENCE_KINDS
        if expected_route["selected_expert_id"] is not None:
            assert str(expected_route["selected_expert_id"]).startswith("SYN3-")
        assert str(expected_route["queue_id"]).startswith("QUEUE-")
        if "routing_confidence" in expected_route:
            assert expected_route["routing_confidence"] == 0.5

        candidates = case["expected_candidates"]
        assert isinstance(candidates, dict)
        assert set(candidates) == REQUIRED_CANDIDATE_FIELDS
        assert len(candidates["required_top3_ids"]) <= 3
        for expert_id in [
            *candidates["required_top3_ids"],
            *candidates["forbidden_selected_ids"],
        ]:
            assert str(expert_id).startswith("SYN3-")
        for exclusion in candidates["required_exclusions"]:
            assert set(exclusion) == {"expert_id", "reason"}
            assert exclusion["expert_id"].startswith("SYN3-")
            assert exclusion["reason"] in ALLOWED_EXCLUSION_REASONS

        explanation = case["expected_explanation"]
        assert isinstance(explanation, dict)
        assert set(explanation) == REQUIRED_EXPLANATION_FIELDS
        assert set(explanation["required_fields"]) <= ALLOWED_EXPLANATION_KEYS


def test_upstream_fixtures_are_full_abstain_planned_runs(cases: list[dict[str, object]]) -> None:
    for case in cases:
        fixture_path = _fixture_path(str(case["upstream_fixture_ref"]))
        fixture = _load_json(fixture_path)
        assert set(fixture) == {
            "fixture_schema_version",
            "fixture_origin",
            "source_scenario_id",
            "planned_verified_run",
        }
        assert fixture["fixture_schema_version"] == "1.0"
        assert fixture["fixture_origin"] == "SYNTHETIC_ROUTING_FIXTURE_V1"
        assert fixture["source_scenario_id"] == case["source_scenario_id"]
        planned = PlannedVerifiedRun.model_validate(fixture["planned_verified_run"])
        result = planned.verified_run.result
        report = planned.verified_run.verification
        assert result.decision is Decision.ABSTAIN
        assert result.answer is None
        assert result.clarifying_question is None
        assert result.route is not None
        assert result.route.expert_id is None
        assert result.route.support_function == case["expected_legacy_route_function"]
        assert report.status.value == "INSUFFICIENT"
        assert [reason.value for reason in result.reason_codes] == case["routing_context"][
            "reason_codes"
        ]
        assert [reason.value for reason in report.reason_codes] == case["routing_context"][
            "reason_codes"
        ]
        assert result.reason_codes


def test_routing_request_has_no_raw_query_fields(cases: list[dict[str, object]]) -> None:
    forbidden = {"query", "original_query", "normalised_query", "answer_text", "retrieved_raw_text"}
    for case in cases:
        context = case["routing_context"]
        assert not forbidden.intersection(context)


def test_exact_case_expectations(cases: list[dict[str, object]]) -> None:
    by_id = {str(case["id"]): case for case in cases}
    assert by_id["M3-026"]["expected_route"]["route_mode"] == "FUNCTIONAL_QUEUE"
    assert by_id["M3-026"]["expected_route"]["selected_expert_id"] is None
    assert by_id["M3-026"]["expected_route"]["routing_confidence"] == 0.500
    assert by_id["M3-026"]["expected_route"]["expected_fallback_reason"] == "LOW_SCORE_OR_MARGIN"

    m3027 = by_id["M3-027"]["expected_candidates"]["required_exclusions"]
    assert {"expert_id": "SYN3-BFS-ALPHA-001", "reason": "NOT_ACCEPTING_CASES"} in m3027

    m3028 = by_id["M3-028"]
    assert m3028["expected_route"]["support_model_version"] == "m3-v2"
    assert m3028["expected_route"]["selected_expert_id"] == "SYN3-BRM-BETA-002"

    assert by_id["M3-023"]["expected_candidates"]["required_exclusions"] == [
        {"expert_id": "SYN3-BRM-ALPHA-001", "reason": "REGION_CONFLICT"}
    ]
    assert (
        "network_proximity" in by_id["M3-024"]["expected_explanation"]["required_decisive_factors"]
    )


def test_support_model_files_are_versioned_and_closed_world() -> None:
    expected_pairs = {
        ("REASON_CODE", "TECHNICAL_FAILURE", "IT_SERVICE_DESK"),
        ("NEED_TYPE", "ROUTINE_PROCESS", "BUSINESS_FRONT_SUPPORT"),
        ("NEED_TYPE", "SYSTEM_GUIDANCE", "BUSINESS_FRONT_SUPPORT"),
        ("REASON_CODE", "UNRESOLVED_REQUIRED_REFERENCE", "BUSINESS_FRONT_SUPPORT"),
        ("NEED_TYPE", "COMPLEX_CASE", "BRM_SUITABILITY_LEAD"),
        ("REASON_CODE", "SCOPE_MISMATCH", "BRM_SUITABILITY_LEAD"),
        ("REASON_CODE", "UNSUPPORTED_MODALITY", "BRM_SUITABILITY_LEAD"),
        ("NEED_TYPE", "POLICY_INTERPRETATION", "SUITABILITY_EXPERT_LEGAL"),
        ("REASON_CODE", "NO_EXPLICIT_SUPPORT", "SUITABILITY_EXPERT_LEGAL"),
        ("NEED_TYPE", "APPROVAL_REQUIRED", "SUITABILITY_EXPERT_COMPLIANCE"),
    }
    for path in SUPPORT_MODEL_PATHS:
        payload = _load_json(path)
        assert payload["schema_version"] == "1.0"
        assert payload["support_model_version"] in {"m3-v1", "m3-v2"}
        rules = payload["rules"]
        actual_pairs = {
            (item["selector_type"], item["selector_value"], item["support_function"])
            for item in rules
        }
        assert actual_pairs == expected_pairs
        assert [item["priority"] for item in rules] == list(range(1, 11))
        assert {item["selector_type"] for item in rules} <= {"NEED_TYPE", "REASON_CODE"}
        assert {item["support_function"] for item in rules} <= ALLOWED_SUPPORT_FUNCTIONS


def test_expert_profiles_have_mandatory_synthetic_fields() -> None:
    profile_payloads = {path.name: _load_json(path) for path in PROFILE_PATHS}
    profile_ids: dict[str, set[str]] = {}
    for filename, payload in profile_payloads.items():
        assert payload["schema_version"] == "1.0"
        assert payload["expert_directory_version"] in {"m3-v1", "m3-v2"}
        profiles = payload["profiles"]
        assert profiles
        profile_ids[filename] = set()
        for profile in profiles:
            assert set(profile) == MANDATORY_EXPERT_FIELDS
            assert profile["expert_id"].startswith("SYN3-")
            assert profile["queue_id"].startswith("QUEUE-")
            assert profile["support_function"] in ALLOWED_SUPPORT_FUNCTIONS
            assert isinstance(profile["mandates"], list) and profile["mandates"]
            assert set(profile["mandates"]) <= ALLOWED_NEED_TYPES
            assert isinstance(profile["topics"], list) and profile["topics"]
            assert isinstance(profile["jurisdictions"], list) and profile["jurisdictions"]
            assert isinstance(profile["regions"], list) and profile["regions"]
            assert isinstance(profile["systems"], list) and profile["systems"]
            assert 0.0 <= profile["workload_ratio"] <= 1.0
            assert 0.0 <= profile["mandate_specificity"] <= 1.0
            profile_ids[filename].add(profile["expert_id"])
    assert (
        profile_ids["expert_profiles_v1.json"]
        == profile_ids["expert_profiles_capacity_stress.json"]
    )
    assert profile_ids["expert_profiles_v1.json"] == profile_ids["expert_profiles_v2.json"]

    default = {p["expert_id"]: p for p in profile_payloads["expert_profiles_v1.json"]["profiles"]}
    stressed = {
        p["expert_id"]: p
        for p in profile_payloads["expert_profiles_capacity_stress.json"]["profiles"]
    }
    v2 = {p["expert_id"]: p for p in profile_payloads["expert_profiles_v2.json"]["profiles"]}
    assert default["SYN3-BFS-ALPHA-001"]["accepting_new_cases"] is True
    assert stressed["SYN3-BFS-ALPHA-001"]["accepting_new_cases"] is False
    assert v2["SYN3-BRM-BETA-001"]["active"] is False
    assert v2["SYN3-BRM-BETA-002"]["active"] is True


def test_network_edges_are_synthetic_and_bounded() -> None:
    payload = _load_json(NETWORK_PATH)
    assert payload["schema_version"] == "1.0"
    assert payload["network_version"] == "m3-network-v1"
    edges = payload["edges"]
    assert edges
    for edge in edges:
        assert set(edge) == {"requester_team", "network_node", "weight"}
        assert edge["requester_team"].startswith("TEAM-")
        assert edge["network_node"].startswith("NODE-")
        assert 0.0 <= edge["weight"] <= 1.0


def test_contract_contains_no_real_data_or_paths() -> None:
    serialised = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            EVALUATION_PATH,
            *SUPPORT_MODEL_PATHS,
            *PROFILE_PATHS,
            NETWORK_PATH,
            *sorted(UPSTREAM_ROOT.glob("*.planned.json")),
        ]
    )
    assert "http://" not in serialised
    assert "https://" not in serialised
    assert "/Users/" not in serialised
    assert "juliusbaer" not in serialised.lower()
    assert "Julius Baer" not in serialised
    assert "@" not in serialised
    assert not re.search(r"\d{8,}", serialised)
    assert "+41" not in serialised
    assert "phone" not in serialised.lower()
    assert "real employee" not in serialised.lower()
