"""Fail-closed and no-worker tests for profiles deferred to M4B."""

import ast
import inspect
import json
from pathlib import Path

import pytest

import riskon.orchestra.runtime as runtime_module
from riskon.config import load_milestone4a_config
from riskon.models import PlannedVerifiedRun
from riskon.orchestra.errors import OrchestraWorkersNotImplementedError
from riskon.orchestra.models import OrchestraContext, RiskSignal
from riskon.orchestra.runtime import M4AOrchestrator
from riskon.pipeline import RiskonPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M4_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m4"


def planned(case_id: str) -> PlannedVerifiedRun:
    """Load a frozen M4 fixture."""

    raw = json.loads((M4_ROOT / "upstream_runs" / f"{case_id}.planned.json").read_text())
    return PlannedVerifiedRun.model_validate(raw["planned_verified_run"])


def pipeline(tmp_path: Path) -> RiskonPipeline:
    """Build an isolated M4A pipeline."""

    config = load_milestone4a_config(PROJECT_ROOT / "config" / "milestone4a.toml")
    orchestra = config.orchestra.model_copy(update={"generated_root": tmp_path / "m4a"})
    return RiskonPipeline.from_milestone4a_config(
        config.model_copy(update={"orchestra": orchestra})
    )


@pytest.mark.parametrize(
    ("case_id", "profile", "signal", "roles"),
    [
        (
            "M4-030",
            "DUAL_CHECK",
            "CRITICAL_CONTROL_RISK",
            ["EVIDENCE_SCOUT", "PROCESS_TABLE_SCOUT", "SKEPTIC"],
        ),
        (
            "M4-031",
            "FULL_ORCHESTRA",
            "SCOPE_SENSITIVE",
            [
                "EVIDENCE_SCOUT",
                "SCOPE_SENTINEL",
                "PROCESS_TABLE_SCOUT",
                "SKEPTIC",
                "COUNTERFACTUAL_SENTINEL",
            ],
        ),
    ],
)
def test_deferred_profiles_raise_the_typed_fail_closed_error(
    tmp_path: Path,
    case_id: str,
    profile: str,
    signal: str,
    roles: list[str],
) -> None:
    target = pipeline(tmp_path)
    with pytest.raises(OrchestraWorkersNotImplementedError) as caught:
        target.orchestrate_planned(
            planned(case_id),
            OrchestraContext(
                risk_signals=(RiskSignal(signal),),
                routing_context=None,
                routing_profile="default",
            ),
            profile,
        )
    error = caught.value
    assert error.activation_profile == profile
    assert error.required_agent_roles == roles
    assert (
        error.message
        == f"Orchestration profile {profile} requires M4B workers and is not available in M4A."
    )
    assert str(error) == error.message


def test_unknown_profile_and_network_enabled_runtime_fail_closed(tmp_path: Path) -> None:
    target = pipeline(tmp_path)
    with pytest.raises(ValueError, match="Unknown activation profile"):
        target.orchestrate_planned(
            planned("M4-029"),
            OrchestraContext(risk_signals=(), routing_context=None, routing_profile="default"),
            "NOT_A_PROFILE",
        )

    config = load_milestone4a_config(PROJECT_ROOT / "config" / "milestone4a.toml")
    policy = target._m4a_orchestrator.policy if target._m4a_orchestrator is not None else None
    assert policy is not None
    network_runtime = M4AOrchestrator(
        policy,
        lambda *_args: (_ for _ in ()).throw(AssertionError("route must not run")),
        network_enabled=True,
    )
    with pytest.raises(ValueError, match="network_enabled"):
        network_runtime.orchestrate_planned(
            planned("M4-029"),
            OrchestraContext(risk_signals=(), routing_context=None, routing_profile="default"),
            "FAST_PATH",
        )
    assert config.security.network_enabled is False


def test_m4a_runtime_has_no_worker_or_asyncio_execution_surface() -> None:
    source = inspect.getsource(runtime_module)
    tree = ast.parse(source)
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert "asyncio" not in imports
    assert "create_task" not in source
    assert "agent_catalog" not in source
    assert "from riskon.orchestra.workers" not in source
    assert "workers/" not in source
