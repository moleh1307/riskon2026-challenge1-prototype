"""Orchestration service for M5B governed knowledge evolution."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from riskon.config import Milestone5BConfig
from riskon.governance.approval import require_approvable
from riskon.governance.counterfactual_gate import (
    CounterfactualExpectation,
    CounterfactualGate,
)
from riskon.governance.errors import (
    ExpiredPatchError,
    GovernanceError,
    MandatoryPolicyChecksFailedError,
    OfficialCorpusMutationError,
    ReleaseActivationError,
    SelfApprovalError,
)
from riskon.governance.event_store import GovernanceEventStore
from riskon.governance.lifecycle import transition
from riskon.governance.models import (
    ApprovalDecision,
    CaseCapsule,
    ClaimRelation,
    EvaluatedPatch,
    ExpertResolution,
    GovernanceEvent,
    GovernanceEventType,
    GovernedPatch,
    HumanApproval,
    KnowledgeOverlaySnapshot,
    KnowledgePatch,
    KnowledgeRelease,
    KnowledgeReleaseRequest,
    PatchStatus,
    PolicyCIPhase,
    PolicyCIReport,
    RegressionGateResult,
    ReleaseStatus,
)
from riskon.governance.overlay import compile_overlay_snapshot
from riskon.governance.policy_ci import PolicyCIExecutor
from riskon.governance.regression_gate import RegressionGate
from riskon.models import Decision, QueryInput


class GovernedKnowledgeService:
    """Enforce proposal, Policy CI, human approval, release, and overlay gates."""

    def __init__(
        self,
        config: Milestone5BConfig,
        *,
        event_store: GovernanceEventStore | None = None,
        regression_gate: RegressionGate | None = None,
        counterfactual_gate: CounterfactualGate | None = None,
        event_timestamp_utc: datetime | None = None,
    ) -> None:
        self.config = config
        if config.governance.official_corpus_mutation_enabled:
            raise OfficialCorpusMutationError("M5B official corpus mutation is disabled")
        self.m5a_root = config.governance.contract_cases.parent
        self._relations = self._load_relations(config.governance.claim_relations)
        self._regression_gate = regression_gate or RegressionGate(config)
        self._regression_result: RegressionGateResult | None = None
        self._counterfactual_gate = counterfactual_gate or CounterfactualGate()
        self._counterfactual_runner: (
            Callable[[KnowledgeOverlaySnapshot, QueryInput], object] | None
        ) = None
        self._governed_patches: dict[str, GovernedPatch] = {}
        self._resolutions: dict[str, ExpertResolution] = {}
        self._approvals: dict[str, HumanApproval] = {}
        self._releases: dict[str, KnowledgeRelease] = {}
        self._event_timestamp_utc = (
            _as_utc(event_timestamp_utc) if event_timestamp_utc is not None else None
        )
        self.event_store = event_store or GovernanceEventStore(
            config.governance.generated_root / "governance_events.jsonl"
        )
        self._event_sequence = len(self.event_store.events)

    def set_event_clock(self, timestamp_utc: datetime | None) -> None:
        """Use a fixed event clock for reproducible synthetic evaluations."""

        self._event_timestamp_utc = _as_utc(timestamp_utc) if timestamp_utc is not None else None

    def set_counterfactual_runner(
        self,
        runner: Callable[[KnowledgeOverlaySnapshot, QueryInput], object],
    ) -> None:
        """Install an optional pipeline probe for candidate sandbox testing."""

        self._counterfactual_runner = runner
        self._counterfactual_gate = CounterfactualGate(runner)

    def record_proposal(
        self,
        resolution: ExpertResolution,
        patch: KnowledgePatch,
    ) -> None:
        """Record a proposal without changing its status or activating it."""

        self._resolutions[resolution.resolution_id] = resolution
        self._record_event(
            GovernanceEventType.PATCH_PROPOSED,
            patch=patch,
            resolution=resolution,
            previous_status=None,
            new_status=PatchStatus.PROPOSED,
        )

    def record_awaiting_approval(
        self,
        resolution: ExpertResolution,
        patch: KnowledgePatch,
    ) -> None:
        """Record the non-active state after automated checks pass."""

        self._record_event(
            GovernanceEventType.PATCH_AWAITING_APPROVAL,
            patch=patch,
            resolution=resolution,
            previous_status=PatchStatus.TESTED,
            new_status=PatchStatus.AWAITING_APPROVAL,
        )

    def record_expiry(
        self,
        resolution: ExpertResolution,
        patch: KnowledgePatch,
    ) -> None:
        """Record expiry without making the patch retrievable."""

        self._record_event(
            GovernanceEventType.PATCH_EXPIRED,
            patch=patch,
            resolution=resolution,
            previous_status=PatchStatus.ACTIVE,
            new_status=PatchStatus.EXPIRED,
        )

    def run_policy_ci(
        self,
        case_capsule: CaseCapsule,
        expert_resolution: ExpertResolution,
        knowledge_patch: KnowledgePatch,
        approval: HumanApproval | None,
        reference_time_utc: datetime,
        phase: PolicyCIPhase,
    ) -> PolicyCIReport:
        """Run all eleven checks without granting approval or activation."""

        del case_capsule
        if self.config.governance.policy_ci.recursive_policy_ci_enabled:
            raise GovernanceError("Recursive Policy CI is disabled")
        if self.config.governance.policy_ci.counterfactual_routing_enabled:
            raise GovernanceError("Counterfactual routing inside Policy CI is disabled")
        reference_time_utc = _as_utc(reference_time_utc)
        self._resolutions[expert_resolution.resolution_id] = expert_resolution
        self._record_event(
            GovernanceEventType.POLICY_CI_COMPLETED,
            patch=knowledge_patch,
            resolution=expert_resolution,
            approval=approval,
            new_status=knowledge_patch.status,
        )
        report = PolicyCIExecutor(
            self._relations,
            self.resolve_reference,
            self._run_regression,
            lambda patch: self._run_counterfactual(patch),
        ).run(
            expert_resolution,
            knowledge_patch,
            approval,
            reference_time_utc,
            phase,
        )
        return report

    def apply_human_decision(
        self,
        evaluated_patch: EvaluatedPatch,
        approval: HumanApproval,
    ) -> GovernedPatch:
        """Apply an independent decision while keeping APPROVED non-active."""

        patch = evaluated_patch.knowledge_patch
        resolution = evaluated_patch.expert_resolution
        if approval.patch_id != patch.patch_id:
            raise ReleaseActivationError("Human decision does not match the evaluated patch")
        if approval.actor_role_id == resolution.resolution_author_role_id:
            raise SelfApprovalError("The resolution author cannot approve the same patch")
        if approval.decision is ApprovalDecision.APPROVE:
            failed = [
                item.check_id.value
                for item in evaluated_patch.policy_ci_report.checks
                if item.status.value == "FAIL"
            ]
            if failed:
                raise MandatoryPolicyChecksFailedError(failed)
            require_approvable(resolution, approval)
            governed_status = transition(PatchStatus.AWAITING_APPROVAL, PatchStatus.APPROVED)
            self._record_event(
                GovernanceEventType.HUMAN_DECISION_RECORDED,
                patch=patch,
                resolution=resolution,
                approval=approval,
                previous_status=PatchStatus.AWAITING_APPROVAL,
                new_status=governed_status,
            )
            self._record_event(
                GovernanceEventType.PATCH_APPROVED,
                patch=patch,
                resolution=resolution,
                approval=approval,
                previous_status=PatchStatus.AWAITING_APPROVAL,
                new_status=governed_status,
            )
        else:
            governed_status = PatchStatus.REJECTED
            self._record_event(
                GovernanceEventType.HUMAN_DECISION_RECORDED,
                patch=patch,
                resolution=resolution,
                approval=approval,
                previous_status=patch.status,
                new_status=governed_status,
            )
            self._record_event(
                GovernanceEventType.PATCH_REJECTED,
                patch=patch,
                resolution=resolution,
                approval=approval,
                previous_status=patch.status,
                new_status=governed_status,
            )
        governed = GovernedPatch(
            case_capsule=evaluated_patch.case_capsule,
            expert_resolution=resolution,
            knowledge_patch=patch,
            policy_ci_report=evaluated_patch.policy_ci_report,
            approval=approval,
            status=governed_status,
        )
        self._governed_patches[patch.patch_id] = governed
        self._approvals[patch.patch_id] = approval
        return governed

    def activate_release(
        self,
        governed_patches: tuple[GovernedPatch, ...],
        release_request: KnowledgeReleaseRequest,
        reference_time_utc: datetime,
    ) -> KnowledgeRelease:
        """Create and explicitly activate a versioned release."""

        if self.config.governance.automatic_activation_enabled:
            raise ReleaseActivationError("Automatic release activation is disabled")
        reference_time_utc = _as_utc(reference_time_utc)
        if release_request.requested_by_role_id == "":
            raise ReleaseActivationError("Release activation requester is required")
        for governed in governed_patches:
            if governed.status is PatchStatus.EXPIRED:
                raise ExpiredPatchError(f"Patch {governed.patch_id} is expired")
            if governed.status is not PatchStatus.APPROVED:
                raise ReleaseActivationError(
                    f"Patch {governed.patch_id} has not reached APPROVED status"
                )
            if (
                governed.approval.actor_role_id
                == governed.expert_resolution.resolution_author_role_id
            ):
                raise ReleaseActivationError("Self-approved patches cannot be activated")
            if governed.approval.decision is not ApprovalDecision.APPROVE:
                raise ReleaseActivationError("Only APPROVE decisions can activate a release")
            if governed.policy_ci_report.failed_check_ids:
                raise MandatoryPolicyChecksFailedError(
                    [item.value for item in governed.policy_ci_report.failed_check_ids]
                )
        previous = self._previous_release(release_request.release_id)
        release = KnowledgeRelease(
            release_id=release_request.release_id,
            version=previous[1] if previous else _version_for_request(release_request.release_id),
            previous_release_id=previous[0] if previous else None,
            patch_ids=[item.patch_id for item in governed_patches],
            created_at_utc=reference_time_utc,
            activated_at_utc=reference_time_utc,
            activated_by_role_id=release_request.requested_by_role_id,
            status=ReleaseStatus.ACTIVE,
        )
        self._record_event(
            GovernanceEventType.RELEASE_CREATED,
            release=release,
            new_status=PatchStatus.ACTIVE,
        )
        active_patches: list[GovernedPatch] = []
        for governed in governed_patches:
            active = governed.model_copy(update={"status": PatchStatus.ACTIVE})
            active_patches.append(active)
            self._governed_patches[governed.patch_id] = active
            self._record_event(
                GovernanceEventType.RELEASE_ACTIVATED,
                patch=governed.knowledge_patch,
                resolution=governed.expert_resolution,
                approval=governed.approval,
                release=release,
                previous_status=PatchStatus.APPROVED,
                new_status=PatchStatus.ACTIVE,
            )
        self._releases[release.release_id] = release
        return release

    def compile_overlay(
        self,
        knowledge_release: KnowledgeRelease,
        reference_time_utc: datetime,
    ) -> KnowledgeOverlaySnapshot:
        """Compile only current active-release claims into a snapshot."""

        if knowledge_release.status.value != "ACTIVE":
            raise ReleaseActivationError("Only an ACTIVE release can compile an overlay")
        if self.config.governance.overlay.special_ranking_boost:
            raise GovernanceError("Overlay ranking boosts are disabled")
        if self.config.governance.overlay.include_expired_patches:
            raise GovernanceError("Expired overlay patches are disabled")
        governed = tuple(
            self._governed_patches[item]
            for item in knowledge_release.patch_ids
            if item in self._governed_patches
        )
        snapshot = compile_overlay_snapshot(
            knowledge_release,
            governed,
            _as_utc(reference_time_utc),
        )
        for patch_id in snapshot.excluded_patch_ids:
            if patch_id in self._governed_patches:
                self._record_event(
                    GovernanceEventType.PATCH_EXPIRED,
                    patch=self._governed_patches[patch_id].knowledge_patch,
                    resolution=self._governed_patches[patch_id].expert_resolution,
                    previous_status=PatchStatus.ACTIVE,
                    new_status=PatchStatus.EXPIRED,
                )
        return snapshot

    def load_case_inputs(
        self,
        case_id: str,
    ) -> tuple[CaseCapsule, ExpertResolution, KnowledgePatch, HumanApproval | None]:
        """Load one frozen M5A case and its local governance records."""

        cases = json.loads(self.config.governance.contract_cases.read_text(encoding="utf-8"))[
            "cases"
        ]
        item = next((case for case in cases if case["id"] == case_id), None)
        if item is None:
            raise KeyError(case_id)
        capsule = CaseCapsule.model_validate_json(self._read_ref(item["case_capsule_ref"]))
        resolution = ExpertResolution.model_validate_json(
            self._read_ref(item["expert_resolution_ref"])
        )
        patch = KnowledgePatch.model_validate_json(self._read_ref(item["knowledge_patch_ref"]))
        approval_ref = item.get("approval_ref")
        approval = (
            HumanApproval.model_validate_json(self._read_ref(approval_ref))
            if isinstance(approval_ref, str)
            else None
        )
        return capsule, resolution, patch, approval

    def load_release_request(self, case_id: str) -> KnowledgeReleaseRequest:
        """Load the explicit release request belonging to one frozen case."""

        raw = json.loads(
            self.config.governance.release_activation_requests.read_text(encoding="utf-8")
        )
        item = next(request for request in raw["requests"] if request["case_id"] == case_id)
        return KnowledgeReleaseRequest.model_validate(item)

    def resolve_reference(self, reference: str) -> Path | None:
        """Resolve local synthetic fixture references without network access."""

        prefix = "local://synthetic-m5a/"
        if not reference.startswith(prefix):
            return None
        relative = reference.removeprefix(prefix).split("#", 1)[0]
        if not relative or ".." in Path(relative).parts:
            return None
        path = (self.m5a_root / relative).resolve()
        if not path.is_relative_to(self.m5a_root.resolve()) or not path.is_file():
            return None
        return path

    def _read_ref(self, reference: str) -> str:
        normalized = reference.replace("/evaluation-cases.json", "/evaluation_cases.json")
        path = self.resolve_reference(normalized)
        if path is None:
            raise FileNotFoundError(f"Unresolvable M5A reference: {reference}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _load_relations(path: Path) -> list[ClaimRelation]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [ClaimRelation.model_validate(item) for item in raw["relations"]]

    def _run_regression(self) -> tuple[bool, str, dict[str, dict[str, int]]]:
        if self._regression_result is None:
            self._regression_result = self._regression_gate.run()
        result = self._regression_result
        return (
            result.passed,
            f"in-process regression {result.matched}/{result.expected}",
            result.suites,
        )

    def _run_counterfactual(self, patch: KnowledgePatch) -> tuple[bool, int, str]:
        expectations = self._expectations_for_patch(patch)
        return self._counterfactual_gate.evaluate(patch, expectations)

    def _expectations_for_patch(self, patch: KnowledgePatch) -> list[CounterfactualExpectation]:
        raw = json.loads(
            self.config.governance.overlay_evaluation_cases.read_text(encoding="utf-8")
        )
        case = next(
            item
            for item in raw["cases"]
            if item["patch_ref"].endswith(f"{patch.patch_id.removesuffix('-PATCH')}.patch.json")
        )
        return [
            CounterfactualExpectation(
                query_input=QueryInput(**item["query_input"]),
                decision=Decision(item["expected_decision"]),
            )
            for item in case["queries"]
        ]

    def _previous_release(self, release_id: str) -> tuple[str, str] | None:
        fixture = self.m5a_root / "releases" / f"{release_id}.release.json"
        if not fixture.is_file():
            return None
        raw = json.loads(fixture.read_text(encoding="utf-8"))
        if raw.get("previous_release_id"):
            return str(raw["previous_release_id"]), str(raw["version"])
        return "", str(raw["version"])

    def _record_event(
        self,
        event_type: GovernanceEventType,
        *,
        patch: KnowledgePatch | None = None,
        resolution: ExpertResolution | None = None,
        approval: HumanApproval | None = None,
        release: KnowledgeRelease | None = None,
        previous_status: PatchStatus | None = None,
        new_status: PatchStatus | None = None,
    ) -> None:
        self._event_sequence += 1
        self.event_store.append(
            GovernanceEvent(
                event_id=f"m5b-event-{self._event_sequence:04d}",
                event_type=event_type,
                timestamp_utc=self._event_timestamp_utc or datetime.now(UTC),
                patch_id=patch.patch_id if patch else None,
                resolution_id=resolution.resolution_id if resolution else None,
                approval_id=approval.approval_id if approval else None,
                release_id=release.release_id if release else None,
                previous_status=previous_status,
                new_status=new_status,
            )
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("reference_time_utc must be timezone-aware")
    return value.astimezone(UTC)


def _version_for_request(release_id: str) -> str:
    suffix = release_id.rsplit("-V", 1)[-1]
    return f"{suffix}.0.0" if suffix.isdigit() else "1.0.0"
