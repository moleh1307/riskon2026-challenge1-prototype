"""M2 retrieval diagnostics schema and exclusion tests."""

import json
from pathlib import Path

from riskon.models import QueryInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = PROJECT_ROOT / "data" / "synthetic" / "m2" / "evaluation_cases.json"


def test_diagnostics_have_exact_candidate_fields_and_allowed_exclusions(m2_pipeline) -> None:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    case = next(item for item in payload["cases"] if item["id"] == "M2-015")
    planned = m2_pipeline.run_planned(
        QueryInput(query=case["query"], context=case["input_context"])
    )
    assert planned.retrieval_diagnostics.entries
    for entry in planned.retrieval_diagnostics.entries:
        assert entry.plan_id == planned.query_plan.plan_id
        assert entry.candidate_ref.startswith("local://synthetic-m2/")
        assert entry.channel_rank >= 1
        assert entry.raw_score > 0.0
        assert entry.exclusion_reason in {
            None,
            "CONTEXT_CONFLICT",
            "DUPLICATE_EVIDENCE",
            "BELOW_CHANNEL_THRESHOLD",
            "NOT_SELECTED_TOP_K",
        }


def test_short_circuit_has_no_diagnostics(m2_pipeline) -> None:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    case = next(item for item in payload["cases"] if item["id"] == "M2-017")
    planned = m2_pipeline.run_planned(
        QueryInput(query=case["query"], context=case["input_context"])
    )
    assert planned.retrieval_diagnostics.entries == []
