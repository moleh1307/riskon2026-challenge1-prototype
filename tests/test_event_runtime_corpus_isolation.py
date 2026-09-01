"""Event runtime corpus and source-integrity boundaries."""

from pathlib import Path

from riskon.event_intake.path_safety import snapshot_source, snapshots_unchanged
from riskon.event_runtime.config import EventRuntimeConfig
from riskon.event_runtime.factory import EventRuntimeFactory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALID_PACK = PROJECT_ROOT / "data" / "synthetic" / "event_readiness" / "valid_pack"


def event_config(tmp_path: Path) -> EventRuntimeConfig:
    return EventRuntimeConfig(
        project_root=PROJECT_ROOT,
        pipeline_config=PROJECT_ROOT / "config" / "milestone5b.toml",
        source_root=VALID_PACK,
        manifest=VALID_PACK / "manifest.xlsx",
        column_mapping={},
        url_prefix="local://event-wiki/",
        generated_root=tmp_path / "generated",
        alias_registry=tmp_path / "event_aliases.json",
        routing_profile="default",
        overlay_enabled=False,
        event_data_copy_enabled=False,
        network_enabled=False,
        external_api_enabled=False,
    )


def test_event_runtime_replaces_synthetic_m4d_corpus(tmp_path: Path) -> None:
    pipeline = EventRuntimeFactory.build(event_config(tmp_path))

    assert pipeline._m4d_runtime is not None
    corpus = pipeline._m4d_runtime.corpus
    assert corpus.sections
    assert {section.filename for section in corpus.sections} == {
        "knowledge/direct_rule.html",
        "knowledge/contextual_workflow.html",
        "knowledge/alert_table.html",
    }
    assert all(section.source_ref.startswith("local://event-wiki/") for section in corpus.sections)
    assert not any("synthetic-m4d" in ref for ref in corpus.provenance.local_refs())


def test_event_runtime_does_not_mutate_source(tmp_path: Path) -> None:
    before = snapshot_source(VALID_PACK)

    EventRuntimeFactory.build(event_config(tmp_path))

    after = snapshot_source(VALID_PACK)
    assert snapshots_unchanged(before, after)
