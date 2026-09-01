"""ER-B catalog-loading tests."""

from __future__ import annotations

from riskon.demo.catalog import DemoCatalog


def test_catalog_has_five_ordered_stories(event_demo_catalog: DemoCatalog) -> None:
    assert [case.id for case in event_demo_catalog.cases] == [
        "ERB-001",
        "ERB-002",
        "ERB-003",
        "ERB-004",
        "ERB-005",
    ]


def test_catalog_keeps_expected_views_and_context_presets_local(
    event_demo_catalog: DemoCatalog,
) -> None:
    assert set(event_demo_catalog.expected_views) == {
        "ERB-001",
        "ERB-002",
        "ERB-003",
        "ERB-004",
        "ERB-005",
    }
    assert event_demo_catalog.preset("REGION_BETA_SERVICE_BASIC").context == {
        "region": "REGION_BETA",
        "service_model": "SERVICE_BASIC",
    }
    assert all(
        not str(value).startswith(("http://", "https://", "/"))
        for value in event_demo_catalog.dashboard_contract["evaluation_configs"]
    )
