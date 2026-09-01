"""No-server static source checks for ER-B."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_demo_modules_do_not_import_server_or_process_capabilities() -> None:
    banned_modules = {
        "socket",
        "http.server",
        "flask",
        "fastapi",
        "streamlit",
        "gradio",
        "dash",
        "subprocess",
    }
    for path in (ROOT / "src" / "riskon" / "demo").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name not in banned_modules for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module not in banned_modules
