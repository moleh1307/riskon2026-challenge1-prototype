"""Evaluator-source tests for ER-C slide metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from riskon.pitch.errors import PitchSourceError
from riskon.pitch.metrics_loader import (
    REQUIRED_PITCH_METRICS,
    load_metric_snapshot,
    metric_source_map,
    metric_values,
    required_metrics,
)
from riskon.pitch.models import MetricSnapshot


def test_metric_snapshot_preserves_all_required_sources(event_pitch_config: object) -> None:
    config = event_pitch_config  # type: ignore[assignment]
    snapshot = load_metric_snapshot(config.runtime.dashboard_metrics)  # type: ignore[attr-defined]
    selected = required_metrics(snapshot)
    assert [metric.id for metric in selected] == list(REQUIRED_PITCH_METRICS)
    assert all(metric.source for metric in selected)
    assert snapshot.network_enabled is False


def test_metric_values_and_sources_follow_requested_order(event_pitch_config: object) -> None:
    config = event_pitch_config  # type: ignore[assignment]
    snapshot = load_metric_snapshot(config.runtime.dashboard_metrics)  # type: ignore[attr-defined]
    ids = ["unsafe_routing", "m0_m4d_regression"]
    assert list(metric_values(snapshot, ids)) == ids
    assert metric_values(snapshot, ids)["unsafe_routing"] == "0"
    assert set(metric_source_map(snapshot, ids)) == set(ids)


def test_metric_helpers_report_missing_ids(event_pitch_config: object) -> None:
    config = event_pitch_config  # type: ignore[assignment]
    snapshot = load_metric_snapshot(config.runtime.dashboard_metrics)  # type: ignore[attr-defined]
    with pytest.raises(PitchSourceError, match="Dashboard metric source is missing"):
        required_metrics(snapshot.model_copy(update={"metrics": snapshot.metrics[:1]}))
    with pytest.raises(PitchSourceError, match="not available: not-present"):
        metric_values(snapshot, ["not-present"])
    with pytest.raises(PitchSourceError, match="not available: not-present"):
        metric_source_map(snapshot, ["not-present"])


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "must contain a metrics list"),
        ({"metrics": "wrong"}, "must contain a metrics list"),
        ({"metrics": [{"id": "m"}]}, "Invalid dashboard metric"),
    ],
)
def test_metric_loader_rejects_malformed_sources(
    tmp_path: Path, payload: object, message: str
) -> None:
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PitchSourceError, match=message):
        load_metric_snapshot(path)


def test_metric_loader_handles_non_mapping_security_and_missing_schema(tmp_path: Path) -> None:
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps({"metrics": [], "security": []}), encoding="utf-8")
    snapshot = load_metric_snapshot(path)
    assert snapshot.schema_version == ""
    assert snapshot.network_enabled is False


def test_metric_loader_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PitchSourceError, match="source not found"):
        load_metric_snapshot(tmp_path / "missing.json")


def test_metric_snapshot_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        MetricSnapshot.model_validate(
            {"schema_version": "1", "metrics": [], "network_enabled": False, "extra": True}
        )
