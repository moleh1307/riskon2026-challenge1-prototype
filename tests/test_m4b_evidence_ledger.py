"""Append-only evidence ledger tests."""

import pytest

from riskon.orchestra.ledger import EvidenceLedger
from riskon.orchestra.models import AgentFinding, FindingStance


def finding(*, finding_id: str = "finding:one", ref: str = "local://synthetic-m4/a.html"):
    return AgentFinding(
        finding_id=finding_id,
        task_id="task:plan:evidence_scout",
        agent_id="AGENT-M4-EVIDENCE-001",
        agent_role="EVIDENCE_SCOUT",
        claim_id="claim-a",
        stance=FindingStance.SUPPORT,
        evidence_refs=[ref],
        source_scope="LOCAL",
        criticality="NORMAL",
    )


def test_ledger_deduplicates_semantics_but_keeps_ids_guarded() -> None:
    ledger = EvidenceLedger({"local://synthetic-m4/a.html"})
    assert ledger.append(finding()) is True
    equivalent = finding(finding_id="finding:two")
    assert ledger.append(equivalent) is False
    assert [item.finding_id for item in ledger.findings] == ["finding:one"]
    with pytest.raises(ValueError, match="Duplicate finding_id"):
        ledger.append(finding())


def test_ledger_sorts_fan_in_and_returns_detached_findings() -> None:
    ledger = EvidenceLedger({"local://synthetic-m4/a.html", "local://synthetic-m4/b.html"})
    second = finding(finding_id="finding:b", ref="local://synthetic-m4/b.html")
    first = finding(finding_id="finding:a")
    ledger.append_many([second, first])
    assert [item.finding_id for item in ledger.findings] == ["finding:a", "finding:b"]
    detached = ledger.findings
    detached[0].evidence_refs.append("local://synthetic-m4/b.html")
    assert ledger.evidence_refs() == ["local://synthetic-m4/a.html", "local://synthetic-m4/b.html"]


@pytest.mark.parametrize(
    "reference",
    [
        "https://example.invalid/source",
        "agent://worker/finding",
        "task://other/task",
        "/tmp/source.html",
        "local://outside/source",
    ],
)
def test_ledger_rejects_non_local_or_non_corpus_references(reference: str) -> None:
    with pytest.raises(ValueError):
        EvidenceLedger({"local://synthetic-m4/a.html"}).append(finding(ref=reference))
