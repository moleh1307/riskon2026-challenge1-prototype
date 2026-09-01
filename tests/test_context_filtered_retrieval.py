"""M2 explicit scope conflict filtering tests."""

import json
from pathlib import Path

from riskon.models import QueryInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = PROJECT_ROOT / "data" / "synthetic" / "m2" / "evaluation_cases.json"


def test_region_alpha_distractor_is_excluded_before_final_fusion(m2_pipeline) -> None:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    case = next(item for item in payload["cases"] if item["id"] == "M2-015")
    request = QueryInput(query=case["query"], context=case["input_context"])
    planned = m2_pipeline.run_planned(request)
    alpha_ref = "local://synthetic-m2/control_delta_region_alpha.html#section-service-plus"
    final_refs = {
        entry.candidate_ref for entry in planned.retrieval_diagnostics.entries if entry.included
    }
    alpha_entries = [
        entry for entry in planned.retrieval_diagnostics.entries if entry.candidate_ref == alpha_ref
    ]
    assert alpha_ref not in final_refs
    assert alpha_entries
    assert all(entry.included is False for entry in alpha_entries)
    assert all(entry.exclusion_reason == "CONTEXT_CONFLICT" for entry in alpha_entries)
    assert planned.verified_run.verification.scope_mismatches == []
