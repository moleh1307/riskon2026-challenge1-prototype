"""Append-only evidence ledger for isolated M4B worker findings."""

from __future__ import annotations

from riskon.orchestra.models import AgentFinding


class EvidenceLedger:
    """Validate, deduplicate, and retain source-grounded findings."""

    _allowed_prefixes = (
        "local://synthetic/",
        "local://synthetic-m1/",
        "local://synthetic-m2/",
        "local://synthetic-m4/",
        "local://synthetic-m4d/",
    )

    def __init__(self, allowed_evidence_refs: set[str] | frozenset[str] | None = None) -> None:
        self._allowed_evidence_refs = (
            frozenset(allowed_evidence_refs) if allowed_evidence_refs is not None else None
        )
        self._findings: list[AgentFinding] = []
        self._finding_ids: set[str] = set()
        self._semantic_keys: set[tuple[object, ...]] = set()

    def append(self, finding: AgentFinding) -> bool:
        """Append one finding; return false for a deterministic semantic duplicate."""

        if finding.finding_id in self._finding_ids:
            raise ValueError(f"Duplicate finding_id: {finding.finding_id}")
        for reference in finding.evidence_refs:
            self._validate_evidence_ref(reference)
            if (
                self._allowed_evidence_refs is not None
                and reference not in self._allowed_evidence_refs
            ):
                raise ValueError(f"Evidence reference is not in the local corpus: {reference}")
        semantic_key = (
            finding.claim_id,
            finding.stance.value,
            tuple(sorted(set(finding.evidence_refs))),
            finding.source_scope,
            finding.criticality,
            tuple(sorted(set(finding.limitations))),
        )
        self._finding_ids.add(finding.finding_id)
        if semantic_key in self._semantic_keys:
            return False
        self._semantic_keys.add(semantic_key)
        self._findings.append(finding.model_copy(deep=True))
        return True

    def append_many(self, findings: list[AgentFinding]) -> int:
        """Append findings in deterministic task/finding order."""

        count = 0
        for finding in sorted(findings, key=lambda item: (item.task_id, item.finding_id)):
            count += int(self.append(finding))
        return count

    @property
    def findings(self) -> list[AgentFinding]:
        """Return detached findings sorted for deterministic fan-in."""

        return [
            finding.model_copy(deep=True)
            for finding in sorted(self._findings, key=lambda item: (item.task_id, item.finding_id))
        ]

    def evidence_refs(self) -> list[str]:
        """Return all admitted source references in deterministic order."""

        return sorted(
            {reference for finding in self._findings for reference in finding.evidence_refs}
        )

    @classmethod
    def _validate_evidence_ref(cls, reference: str) -> None:
        if (
            not isinstance(reference, str)
            or not reference
            or reference.startswith(("http://", "https://", "agent://", "task://", "worker://"))
            or reference.startswith("/")
            or not reference.startswith(cls._allowed_prefixes)
        ):
            raise ValueError(f"Evidence reference must be a local source URI: {reference!r}")
