"""Skeptic challenge and safety tests."""

import asyncio

from m4b_helpers import m4b_config, worker_context_for

from riskon.orchestra.models import AgentFinding, FindingStance
from riskon.orchestra.workers.skeptic import Skeptic
from riskon.pipeline import RiskonPipeline


def test_skeptic_retains_resolved_critical_control_objection(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(Skeptic().run(worker_context_for(pipeline, "M4-030", "SKEPTIC")))
    assert result.findings[0].claim_id == "client_acceptance_does_not_override"
    assert result.material_objections[0].reason_code == "CRITICAL_CONTROL_OMITTED"
    assert result.material_objections[0].status == "RESOLVED"


def test_skeptic_marks_scope_support_neutral_after_discovery(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    context = worker_context_for(pipeline, "M4-031", "SKEPTIC")
    prior_finding = AgentFinding(
        finding_id="finding:discovery:001",
        task_id="task:discovery:evidence_scout",
        agent_id="AGENT-M4-EVIDENCE-001",
        agent_role="EVIDENCE_SCOUT",
        claim_id="region_beta_scope_rule",
        stance=FindingStance.SUPPORT,
        evidence_refs=["local://synthetic-m4/regional_scope_beta.html#section-applicability"],
        source_scope="REGION_BETA",
        criticality="CRITICAL",
    )
    result = asyncio.run(
        Skeptic().run(context.model_copy(update={"prior_findings": [prior_finding]}))
    )
    assert [(item.claim_id, item.stance) for item in result.findings] == [
        ("region_beta_scope_rule", FindingStance.NEUTRAL)
    ]


def test_skeptic_challenges_overnight_table_row(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(Skeptic().run(worker_context_for(pipeline, "M4-032", "SKEPTIC")))
    assert result.findings[0].claim_id == "filtered_alert_set"
    assert result.findings[0].stance is FindingStance.CHALLENGE
    assert result.findings[0].evidence_refs[0].endswith("row-4")


def test_skeptic_opens_objection_for_two_supporting_sources(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    context = worker_context_for(pipeline, "M4-037", "SKEPTIC")
    supports = [
        AgentFinding(
            finding_id="finding:prior-a",
            task_id="task:plan-a:evidence_scout",
            agent_id="AGENT-M4-EVIDENCE-001",
            agent_role="EVIDENCE_SCOUT",
            claim_id="control_atlas_applicability",
            stance=FindingStance.SUPPORT,
            evidence_refs=["local://synthetic-m4/conflict_policy_a.html#section-synthetic-rule-a"],
            source_scope="REGION_BETA/SERVICE_BASIC",
            criticality="CRITICAL",
        ),
        AgentFinding(
            finding_id="finding:prior-b",
            task_id="task:plan-b:scope_sentinel",
            agent_id="AGENT-M4-SCOPE-001",
            agent_role="SCOPE_SENTINEL",
            claim_id="control_atlas_applicability",
            stance=FindingStance.SUPPORT,
            evidence_refs=["local://synthetic-m4/conflict_policy_b.html#section-synthetic-rule-b"],
            source_scope="REGION_BETA/SERVICE_BASIC",
            criticality="CRITICAL",
        ),
    ]
    result = asyncio.run(Skeptic().run(context.model_copy(update={"prior_findings": supports})))
    assert result.material_objections[0].reason_code == "CONTRADICTORY_EVIDENCE"
    assert result.material_objections[0].status == "OPEN"


def test_skeptic_records_injection_diagnostic_without_following_it(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(Skeptic().run(worker_context_for(pipeline, "M4-038", "SKEPTIC")))
    assert [item.code for item in result.diagnostics] == ["SOURCE_INSTRUCTION_IGNORED"]
    assert result.findings[0].claim_id == "source_instruction"
    assert "section-untrusted-instruction-text" in result.findings[0].evidence_refs[0]
