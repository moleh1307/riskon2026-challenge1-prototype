"""Evidence gate tests."""

from riskon.evidence import EvidenceChecker
from riskon.models import DetectedContext, NeedType, ReasonCode, RetrievalHit


def _hit(text: str, score: float = 0.5) -> RetrievalHit:
    return RetrievalHit(
        section_id="synthetic::section-01",
        source_ref="local://synthetic/page.html",
        title="Synthetic page",
        heading_path=["Rule"],
        score=score,
        excerpt=text,
        table_rows=[],
    )


def test_missing_context_is_a_reason_but_not_an_abstention_reason() -> None:
    check = EvidenceChecker().check(
        "workflow stage missing",
        DetectedContext(missing_context=["channel"]),
        [_hit("supported workflow")],
    )
    assert check.reason_codes == [ReasonCode.MISSING_REQUIRED_CONTEXT]
    assert check.missing_context == ["channel"]


def test_scope_and_technical_gates_are_explicit() -> None:
    scope = EvidenceChecker().check(
        "Region Beta policy",
        DetectedContext(region="REGION_BETA", need_type=NeedType.COMPLEX_CASE),
        [_hit("This policy applies to Region Alpha only.")],
    )
    assert scope.reason_codes == [ReasonCode.SCOPE_MISMATCH]
    technical = EvidenceChecker().check(
        "technical network-timeout",
        DetectedContext(need_type=NeedType.TECHNICAL_FAILURE),
        [_hit("technical failure", score=0.4)],
    )
    assert technical.reason_codes == [ReasonCode.TECHNICAL_FAILURE]


def test_weak_and_open_evidence_are_rejected() -> None:
    checker = EvidenceChecker()
    weak = checker.check("unknown topic", DetectedContext(), [_hit("unrelated", score=0.01)])
    assert weak.reason_codes == [ReasonCode.NO_RELEVANT_EVIDENCE]
    open_check = checker.check(
        "the evidence is unclear",
        DetectedContext(),
        [_hit("some evidence", score=0.4)],
    )
    assert open_check.reason_codes == [ReasonCode.OPEN_EVIDENCE]
