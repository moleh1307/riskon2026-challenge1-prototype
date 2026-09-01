"""Run one synthetic query through the existing M5B orchestrated API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from riskon.config import load_event_demo_config, load_milestone5b_config
from riskon.demo.catalog import DemoCatalog
from riskon.demo.html_renderer import render_story_html
from riskon.demo.models import StoryView
from riskon.demo.view_models import story_view_from_run
from riskon.models import QueryInput
from riskon.pipeline import M5BRiskonPipeline


def run_live_query(
    config_path: Path,
    question: str,
    context: dict[str, str] | None = None,
    output: Path | None = None,
) -> StoryView:
    """Execute exactly one `run_orchestrated` call and optionally write HTML."""

    config = load_event_demo_config(config_path)
    catalog = DemoCatalog.from_config(config)
    pipeline = M5BRiskonPipeline.from_milestone5b_config(
        load_milestone5b_config(config.runtime.pipeline_config)
    )
    run = pipeline.run_orchestrated(QueryInput(query=question, context=context or {}))
    story = story_view_from_run(
        run,
        case_id="LIVE",
        source_case_id="M5B-RUNTIME",
        story_kind="LIVE_SYNTHETIC_QUERY",
        title="Live synthetic query",
        question=question,
        presentation_message=(
            "This result was produced by one local orchestrated runtime call over the "
            "synthetic contract."
        ),
        audit_reference="m5b:demo-live-query",
        maximum_excerpt_characters=config.rendering.maximum_evidence_excerpt_characters,
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_story_html(story, catalog.presentation_copy), encoding="utf-8")
    return story


def load_context_file(path: Path, context_id: str) -> dict[str, str]:
    """Load one named context from the local ER-B context-preset file."""

    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Context file must contain valid JSON") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("presets"), list):
        raise ValueError("Context file must contain a presets list")
    for item in raw["presets"]:
        if isinstance(item, dict) and item.get("id") == context_id:
            context = item.get("context")
            if not isinstance(context, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in context.items()
            ):
                raise ValueError(f"Context preset {context_id} is not a string mapping")
            return dict(context)
    raise KeyError(f"Unknown context preset: {context_id}")
