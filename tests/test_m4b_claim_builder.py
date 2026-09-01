"""Deterministic candidate claim-builder tests."""

from m4b_helpers import M4_ROOT

from riskon.orchestra.claim_builder import DeterministicClaimBuilder
from riskon.orchestra.models import AgentFinding, FindingStance
from riskon.orchestra.source_safety import (
    SourceSafetyContext,
    SourceSafetyPolicy,
    build_local_corpus,
)


def _builder() -> DeterministicClaimBuilder:
    corpus = build_local_corpus(M4_ROOT / "manifest.xlsx", M4_ROOT / "knowledge")
    policy = SourceSafetyPolicy.from_file(M4_ROOT / "source_safety_policy.json")
    return DeterministicClaimBuilder(
        corpus,
        SourceSafetyContext(policy=policy, report=policy.inspect(corpus)),
    )


def _finding(claim_id: str, ref: str, stance: FindingStance, ordinal: str) -> AgentFinding:
    return AgentFinding(
        finding_id=f"finding:{ordinal}",
        task_id=f"task:{ordinal}:evidence_scout",
        agent_id="AGENT-M4-EVIDENCE-001",
        agent_role="EVIDENCE_SCOUT",
        claim_id=claim_id,
        stance=stance,
        evidence_refs=[ref],
        source_scope="LOCAL",
        criticality="NORMAL",
    )


def test_builder_uses_support_only_and_merges_duplicate_claims() -> None:
    ref = "local://synthetic-m4/active_control.html#section-critical-controls"
    result = _builder().build(
        [
            _finding("do_not_proceed", ref, FindingStance.SUPPORT, "a"),
            _finding("do_not_proceed", ref, FindingStance.SUPPORT, "b"),
            _finding("filtered_alert_set", ref, FindingStance.CHALLENGE, "c"),
        ]
    )
    assert [claim.claim_id for claim in result.claims] == ["do_not_proceed"]
    assert result.conflicting_claim_ids == ()


def test_builder_refuses_contradictory_support_texts() -> None:
    first = "local://synthetic-m4/conflict_policy_a.html#section-synthetic-rule-a"
    second = "local://synthetic-m4/conflict_policy_b.html#section-synthetic-rule-b"
    result = _builder().build(
        [
            _finding("control_atlas_applicability", first, FindingStance.SUPPORT, "a"),
            _finding("control_atlas_applicability", second, FindingStance.SUPPORT, "b"),
        ]
    )
    assert result.claims == ()
    assert result.conflicting_claim_ids == ("control_atlas_applicability",)


def test_builder_filters_unsafe_source_and_unknown_reference() -> None:
    safe_ref = (
        "local://synthetic-m4/prompt_injection_source.html#section-valid-synthetic-policy-statement"
    )
    unsafe_ref = "local://synthetic-m4/prompt_injection_source.html#section-untrusted-instruction-text:sentence-1"
    result = _builder().build(
        [
            _finding("prompt_safe_control_rule", safe_ref, FindingStance.SUPPORT, "safe"),
            _finding("source_instruction", unsafe_ref, FindingStance.SUPPORT, "unsafe"),
        ]
    )
    assert [claim.claim_id for claim in result.claims] == ["prompt_safe_control_rule"]
    assert result.forbidden_evidence_refs == (unsafe_ref,)
