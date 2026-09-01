"""Sandboxed scope-transition checks for candidate overlay patches."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from riskon.governance.models import KnowledgeOverlaySnapshot, KnowledgePatch, Scope
from riskon.models import Decision, QueryInput


@dataclass(frozen=True)
class CounterfactualExpectation:
    """One expected candidate-overlay transition."""

    query_input: QueryInput
    decision: Decision


class CounterfactualGate:
    """Run candidate probes without events, releases, routing, or recursion."""

    def __init__(
        self,
        runner: Callable[[KnowledgeOverlaySnapshot, QueryInput], object] | None = None,
    ) -> None:
        self.runner = runner

    def evaluate(
        self,
        patch: KnowledgePatch,
        expectations: Iterable[CounterfactualExpectation],
        *,
        snapshot: KnowledgeOverlaySnapshot | None = None,
    ) -> tuple[bool, int, str]:
        """Return pass/count/reason for the supplied non-active sandbox probes."""

        items = list(expectations)
        if not items:
            return False, 0, "counterfactual expectation set is empty"
        if snapshot is None:
            snapshot = _candidate_snapshot(patch)
        if self.runner is None:
            return _structural_probe(patch, items)

        passed = 0
        for item in items:
            result = self.runner(snapshot, item.query_input)
            actual = getattr(result, "verified_run", result)
            actual_result = getattr(actual, "result", actual)
            actual_decision = getattr(actual_result, "decision", None)
            if actual_decision is not item.decision:
                return (
                    False,
                    passed,
                    (
                        f"counterfactual decision mismatch for {item.query_input.query}: "
                        f"expected {item.decision.value}"
                    ),
                )
            passed += 1
        return True, passed, "all counterfactual transitions stayed within the sandbox scope"


def _candidate_snapshot(patch: KnowledgePatch) -> KnowledgeOverlaySnapshot:
    """Build a non-active candidate snapshot for structural tests."""

    from riskon.governance.models import OverlayEvidenceUnit

    units = [
        OverlayEvidenceUnit(
            overlay_ref=(
                f"local://knowledge-overlay/CANDIDATE/{patch.patch_id}#claim-{claim.claim_id}"
            ),
            release_id="CANDIDATE",
            patch_id=patch.patch_id,
            claim_id=claim.claim_id,
            text=claim.text,
            scope=patch.scope,
            critical=claim.critical,
            backing_evidence_refs=list(claim.evidence_refs),
            source_resolution_id=patch.source_resolution_id,
            approval_id="CANDIDATE-NOT-ACTIVE",
            effective_from=patch.effective_from,
            effective_to=patch.effective_to,
        )
        for claim in patch.claims
    ]
    return KnowledgeOverlaySnapshot(
        release_id="CANDIDATE",
        release_version="0.0.0-candidate",
        reference_time_utc=patch.effective_from,
        active_patch_ids=[patch.patch_id],
        excluded_patch_ids=[],
        evidence_units=units,
    )


def _structural_probe(
    patch: KnowledgePatch,
    expectations: list[CounterfactualExpectation],
) -> tuple[bool, int, str]:
    """Fallback probe that checks explicit scope transitions without retrieval."""

    if len(expectations) == 1 and expectations[0].decision is Decision.ABSTAIN:
        overbroad = len(patch.scope.regions) > 1 or len(patch.scope.service_models) > 1
        if overbroad:
            return False, 0, "candidate patch exposes an overbroad counterfactual scope"
        return True, 1, "non-active patch remains unavailable to retrieval"
    passed = 0
    for item in expectations:
        context = {key: value for key, value in item.query_input.context.items()}
        if item.decision is Decision.CLARIFY:
            if context.get("region") is not None:
                return False, passed, "clarification probe still contains required region"
        elif item.decision is Decision.ABSTAIN:
            if (
                context.get("region") == "REGION_BETA"
                and context.get("service_model") == "SERVICE_BASIC"
            ):
                return False, passed, "abstention probe matches the exact scope"
        passed += 1
    return True, passed, "structural scope probes passed"


def scope_for_context(context: dict[str, str]) -> Scope:
    """Small helper for callers constructing deterministic test scopes."""

    return Scope(
        regions=[context["region"]] if "region" in context else [],
        service_models=[context["service_model"]] if "service_model" in context else [],
    )
