"""Configuration for the repo-external event runtime."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventRuntimeConfig(BaseModel):
    """Resolved event runtime inputs and fail-closed switches."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_root: Path
    pipeline_config: Path
    source_root: Path
    manifest: Path
    column_mapping: dict[str, str] = Field(default_factory=dict)
    url_prefix: str
    generated_root: Path
    alias_registry: Path
    routing_profile: str = Field(min_length=1)
    overlay_enabled: bool
    event_data_copy_enabled: bool
    network_enabled: bool
    external_api_enabled: bool

    @classmethod
    def from_file(cls, config_path: Path) -> EventRuntimeConfig:
        """Load a local event config while allowing the corpus itself outside the repo."""

        resolved_config = config_path.expanduser().resolve()
        if not resolved_config.is_file():
            raise FileNotFoundError(f"Event runtime configuration not found: {resolved_config}")
        with resolved_config.open("rb") as handle:
            raw = tomllib.load(handle)
        if not isinstance(raw, dict) or set(raw) != {
            "base",
            "event_corpus",
            "event_runtime",
            "security",
        }:
            raise ValueError("Event runtime configuration fields do not match the contract")
        project_root = _find_project_root(resolved_config)
        base = _table(raw, "base")
        corpus = _table(raw, "event_corpus")
        runtime = _table(raw, "event_runtime")
        security = _table(raw, "security")
        if set(base) != {"pipeline_config"}:
            raise ValueError("Event runtime base fields do not match the contract")
        if set(corpus) != {
            "source_root",
            "manifest",
            "column_mapping",
            "url_prefix",
            "generated_root",
        }:
            raise ValueError("Event runtime corpus fields do not match the contract")
        if set(runtime) != {"alias_registry", "routing_profile", "overlay_enabled"}:
            raise ValueError("Event runtime fields do not match the contract")
        if set(security) != {
            "event_data_copy_enabled",
            "network_enabled",
            "external_api_enabled",
        }:
            raise ValueError("Event runtime security fields do not match the contract")
        source_root = _resolve_external_path(corpus.get("source_root"), "event_corpus.source_root")
        manifest = _resolve_external_path(corpus.get("manifest"), "event_corpus.manifest")
        pipeline_config = _resolve_repo_path(
            project_root, base.get("pipeline_config"), "base.pipeline_config"
        )
        generated_root = _resolve_repo_path(
            project_root, corpus.get("generated_root"), "event_corpus.generated_root"
        )
        alias_registry = _resolve_repo_path(
            project_root, runtime.get("alias_registry"), "event_runtime.alias_registry"
        )
        mapping = corpus.get("column_mapping")
        if not isinstance(mapping, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()
        ):
            raise ValueError("event_corpus.column_mapping must be an object of strings")
        url_prefix = corpus.get("url_prefix")
        if not isinstance(url_prefix, str) or url_prefix != "local://event-wiki/":
            raise ValueError("Event runtime provenance must use local://event-wiki/")
        config = cls(
            project_root=project_root,
            pipeline_config=pipeline_config,
            source_root=source_root,
            manifest=manifest,
            column_mapping=dict(mapping),
            url_prefix=url_prefix,
            generated_root=generated_root,
            alias_registry=alias_registry,
            routing_profile=_required_string(runtime.get("routing_profile"), "routing_profile"),
            overlay_enabled=bool(runtime.get("overlay_enabled")),
            event_data_copy_enabled=bool(security.get("event_data_copy_enabled")),
            network_enabled=bool(security.get("network_enabled")),
            external_api_enabled=bool(security.get("external_api_enabled")),
        )
        if not config.source_root.is_dir():
            raise FileNotFoundError(f"Event source root not found: {config.source_root}")
        if not config.manifest.is_file():
            raise FileNotFoundError(f"Event manifest not found: {config.manifest}")
        if config.overlay_enabled:
            raise ValueError("Event runtime overlay_enabled must remain false")
        if config.event_data_copy_enabled:
            raise ValueError("Event runtime event_data_copy_enabled must remain false")
        if config.network_enabled or config.external_api_enabled:
            raise ValueError("Event runtime network and external API must remain disabled")
        return config


def load_event_runtime_config(config_path: Path) -> EventRuntimeConfig:
    """Public config-loader convenience function."""

    return EventRuntimeConfig.from_file(config_path)


def _table(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"Event runtime table {name} is required")
    return value


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Event runtime {name} must be a non-empty string")
    return value.strip()


def _resolve_repo_path(project_root: Path, value: object, name: str) -> Path:
    raw = _required_string(value, name)
    candidate = Path(raw)
    if candidate.is_absolute():
        raise ValueError(f"Event runtime path {name} must be relative to the repository")
    resolved = (project_root / candidate).resolve()
    if not resolved.is_relative_to(project_root):
        raise ValueError(f"Event runtime path {name} must remain in the repository")
    return resolved


def _resolve_external_path(value: object, name: str) -> Path:
    raw = _required_string(value, name)
    return Path(raw).expanduser().resolve()


def _find_project_root(config_path: Path) -> Path:
    """Find the repository root without assuming the private config directory."""

    for candidate in (config_path.parent, *config_path.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src").is_dir():
            return candidate.resolve()
    raise ValueError("Event runtime configuration is not inside the repository")
