"""Frozen M5B evaluation matrix and generated governance artifacts."""

import pytest
from m5b_helpers import config

from riskon.m5b_evaluation import REFERENCE_TIME, M5BEvaluator, _excluded_snapshot
from riskon.models import Decision


@pytest.fixture(scope="module")
def document():
    return M5BEvaluator(config()).run()


def test_m5b_evaluator_matches_all_five_cases(document) -> None:
    assert [item.case_id for item in document.case_results] == [
        "M5A-046",
        "M5A-047",
        "M5A-048",
        "M5A-049",
        "M5A-050",
    ]
    assert all(item.matched for item in document.case_results)
    assert document.metrics.m5b_case_match_rate == 1.0
    assert document.metrics.governed_evolution_count == 1
    assert document.metrics.awaiting_approval_count == 1
    assert document.metrics.rejected_unsafe_patch_count == 2
    assert document.metrics.expired_patch_exclusion_count == 1


def test_m5b_evaluator_emits_exact_governance_counters(document) -> None:
    metrics = document.metrics
    assert metrics.policy_ci_check_count == metrics.expected_policy_ci_check_count == 55
    assert metrics.policy_ci_status_match_count == 55
    assert (metrics.regression_expected, metrics.regression_matched) == (45, 45)
    assert (metrics.counterfactual_expected, metrics.counterfactual_matched) == (4, 4)
    assert metrics.exact_scope_answer_count == 1
    assert metrics.alternate_region_abstention_count == 1
    assert metrics.alternate_service_abstention_count == 1
    assert metrics.missing_context_clarification_count == 1
    assert metrics.automatic_approval_count == 0
    assert metrics.automatic_activation_count == 0
    assert metrics.self_approval_count == 0
    assert metrics.official_corpus_mutation_count == 0
    assert metrics.expired_evidence_retrieval_count == 0
    assert metrics.network_violation_count == 0


def test_m5b_evaluator_contains_required_architecture_statement(document) -> None:
    assert document.architecture_statement == (
        "M5B does not train or fine-tune a model from expert conversations.\n\n"
        "It converts structured expert resolutions into proposed knowledge\n"
        "patches and activates them only after mandatory Policy CI checks,\n"
        "separate human approval, and explicit release activation."
    )
    assert document.security == {
        "network_enabled": False,
        "external_api_enabled": False,
        "telemetry_enabled": False,
    }


def test_m5b_case_level_outcomes_have_expected_details(document) -> None:
    cases = {item.case_id: item for item in document.case_results}
    assert cases["M5A-046"].actual_patch_status == "ACTIVE"
    assert cases["M5A-046"].actual_active_release == "KB-SYN-V2"
    assert cases["M5A-046"].overlay_claim_ids == ["meridian_beta_basic_applies"]
    assert cases["M5A-046"].orchestration_decision == Decision.ANSWER.value
    assert cases["M5A-047"].actual_patch_status == "AWAITING_APPROVAL"
    assert cases["M5A-048"].actual_patch_status == "REJECTED"
    assert cases["M5A-049"].actual_patch_status == "REJECTED"
    assert cases["M5A-050"].actual_patch_status == "EXPIRED"


def test_m5b_generated_outputs_have_the_frozen_names(document) -> None:
    del document
    root = config().governance.generated_root
    expected = {
        "evaluation.json",
        "evaluation.md",
        "policy_ci_reports.jsonl",
        "governance_events.jsonl",
        "knowledge_releases.jsonl",
        "overlay_snapshot.json",
        "audit.jsonl",
    }
    # The evaluator writes the JSONL/overlay/audit artifacts; report writers add the two reports.
    from riskon.reporting import write_m5b_reports

    write_m5b_reports(M5BEvaluator(config()).run(), root)
    assert {path.name for path in root.iterdir() if path.name in expected} == expected


@pytest.mark.parametrize(
    ("patch_id", "expected_release", "expected_excluded"),
    [
        ("patch-1", "NO-ACTIVE-patch-1", ["patch-1"]),
        ("M5A-050-PATCH", "NO-ACTIVE-M5A-050-PATCH", ["M5A-050-PATCH"]),
    ],
)
def test_excluded_snapshot_is_explicitly_nonretrievable(
    patch_id: str, expected_release: str, expected_excluded: list[str]
) -> None:
    snapshot = _excluded_snapshot(patch_id)
    assert snapshot.release_id == expected_release
    assert snapshot.reference_time_utc == REFERENCE_TIME
    assert snapshot.active_patch_ids == []
    assert snapshot.excluded_patch_ids == expected_excluded
    assert snapshot.evidence_units == []


@pytest.mark.parametrize(
    ("patch_id", "has_approval", "expected"),
    [
        ("M5A-046-PATCH", True, "ACTIVATION"),
        ("M5A-047-PATCH", None, "PRE_APPROVAL"),
    ],
)
def test_phase_selection_matches_approval_and_effective_state(
    patch_id: str, has_approval: bool | None, expected: str, tmp_path
) -> None:
    evaluator = M5BEvaluator(config())
    from m5b_helpers import service as make_service

    loaded = make_service(tmp_path).load_case_inputs(patch_id.removesuffix("-PATCH"))
    approval = loaded[3] if has_approval else None
    assert evaluator._phase_for(loaded[2], approval).value == expected
