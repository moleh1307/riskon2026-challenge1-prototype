"""No-egress runtime checks for ER-B."""

from __future__ import annotations

from riskon.demo.models import DashboardView


def test_demo_security_and_network_metrics_are_disabled(
    event_demo_config: object,
    event_demo_dashboard: DashboardView,
) -> None:
    security = event_demo_config.security  # type: ignore[union-attr]
    assert security.network_enabled is False
    assert security.external_api_enabled is False
    assert security.telemetry_enabled is False
    assert security.local_server_enabled is False
    network = next(
        metric for metric in event_demo_dashboard.metrics if metric.id == "network_violations"
    )
    assert network.value == "0"
