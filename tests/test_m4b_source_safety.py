"""M4B source-content safety tests."""

import json
from pathlib import Path

import pytest
from m4b_helpers import M4_ROOT

from riskon.orchestra.source_safety import SourceSafetyPolicy, build_local_corpus


def _policy() -> SourceSafetyPolicy:
    return SourceSafetyPolicy.from_file(M4_ROOT / "source_safety_policy.json")


def test_source_safety_marks_instruction_child_but_keeps_valid_sibling_allowed() -> None:
    corpus = build_local_corpus(M4_ROOT / "manifest.xlsx", M4_ROOT / "knowledge")
    policy = _policy()
    report = policy.inspect(corpus)
    safe = (
        "local://synthetic-m4/prompt_injection_source.html#section-valid-synthetic-policy-statement"
    )
    unsafe = "local://synthetic-m4/prompt_injection_source.html#section-untrusted-instruction-text:sentence-1"
    assert policy.evidence_allowed(safe, report) is True
    assert policy.evidence_allowed(unsafe, report) is False
    assert report.diagnostics[0].diagnostic_code == "SOURCE_INSTRUCTION_IGNORED"


@pytest.mark.parametrize(
    "reference",
    ["https://bad.invalid", "agent://x", "task://x", "/Users/private/source", "other://x"],
)
def test_source_safety_rejects_external_and_worker_references(reference: str) -> None:
    with pytest.raises(ValueError, match="Unsafe or non-source"):
        _policy().validate_evidence_ref(reference)


def test_source_safety_loader_rejects_unknown_schema_key(tmp_path: Path) -> None:
    raw = json.loads((M4_ROOT / "source_safety_policy.json").read_text(encoding="utf-8"))
    raw["unknown"] = True
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="fields do not match"):
        SourceSafetyPolicy.from_file(path)
