"""M4B signal-to-role selection tests."""

import json
from pathlib import Path

import pytest
from m4b_helpers import M4_ROOT, M4B_CONFIG_PATH, m4b_config

from riskon.orchestra.policy import WorkerSelectionPolicy
from riskon.orchestra.tasks import AgentCatalog
from riskon.orchestra.worker_selection import WorkerSelector


def selector() -> WorkerSelector:
    """Build a selector from the frozen policy and catalog."""

    policy = WorkerSelectionPolicy.from_file(
        M4_ROOT.parent / "m4b" / "worker_selection_policy.json"
    )
    catalog = AgentCatalog.from_file(M4_ROOT / "agent_catalog.json")
    return WorkerSelector(policy, catalog)


def test_signal_union_is_in_canonical_order() -> None:
    selected = selector().select_roles(
        ["TABLE_DEPENDENT", "CRITICAL_CONTROL_RISK", "PROMPT_INJECTION_SIGNAL"]
    )
    assert selected == ["EVIDENCE_SCOUT", "PROCESS_TABLE_SCOUT", "SKEPTIC"]


def test_counterfactual_mapping_is_declared_but_not_implemented() -> None:
    policy = WorkerSelectionPolicy.from_file(
        M4_ROOT.parent / "m4b" / "worker_selection_policy.json"
    )
    mapping = policy.mapping("COUNTERFACTUAL_REQUIRED")
    assert mapping.required_agent_roles == ("COUNTERFACTUAL_SENTINEL",)
    assert policy.status_for("COUNTERFACTUAL_REQUIRED") == "NOT_IMPLEMENTED"


def test_policy_loader_rejects_schema_drift(tmp_path: Path) -> None:
    source = M4_ROOT.parent / "m4b" / "worker_selection_policy.json"
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["unexpected"] = True
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="fields do not match"):
        WorkerSelectionPolicy.from_file(path)


def test_m4b_config_keeps_worker_backend_and_bounds(tmp_path: Path) -> None:
    config = m4b_config(tmp_path)
    profile = config.orchestra.m4b
    assert profile.worker_backend == "DETERMINISTIC_WORKER_V1"
    assert (profile.maximum_worker_depth, profile.maximum_parallel_discovery_workers) == (1, 3)
    assert profile.maximum_challenge_rounds == 1
    assert M4B_CONFIG_PATH.is_file()
