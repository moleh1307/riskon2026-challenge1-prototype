"""M1 verification-contract gate tests."""

import json
from pathlib import Path

from riskon.models import QueryInput, ReasonCode, VerificationReport, VerifiedRun

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = PROJECT_ROOT / "data" / "synthetic" / "m1" / "evaluation_cases.json"


def _cases() -> dict[str, dict[str, object]]:
    payload = json.loads(CASE_PATH.read_text(encoding="utf-8"))
    return {case["id"]: case for case in payload["cases"]}


def _run(m1_pipeline, case_id: str):
    case = _cases()[case_id]
    return m1_pipeline.run_verified(QueryInput(query=case["query"], context=case["input_context"]))


def test_verified_models_have_exact_public_fields() -> None:
    assert set(VerificationReport.model_fields) == {
        "status",
        "reason_codes",
        "supported_claim_ids",
        "unsupported_claim_ids",
        "missing_required_claim_ids",
        "scope_mismatches",
        "unresolved_required_references",
        "unsupported_modalities",
        "evidence_refs",
        "explanation",
    }
    assert set(VerifiedRun.model_fields) == {"result", "verification"}


def test_ambiguous_acronym_clarifies_exactly(m1_pipeline) -> None:
    verified = _run(m1_pipeline, "M1-006")
    assert verified.result.decision.value == "CLARIFY"
    assert verified.result.clarifying_question == (
        "Do you mean Advisory Review Code or Account Routing Console?"
    )
    assert verified.result.route is None
    assert verified.verification.reason_codes == [ReasonCode.AMBIGUOUS_ACRONYM]
    assert verified.verification.status.value == "INSUFFICIENT"


def test_unsupported_service_model_abstains_and_routes_legal(m1_pipeline) -> None:
    verified = _run(m1_pipeline, "M1-007")
    assert verified.result.decision.value == "ABSTAIN"
    assert verified.result.answer is None
    assert verified.result.reason_codes == [ReasonCode.NO_EXPLICIT_SUPPORT]
    assert verified.result.route is not None
    assert verified.result.route.support_function == "SUITABILITY_EXPERT_LEGAL"
    assert verified.result.route.expert_id == "SYN-LEGAL-001"


def test_critical_controls_are_both_supported(m1_pipeline) -> None:
    verified = _run(m1_pipeline, "M1-008")
    assert verified.result.decision.value == "ANSWER"
    assert verified.result.answer is not None
    assert "must not proceed" in verified.result.answer
    assert "Client acceptance does not override" in verified.result.answer
    assert verified.verification.supported_claim_ids == [
        "do_not_proceed",
        "client_acceptance_does_not_override",
    ]
    assert all(claim.critical for claim in verified.verification.claims)


def test_missing_form_abstains_with_business_support(m1_pipeline) -> None:
    verified = _run(m1_pipeline, "M1-009")
    assert verified.result.decision.value == "ABSTAIN"
    assert verified.result.reason_codes == [ReasonCode.UNRESOLVED_REQUIRED_REFERENCE]
    assert verified.verification.unresolved_required_references == [
        "attachments/exception-request-form.pdf"
    ]
    assert verified.result.route is not None
    assert verified.result.route.expert_id == "SYN-BFS-001"


def test_image_only_methodology_abstains_without_image_interpretation(m1_pipeline) -> None:
    verified = _run(m1_pipeline, "M1-010")
    assert verified.result.decision.value == "ABSTAIN"
    assert verified.result.reason_codes == [ReasonCode.UNSUPPORTED_MODALITY]
    assert verified.verification.unsupported_modalities == [
        "local://synthetic-m1/image_only_methodology.html#asset-1"
    ]
    assert verified.result.route is not None
    assert verified.result.route.expert_id is None


def test_adjacent_unrelated_section_is_excluded(m1_pipeline) -> None:
    verified = _run(m1_pipeline, "M1-011")
    assert verified.result.decision.value == "ANSWER"
    assert verified.result.answer is not None
    assert "A synthetic recommendation is" in verified.result.answer
    assert "solicitation process records" not in verified.result.answer
    assert verified.verification.supported_claim_ids == ["recommendation_definition"]
    assert "unrelated_solicitation_process" not in verified.verification.supported_claim_ids


def test_approval_request_routes_compliance_without_granting_exception(m1_pipeline) -> None:
    verified = _run(m1_pipeline, "M1-012")
    assert verified.result.decision.value == "ABSTAIN"
    assert verified.result.answer is None
    assert verified.result.reason_codes == [ReasonCode.APPROVAL_REQUIRED]
    assert verified.result.route is not None
    assert verified.result.route.support_function == "SUITABILITY_EXPERT_COMPLIANCE"
    assert verified.result.route.expert_id == "SYN-COMPLIANCE-001"


def test_m1_evidence_refs_are_local_and_report_claims_are_addressed(m1_pipeline) -> None:
    for case_id in _cases():
        verified = _run(m1_pipeline, case_id)
        assert verified.verification.evidence_refs
        assert all(
            ref.startswith("local://synthetic-m1/") for ref in verified.verification.evidence_refs
        )
        for claim in verified.verification.claims:
            assert claim.evidence_refs
            assert all(ref in verified.verification.evidence_refs for ref in claim.evidence_refs)
