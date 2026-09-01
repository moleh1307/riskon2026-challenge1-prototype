"""Evidence Scout responsibility tests."""

import asyncio

from m4b_helpers import m4b_config, worker_context_for

from riskon.orchestra.models import FindingStance
from riskon.orchestra.workers.evidence_scout import EvidenceScout
from riskon.pipeline import RiskonPipeline


def test_evidence_scout_recovers_explicit_control_support(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(
        EvidenceScout().run(worker_context_for(pipeline, "M4-030", "EVIDENCE_SCOUT"))
    )
    assert [(item.claim_id, item.stance) for item in result.findings] == [
        ("do_not_proceed", FindingStance.SUPPORT)
    ]
    assert result.material_objections == []


def test_evidence_scout_uses_safe_policy_paragraph_not_injection(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(
        EvidenceScout().run(worker_context_for(pipeline, "M4-038", "EVIDENCE_SCOUT"))
    )
    assert len(result.findings) == 1
    assert result.findings[0].claim_id == "prompt_safe_control_rule"
    assert "untrusted-instruction-text" not in result.findings[0].evidence_refs[0]


def test_evidence_scout_does_not_scan_table_cases(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(
        EvidenceScout().run(worker_context_for(pipeline, "M4-032", "PROCESS_TABLE_SCOUT"))
    )
    assert result.findings == []
