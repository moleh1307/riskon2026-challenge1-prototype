"""M5B immutability and official-corpus separation checks."""

import subprocess

import pytest
from m5b_helpers import REFERENCE_TIME, config, service, valid_patch

from riskon.governance.errors import OfficialCorpusMutationError
from riskon.governance.models import GovernanceEvent, GovernanceEventType, PatchStatus
from riskon.governance.service import GovernedKnowledgeService


def test_frozen_m5a_contract_files_have_no_worktree_changes() -> None:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "m5a-governed-evolution-contract..HEAD",
            "--",
            "data/synthetic/m5a",
            "docs/milestone5a-contract.md",
            "tests/test_m5a_*.py",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""


def test_governance_models_are_frozen() -> None:
    patch = valid_patch()
    with pytest.raises(ValueError):
        patch.status = PatchStatus.ACTIVE
    event = GovernanceEvent(
        event_id="event",
        event_type=GovernanceEventType.PATCH_PROPOSED,
        timestamp_utc=REFERENCE_TIME,
    )
    with pytest.raises(ValueError):
        event.event_id = "changed"


def test_service_rejects_official_corpus_mutation_before_event_store_use(tmp_path) -> None:
    base = config()
    unsafe_governance = base.governance.model_copy(
        update={"official_corpus_mutation_enabled": True}
    )
    unsafe = base.model_copy(update={"governance": unsafe_governance})
    with pytest.raises(OfficialCorpusMutationError):
        GovernedKnowledgeService(unsafe)


def test_overlay_claims_keep_original_evidence_refs_and_do_not_make_resolution_evidence(
    tmp_path,
) -> None:
    instance = service(tmp_path)
    _, resolution, patch, _ = instance.load_case_inputs("M5A-046")
    assert patch.claims[0].evidence_refs == resolution.claims[0].evidence_refs
    assert instance.event_store.events == ()
