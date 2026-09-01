"""Pre-production contract checks for fixture-backed M3 evaluation."""

import json
from pathlib import Path

from riskon.models import PlannedVerifiedRun

PROJECT_ROOT = Path(__file__).resolve().parents[1]
M3_ROOT = PROJECT_ROOT / "data" / "synthetic" / "m3"
CASES_PATH = M3_ROOT / "evaluation_cases.json"
UPSTREAM_ROOT = M3_ROOT / "upstream_runs"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _planned(case: dict[str, object]) -> PlannedVerifiedRun:
    ref = str(case["upstream_fixture_ref"])
    prefix = "local://synthetic-m3/upstream-runs/"
    return PlannedVerifiedRun.model_validate(
        _load(UPSTREAM_ROOT / ref.removeprefix(prefix))["planned_verified_run"]
    )


def test_fixture_loader_is_query_free_and_complete() -> None:
    payload = _load(CASES_PATH)
    cases = payload["cases"]
    assert isinstance(cases, list) and len(cases) == 8
    assert all("query" not in case for case in cases)
    assert all(
        _planned(case).query_plan.original_query and _planned(case).query_plan.normalised_query
        for case in cases
    )


def test_fixture_backed_harness_never_calls_run_planned(monkeypatch) -> None:
    payload = _load(CASES_PATH)
    cases = payload["cases"]
    calls: list[str] = []

    class FixtureOnlyHarness:
        def run_planned(self, _query):
            calls.append("run_planned")
            raise AssertionError("M3 fixture evaluation must not call run_planned")

        def evaluate_case(self, case: dict[str, object]) -> PlannedVerifiedRun:
            return _planned(case)

    harness = FixtureOnlyHarness()
    monkeypatch.setattr(harness, "run_planned", harness.run_planned)
    for case in cases:
        planned = harness.evaluate_case(case)
        assert planned.verified_run.result.decision.value == "ABSTAIN"
    assert calls == []
