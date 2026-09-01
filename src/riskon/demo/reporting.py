"""Build and write ER-B demo artifacts with deterministic local reporting."""

from __future__ import annotations

import json
from pathlib import Path

from riskon.config import load_event_demo_config
from riskon.demo.catalog import DemoCatalog
from riskon.demo.dashboard import DashboardBuilder
from riskon.demo.html_renderer import render_dashboard_html, render_index_html, render_story_html
from riskon.demo.models import AuditRecord, DemoBundle, StoryView
from riskon.demo.runner import DemoRunner


class BuildResult:
    """Paths and payloads produced by a full ER-B build."""

    def __init__(self, output_root: Path, stories: tuple[StoryView, ...]) -> None:
        self.output_root = output_root
        self.stories = stories
        self.index_path = output_root / "index.html"
        self.dashboard_path = output_root / "dashboard.html"
        self.bundle_path = output_root / "demo_bundle.json"
        self.metrics_path = output_root / "dashboard_metrics.json"
        self.audit_path = output_root / "audit.jsonl"


def build_demo(config_path: Path) -> BuildResult:
    """Run the local story/evaluator bundle and write all canonical ER-B outputs."""

    config = load_event_demo_config(config_path)
    catalog = DemoCatalog.from_config(config)
    runtime = DemoRunner(config, catalog).run_all()
    dashboard = DashboardBuilder(catalog).build(
        m4d_runs=runtime.m4d_runs,
        m5b_document=runtime.m5b_document,
    )
    bundle = DemoBundle(
        schema_version="1.0",
        stories=list(runtime.stories),
        dashboard=dashboard,
        security={
            "network_enabled": config.security.network_enabled,
            "external_api_enabled": config.security.external_api_enabled,
            "telemetry_enabled": config.security.telemetry_enabled,
            "local_server_enabled": config.security.local_server_enabled,
        },
    )
    output_root = config.runtime.generated_root
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / "demo_bundle.json", bundle.model_dump(mode="json"))
    _write_json(output_root / "dashboard_metrics.json", dashboard.model_dump(mode="json"))
    (output_root / "index.html").write_text(
        render_index_html(runtime.stories, dashboard, catalog.presentation_copy),
        encoding="utf-8",
    )
    (output_root / "dashboard.html").write_text(
        render_dashboard_html(dashboard, catalog.presentation_copy),
        encoding="utf-8",
    )
    audit = AuditRecord(
        artifact="event_demo",
        status="PASS",
        story_count=len(runtime.stories),
        dashboard_metric_count=len(dashboard.metrics),
        external_asset_count=0,
        network_enabled=config.security.network_enabled,
    )
    (output_root / "audit.jsonl").write_text(
        json.dumps(audit.model_dump(mode="json"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return BuildResult(output_root, runtime.stories)


def build_demo_case(config_path: Path, case_id: str, output: Path) -> StoryView:
    """Run one frozen story and write its standalone HTML file."""

    config = load_event_demo_config(config_path)
    catalog = DemoCatalog.from_config(config)
    story = DemoRunner(config, catalog).run_case(case_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_story_html(story, catalog.presentation_copy), encoding="utf-8")
    return story


def _write_json(path: Path, value: object) -> None:
    """Write deterministic JSON with no generated absolute paths."""

    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
