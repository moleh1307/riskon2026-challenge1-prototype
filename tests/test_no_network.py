"""Static and runtime network-boundary checks."""

import ast
from pathlib import Path

from riskon.config import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROHIBITED = {
    "requests",
    "httpx",
    "urllib.request",
    "http.client",
    "socket",
    "openai",
    "google.generativeai",
    "google.genai",
    "boto3",
    "subprocess",
}


def test_source_has_no_network_or_cloud_imports() -> None:
    found: list[str] = []
    for path in (PROJECT_ROOT / "src" / "riskon").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend(alias.name for alias in node.names if alias.name in PROHIBITED)
            elif isinstance(node, ast.ImportFrom) and node.module in PROHIBITED:
                found.append(node.module)
    assert found == []


def test_network_is_disabled_in_canonical_config() -> None:
    config = load_config(PROJECT_ROOT / "config" / "milestone0.toml")
    assert config.security.network_enabled is False
    assert config.runtime.confidence_kind == "DETERMINISTIC_GATE_PLACEHOLDER"
