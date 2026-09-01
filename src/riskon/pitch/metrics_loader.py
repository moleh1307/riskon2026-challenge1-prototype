"""Load evaluator-backed values for the pitch without duplicating metrics."""

from __future__ import annotations

import json
from pathlib import Path

from riskon.pitch.errors import PitchSourceError
from riskon.pitch.models import MetricSnapshot, MetricSource

REQUIRED_PITCH_METRICS = (
    "m0_m4d_regression",
    "m5b_governed_evolution",
    "policy_ci_checks",
    "counterfactual_transitions",
    "unsafe_routing",
    "automatic_approvals",
    "network_violations",
)


def load_metric_snapshot(path: Path) -> MetricSnapshot:
    """Read the current ER-B dashboard output and preserve its provenance."""

    if not path.is_file():
        raise PitchSourceError(f"Dashboard metric source not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PitchSourceError(f"Unable to read dashboard metrics: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("metrics"), list):
        raise PitchSourceError("Dashboard metric source must contain a metrics list")
    metrics: list[MetricSource] = []
    for item in raw["metrics"]:
        try:
            metrics.append(MetricSource.model_validate(item))
        except ValueError as exc:
            raise PitchSourceError(f"Invalid dashboard metric: {exc}") from exc
    security = raw.get("security", {})
    network_enabled = (
        bool(security.get("network_enabled", False)) if isinstance(security, dict) else False
    )
    return MetricSnapshot(
        schema_version=str(raw.get("schema_version", "")),
        metrics=metrics,
        network_enabled=network_enabled,
    )


def required_metrics(snapshot: MetricSnapshot) -> list[MetricSource]:
    """Return the seven metrics used by the pitch in contract order."""

    by_id = {metric.id: metric for metric in snapshot.metrics}
    missing = [metric_id for metric_id in REQUIRED_PITCH_METRICS if metric_id not in by_id]
    if missing:
        raise PitchSourceError(f"Dashboard metric source is missing: {', '.join(missing)}")
    selected = [by_id[metric_id] for metric_id in REQUIRED_PITCH_METRICS]
    if any(not metric.source.strip() for metric in selected):
        raise PitchSourceError("Every pitch metric must preserve a non-empty evaluator source")
    return selected


def metric_values(snapshot: MetricSnapshot, metric_ids: list[str]) -> dict[str, str]:
    """Resolve display values by ID while keeping the source data authoritative."""

    by_id = {metric.id: metric for metric in snapshot.metrics}
    missing = [metric_id for metric_id in metric_ids if metric_id not in by_id]
    if missing:
        raise PitchSourceError(f"Requested metric is not available: {', '.join(missing)}")
    return {metric_id: by_id[metric_id].value for metric_id in metric_ids}


def metric_source_map(snapshot: MetricSnapshot, metric_ids: list[str]) -> dict[str, str]:
    """Return evaluator provenance for the requested metric IDs."""

    by_id = {metric.id: metric for metric in snapshot.metrics}
    missing = [metric_id for metric_id in metric_ids if metric_id not in by_id]
    if missing:
        raise PitchSourceError(f"Requested metric source is not available: {', '.join(missing)}")
    return {metric_id: by_id[metric_id].source for metric_id in metric_ids}
