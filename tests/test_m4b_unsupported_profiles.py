"""M4B fail-closed unsupported profile tests."""

import pytest
from m4b_helpers import case, context_for, m4b_config, planned

from riskon.orchestra.errors import OrchestraWorkersNotImplementedError
from riskon.pipeline import RiskonPipeline


def test_counterfactual_cases_fail_with_the_m4c_boundary_message(tmp_path) -> None:
    config = m4b_config(tmp_path)
    pipeline = RiskonPipeline.from_milestone4b_config(config)
    for case_id in ("M4-035", "M4-036"):
        case_value = case(case_id)
        fixture = planned(case_id)
        with pytest.raises(OrchestraWorkersNotImplementedError) as error:
            pipeline.orchestrate_planned(
                fixture.planned_verified_run,
                context_for(case_value, fixture),
                case_value.activation_profile.value,
            )
        assert str(error.value) == (
            "Orchestration requires COUNTERFACTUAL_SENTINEL, which is reserved for M4C."
        )
        assert error.value.activation_profile == "FULL_ORCHESTRA"
        assert "COUNTERFACTUAL_SENTINEL" in error.value.required_agent_roles


def test_m4b_requires_declared_signal_for_worker_profile(tmp_path) -> None:
    config = m4b_config(tmp_path)
    pipeline = RiskonPipeline.from_milestone4b_config(config)
    fixture = planned("M4-030")
    context = context_for(case("M4-030"), fixture).model_copy(update={"risk_signals": ()})
    with pytest.raises(ValueError, match="at least one declared risk signal"):
        pipeline.orchestrate_planned(fixture.planned_verified_run, context, "DUAL_CHECK")
