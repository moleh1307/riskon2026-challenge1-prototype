"""Retrieval behavior for the active M5B knowledge overlay."""

import pytest
from m5b_helpers import config

from riskon.governance.models import KnowledgeOverlaySnapshot
from riskon.m5b_evaluation import M5BEvaluator
from riskon.models import Decision, QueryInput
from riskon.pipeline import M5BRiskonPipeline, _overlay_section


@pytest.fixture(scope="module")
def pipeline_and_overlay():
    document = M5BEvaluator(config()).run()
    pipeline = M5BRiskonPipeline.from_milestone5b_config(config())
    overlay = KnowledgeOverlaySnapshot.model_validate(document.overlay_snapshot)
    return pipeline, overlay


def test_active_overlay_is_admitted_without_special_score_boost(pipeline_and_overlay) -> None:
    pipeline, overlay = pipeline_and_overlay
    query = QueryInput(
        query="Does Control Meridian apply to Service Basic in Region Beta?",
        context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
    )
    planned = pipeline.run_planned_with_overlay(query, overlay)
    result = planned.verified_run.result
    assert result.decision is Decision.ANSWER
    assert any(
        ref.startswith("local://knowledge-overlay/KB-SYN-V2/M5A-046-PATCH#claim-")
        for ref in planned.verified_run.verification.evidence_refs
    )
    assert "Control Meridian" in (result.answer or "")


@pytest.mark.parametrize(
    ("context", "decision", "reason"),
    [
        ({"region": "REGION_ALPHA", "service_model": "SERVICE_BASIC"}, "ABSTAIN", "SCOPE_MISMATCH"),
        ({"region": "REGION_BETA", "service_model": "SERVICE_PLUS"}, "ABSTAIN", "SCOPE_MISMATCH"),
        ({"service_model": "SERVICE_BASIC"}, "CLARIFY", "MISSING_REQUIRED_CONTEXT"),
    ],
)
def test_active_overlay_preserves_scope_and_clarification_gates(
    pipeline_and_overlay, context, decision: str, reason: str
) -> None:
    pipeline, overlay = pipeline_and_overlay
    planned = pipeline.run_planned_with_overlay(
        QueryInput(query="Does Control Meridian apply to the service?", context=context),
        overlay,
    )
    result = planned.verified_run.result
    assert result.decision.value == decision
    assert reason in [item.value for item in result.reason_codes]


def test_overlay_section_preserves_scope_claim_and_local_provenance(pipeline_and_overlay) -> None:
    _, overlay = pipeline_and_overlay
    section = _overlay_section(overlay.evidence_units[0])
    assert section.source_ref == overlay.evidence_units[0].overlay_ref
    assert section.claims == {overlay.evidence_units[0].claim_id: overlay.evidence_units[0].text}
    assert section.scope == {
        "region": "REGION_BETA",
        "service_model": "SERVICE_BASIC",
    }
    assert section.filename.startswith("overlay/")


def test_excluded_overlay_is_not_retrievable_and_missing_context_still_clarifies(
    pipeline_and_overlay,
) -> None:
    pipeline, overlay = pipeline_and_overlay
    excluded = overlay.model_copy(
        update={
            "active_patch_ids": [],
            "excluded_patch_ids": ["M5A-047-PATCH"],
            "evidence_units": [],
        }
    )
    exact = pipeline.run_planned_with_overlay(
        QueryInput(
            query="Does Control Meridian apply to Service Basic in Region Beta?",
            context={"region": "REGION_BETA", "service_model": "SERVICE_BASIC"},
        ),
        excluded,
    )
    missing = pipeline.run_planned_with_overlay(
        QueryInput(
            query="Does Control Meridian apply to the basic service?",
            context={"service_model": "SERVICE_BASIC"},
        ),
        excluded,
    )
    assert exact.verified_run.result.decision is Decision.ABSTAIN
    assert missing.verified_run.result.decision is Decision.CLARIFY
