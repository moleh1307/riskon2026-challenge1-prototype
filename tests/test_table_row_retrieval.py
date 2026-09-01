"""M2 header-aware table-row retrieval tests."""

import json
from pathlib import Path

from riskon.models import QueryInput

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = PROJECT_ROOT / "data" / "synthetic" / "m2" / "evaluation_cases.json"


def test_configuration_lookup_returns_all_active_interactive_rows(m2_pipeline) -> None:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    case = next(item for item in payload["cases"] if item["id"] == "M2-016")
    planned = m2_pipeline.run_planned(
        QueryInput(query=case["query"], context=case["input_context"])
    )
    refs = {ref for ref in planned.verified_run.verification.evidence_refs if ":table-" in ref}
    assert refs == set(case["expected_retrieval"]["required_table_row_refs"])
    assert not refs & set(case["expected_retrieval"]["forbidden_table_row_refs"])
    assert planned.verified_run.verification.supported_claim_ids == [
        "atlas_alert_active",
        "beacon_alert_active",
        "cedar_alert_active",
    ]


def test_table_row_provenance_keeps_headers(m2_pipeline) -> None:
    row_ref = "local://synthetic-m2/alert_configuration.html#section-session-alerts:table-1:row-1"
    unit = m2_pipeline._m2_provenance.resolve(row_ref)
    assert unit is not None
    assert unit.kind == "table_row"
    assert unit.headers == ["Alert", "Location", "Mandate", "State", "Session"]
    assert "Alert: Atlas" in unit.text
