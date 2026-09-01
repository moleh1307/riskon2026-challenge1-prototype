"""M5B explicit scope containment and query matching."""

import pytest
from m5b_helpers import valid_patch, valid_resolution, valid_scope

from riskon.governance.scope_checks import context_matches_scope, scope_containment, scope_contains


def test_equal_scope_is_contained() -> None:
    resolution = valid_resolution()
    assert scope_containment(resolution, valid_patch(resolution)) == (
        True,
        "patch scope is contained by resolution scope",
    )


@pytest.mark.parametrize(
    ("dimension", "value"),
    [
        ("regions", ["REGION_ALPHA"]),
        ("service_models", ["SERVICE_PLUS"]),
        ("systems", ["SYSTEM_OTHER"]),
    ],
)
def test_scope_dimension_outside_resolution_fails(dimension: str, value: list[str]) -> None:
    container = valid_scope(regions=["REGION_BETA"], service_models=["SERVICE_BASIC"])
    candidate = valid_scope(**{dimension: value})
    ok, details = scope_contains(container, candidate)
    assert ok is False
    assert dimension in details


def test_empty_candidate_dimension_is_not_a_wildcard() -> None:
    container = valid_scope(regions=["REGION_BETA"])
    candidate = valid_scope(regions=[], service_models=["SERVICE_BASIC"])
    assert scope_contains(container, candidate)[0] is False


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ({"region": "REGION_BETA", "service_model": "SERVICE_BASIC"}, True),
        ({"region": "region_beta", "service_model": "service_basic"}, True),
        ({"region": "REGION_ALPHA", "service_model": "SERVICE_BASIC"}, False),
        ({"service_model": "SERVICE_BASIC"}, True),
        ({"region": "REGION_BETA", "workflow_stage": "PRE_DECISION"}, True),
    ],
)
def test_context_matches_only_declared_nonempty_dimensions(
    context: dict[str, str], expected: bool
) -> None:
    scope = valid_scope(regions=["REGION_BETA"], service_models=["SERVICE_BASIC"])
    assert context_matches_scope(context, scope) is expected


def test_context_dimension_mapping_covers_all_scope_fields() -> None:
    scope = valid_scope(
        jurisdictions=["CH"],
        solicitation_types=["SOLICITED"],
        workflow_stages=["PRE_DECISION"],
        client_classifications=["PROFESSIONAL"],
        systems=["SYSTEM_X"],
    )
    context = {
        "jurisdiction": "CH",
        "solicitation_type": "SOLICITED",
        "workflow_stage": "PRE_DECISION",
        "client_classification": "PROFESSIONAL",
        "system": "SYSTEM_X",
    }
    assert context_matches_scope(context, scope) is True
