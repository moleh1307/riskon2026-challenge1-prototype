"""Contract tests for the event-backed unified runtime."""

from pathlib import Path

from riskon.event_runtime.config import EventRuntimeConfig
from riskon.event_runtime.factory import EventRuntimeFactory
from riskon.models import QueryInput

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


def test_event_factory_builds_and_uses_event_provenance(tmp_path: Path) -> None:
    pipeline = EventRuntimeFactory.build(event_config(tmp_path))

    calls: list[QueryInput] = []
    assert pipeline._m4d_runtime is not None
    original_run_planned = pipeline._m4d_runtime.run_planned

    def counted_run_planned(request: QueryInput):
        calls.append(request)
        return original_run_planned(request)

    pipeline._m4d_runtime.run_planned = counted_run_planned
    run = pipeline.run_orchestrated(
        QueryInput(query="How should a delegated operator handle the record?")
    )

    assert len(calls) == 1
    assert run.baseline_run.verified_run.result.evidence
    refs = [item.source_ref for item in run.baseline_run.verified_run.result.evidence]
    assert refs
    assert all(ref.startswith("local://event-wiki/") for ref in refs)
    assert all("synthetic-m4d" not in ref for ref in refs)
    assert all("/Users/" not in ref for ref in refs)


def test_event_factory_writes_only_descriptor_intake_artifacts(tmp_path: Path) -> None:
    config = event_config(tmp_path)
    EventRuntimeFactory.build(config)

    output = config.generated_root / "intake"
    assert (output / "inspection.json").is_file()
    assert (output / "prepared_corpus.json").is_file()
    assert not list(output.rglob("*.html"))
