"""Process/Table Scout responsibility tests."""

import asyncio

from m4b_helpers import m4b_config, worker_context_for

from riskon.orchestra.models import FindingStance
from riskon.orchestra.workers.process_table_scout import ProcessTableScout
from riskon.pipeline import RiskonPipeline


def test_process_table_scout_recovers_all_eligible_rows_with_header_context(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(
        ProcessTableScout().run(worker_context_for(pipeline, "M4-032", "PROCESS_TABLE_SCOUT"))
    )
    assert [item.claim_id for item in result.findings] == [
        "atlas_alert_active",
        "beacon_alert_active",
        "cedar_alert_active",
    ]
    assert all(item.stance is FindingStance.SUPPORT for item in result.findings)
    assert all(":table-1:row-" in item.evidence_refs[0] for item in result.findings)


def test_process_table_scout_does_not_include_overnight_or_inactive_rows(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(
        ProcessTableScout().run(worker_context_for(pipeline, "M4-032", "PROCESS_TABLE_SCOUT"))
    )
    refs = " ".join(item.evidence_refs[0] for item in result.findings)
    assert "row-4" not in refs
    assert "row-5" not in refs


def test_process_table_scout_returns_empty_for_non_table_query(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(ProcessTableScout().run(worker_context_for(pipeline, "M4-030", "SKEPTIC")))
    assert result.findings == []
