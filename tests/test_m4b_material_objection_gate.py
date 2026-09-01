"""Material-objection gate tests."""

from riskon.orchestra.adjudication import MaterialObjectionGate
from riskon.orchestra.models import MaterialObjection


def objection(objection_id: str, status: str, materiality: str = "MATERIAL") -> MaterialObjection:
    return MaterialObjection(
        objection_id=objection_id,
        agent_id="AGENT-M4-SKEPTIC-001",
        target_claim_id="claim-a",
        reason_code="CONTRADICTORY_EVIDENCE",
        materiality=materiality,
        evidence_refs=["local://synthetic-m4/conflict_policy_a.html#section-synthetic-rule-a"],
        status=status,
        resolvable_by="M1_VERIFICATION_AUTHORITY",
    )


def test_gate_preserves_history_but_blocks_open_material_objection() -> None:
    decision = MaterialObjectionGate().evaluate(
        [objection("objection:2", "OPEN"), objection("objection:1", "RESOLVED")]
    )
    assert [item.objection_id for item in decision.objections] == [
        "objection:1",
        "objection:2",
    ]
    assert decision.answer_allowed is False
    assert [item.objection_id for item in decision.open_material_objections] == ["objection:2"]


def test_gate_allows_resolved_or_non_material_history() -> None:
    decision = MaterialObjectionGate().evaluate(
        [objection("objection:1", "RESOLVED"), objection("objection:2", "OPEN", "NON_MATERIAL")]
    )
    assert decision.answer_allowed is True
    assert decision.open_material_objections == ()


def test_gate_accepts_empty_objection_history() -> None:
    decision = MaterialObjectionGate().evaluate([])
    assert decision.objections == ()
    assert decision.answer_allowed is True
