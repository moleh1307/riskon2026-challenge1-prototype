"""ER-B expected story-view contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = ROOT / "data" / "synthetic" / "event_demo"
CASE_IDS = ["ERB-001", "ERB-002", "ERB-003", "ERB-004", "ERB-005"]


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_expected_view_files_cover_the_five_cases() -> None:
    files = sorted(path.name for path in (DEMO_ROOT / "expected_views").glob("*.view.json"))
    assert files == [f"{case_id}.view.json" for case_id in CASE_IDS]


def test_expected_views_have_closed_common_shape() -> None:
    cases = {case["id"]: case for case in _json(DEMO_ROOT / "demo_cases.json")["cases"]}
    required = {
        "schema_version",
        "case_id",
        "source_case_id",
        "decision",
        "activation_profile",
        "agent_roles",
        "reason_codes",
        "answer_present",
        "clarifying_question",
        "route",
        "evidence_required",
        "counterfactuals",
        "governance",
        "audit_reference",
    }
    for case_id in CASE_IDS:
        view = _json(DEMO_ROOT / "expected_views" / f"{case_id}.view.json")
        assert required.issubset(view)
        assert view["schema_version"] == "1.0"
        assert view["case_id"] == case_id
        assert view["source_case_id"] == cases[case_id]["source_case_id"]
        assert view["decision"] == cases[case_id]["expected_decision"]
        assert view["activation_profile"] == cases[case_id]["expected_activation_profile"]


def test_expected_views_lock_the_safety_critical_outcomes() -> None:
    views = {
        case_id: _json(DEMO_ROOT / "expected_views" / f"{case_id}.view.json")
        for case_id in CASE_IDS
    }
    assert views["ERB-001"]["agent_roles"] == []
    assert views["ERB-001"]["answer_present"] is True

    assert views["ERB-002"]["clarifying_question"] == (
        "Do you mean Advisory Review Code or Account Routing Console?"
    )
    assert views["ERB-002"]["answer_present"] is False

    assert len(views["ERB-003"]["counterfactuals"]) == 3
    assert [item["decision"] for item in views["ERB-003"]["counterfactuals"]] == [
        "ABSTAIN",
        "ABSTAIN",
        "CLARIFY",
    ]

    route = views["ERB-004"]["route"]
    assert route["support_function"] == "BUSINESS_FRONT_SUPPORT"
    assert route["route_mode"] == "FUNCTIONAL_QUEUE"
    assert route["queue_id"] == "QUEUE-BFS-GLOBAL"
    assert views["ERB-004"]["case_capsule_required"] is True

    governance = views["ERB-005"]["governance"]
    assert governance["policy_ci"] == {"matched": 11, "expected": 11}
    assert governance["regression"] == {"matched": 45, "expected": 45}
    assert governance["counterfactual_containment"] == {"matched": 4, "expected": 4}
    assert governance["automatic_approval"] == 0
    assert governance["automatic_activation"] == 0
    assert governance["human_approval"] is True
    assert governance["release_activation"] is True
