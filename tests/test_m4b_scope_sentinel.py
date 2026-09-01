"""Scope Sentinel responsibility tests."""

import asyncio

from m4b_helpers import m4b_config, worker_context_for

from riskon.orchestra.models import FindingStance
from riskon.orchestra.workers.scope_sentinel import ScopeSentinel
from riskon.pipeline import RiskonPipeline


def test_scope_sentinel_excludes_region_alpha_distractor(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(
        ScopeSentinel().run(worker_context_for(pipeline, "M4-031", "SCOPE_SENTINEL"))
    )
    assert result.findings[0].stance is FindingStance.CHALLENGE
    assert result.findings[0].evidence_refs == [
        "local://synthetic-m4/regional_scope_alpha.html#section-applicability"
    ]
    assert result.material_objections[0].reason_code == "SCOPE_CONFLICT"
    assert result.material_objections[0].status == "RESOLVED"


def test_scope_sentinel_surfaces_the_second_conflicting_policy(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(
        ScopeSentinel().run(worker_context_for(pipeline, "M4-037", "SCOPE_SENTINEL"))
    )
    assert [(item.claim_id, item.stance) for item in result.findings] == [
        ("control_atlas_applicability", FindingStance.SUPPORT)
    ]
    assert result.material_objections == []


def test_scope_sentinel_is_quiet_for_an_unrelated_signal(tmp_path) -> None:
    pipeline = RiskonPipeline.from_milestone4b_config(m4b_config(tmp_path))
    result = asyncio.run(ScopeSentinel().run(worker_context_for(pipeline, "M4-030", "SKEPTIC")))
    assert result.findings == []
    assert result.material_objections == []
