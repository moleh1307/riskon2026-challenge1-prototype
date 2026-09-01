"""Deterministic configurable expert routing for M3."""

from datetime import UTC, datetime
from pathlib import Path

from riskon.config import M3RoutingConfig
from riskon.expert_directory import ExpertDirectory, ExpertProfile, NetworkDirectory
from riskon.models import (
    ExpertRoute,
    RouteMode,
    RoutingCandidateDiagnostic,
    RoutingDiagnostics,
    RoutingRequest,
    RoutingStatus,
)
from riskon.routing_explainability import build_explanation
from riskon.support_model import SupportModel


class ExpertRouter:
    """Route only from structured fields and versioned synthetic data."""

    def __init__(
        self,
        support_model: SupportModel,
        directory: ExpertDirectory,
        network: NetworkDirectory,
        config: M3RoutingConfig,
    ) -> None:
        self.support_model = support_model
        self.directory = directory
        self.network = network
        self.config = config
        self.reference_time = _parse_utc(config.reference_time_utc)

    @classmethod
    def from_files(
        cls,
        support_model_path: Path,
        expert_directory_path: Path,
        network_path: Path,
        config: M3RoutingConfig,
    ) -> "ExpertRouter":
        """Load one support-model/profile/network combination."""

        return cls(
            SupportModel.from_file(support_model_path),
            ExpertDirectory.from_file(expert_directory_path),
            NetworkDirectory.from_file(network_path),
            config,
        )

    def route(self, request: RoutingRequest) -> ExpertRoute:
        """Return one deterministic person or functional-queue route."""

        route, _diagnostics = self._route_with_diagnostics(request)
        return route

    def route_with_diagnostics(
        self,
        request: RoutingRequest,
        legacy_route_function: str | None = None,
    ) -> tuple[ExpertRoute | None, RoutingDiagnostics]:
        """Route and optionally enforce legacy support-function consistency."""

        route, diagnostics = self._route_with_diagnostics(request)
        diagnostics.legacy_route_function = legacy_route_function
        if legacy_route_function is not None and route.support_function != legacy_route_function:
            diagnostics.status = RoutingStatus.BLOCKED
            diagnostics.reason_codes = ["LEGACY_ROUTE_CONFLICT"]
            diagnostics.explanation = route.explanation
            return None, diagnostics
        return route, diagnostics

    def _route_with_diagnostics(
        self,
        request: RoutingRequest,
    ) -> tuple[ExpertRoute, RoutingDiagnostics]:
        support_function = self.support_model.resolve(request)
        if support_function is None:
            explanation = build_explanation(
                request,
                "UNMAPPED_SUPPORT_FUNCTION",
                [],
                route_mode=RouteMode.FUNCTIONAL_QUEUE,
                fallback_reason="NO_SUPPORT_MODEL_RULE",
            )
            route = ExpertRoute(
                support_function="UNMAPPED_SUPPORT_FUNCTION",
                route_mode=RouteMode.FUNCTIONAL_QUEUE,
                selected_expert_id=None,
                queue_id=None,
                candidate_expert_ids=[],
                routing_confidence=self.config.functional_queue_confidence,
                confidence_kind=self.config.confidence_kind,
                support_model_version=self.support_model.support_model_version,
                expected_fallback_reason="NO_SUPPORT_MODEL_RULE",
                explanation=explanation,
            )
            return route, RoutingDiagnostics(
                status=RoutingStatus.ROUTED,
                routing_request=request,
                support_function=route.support_function,
                support_model_version=route.support_model_version,
                route_mode=route.route_mode,
                reason_codes=["NO_SUPPORT_MODEL_RULE"],
                explanation=explanation,
            )

        candidates = [
            self._candidate(profile, request, support_function)
            for profile in self.directory.profiles
        ]
        eligible = [item for item in candidates if item.eligible]
        eligible.sort(
            key=lambda item: (
                -(item.total_score or 0.0),
                -item.mandate_specificity,
                item.expert_id,
            )
        )
        for rank, item in enumerate(eligible, start=1):
            item.rank = rank
        ordered = eligible[: self.config.top_k]
        top = ordered[0] if ordered else None
        queue_id = self.directory.queue_for_support_function(support_function)
        fallback_reason: str | None = None
        route_mode = RouteMode.FUNCTIONAL_QUEUE
        selected_expert_id: str | None = None
        routing_confidence = self.config.functional_queue_confidence
        if top is None:
            fallback_reason = "NO_ELIGIBLE_CANDIDATE"
        else:
            second_score = ordered[1].total_score if len(ordered) > 1 else None
            top_score = top.total_score or 0.0
            margin = top_score if second_score is None else top_score - (second_score or 0.0)
            person_allowed = top_score >= self.config.person_min_score and (
                len(ordered) == 1 or margin >= self.config.person_min_margin
            )
            if person_allowed:
                route_mode = RouteMode.PERSON
                selected_expert_id = top.expert_id
                queue_id = self.directory.queue_for_expert_id(top.expert_id)
                margin_component = min(1.0, margin / 0.25)
                routing_confidence = round(
                    0.70 * top_score + 0.30 * margin_component,
                    3,
                )
            else:
                fallback_reason = "LOW_SCORE_OR_MARGIN"

        explanation = build_explanation(
            request,
            support_function,
            candidates,
            route_mode=route_mode,
            fallback_reason=fallback_reason,
        )
        route = ExpertRoute(
            support_function=support_function,
            route_mode=route_mode,
            selected_expert_id=selected_expert_id,
            queue_id=queue_id,
            candidate_expert_ids=[item.expert_id for item in ordered],
            routing_confidence=routing_confidence,
            confidence_kind=self.config.confidence_kind,
            support_model_version=self.support_model.support_model_version,
            expected_fallback_reason=fallback_reason,
            explanation=explanation,
        )
        diagnostics = RoutingDiagnostics(
            status=RoutingStatus.ROUTED,
            routing_request=request,
            support_function=support_function,
            support_model_version=self.support_model.support_model_version,
            route_mode=route_mode,
            selected_expert_id=selected_expert_id,
            reason_codes=[fallback_reason] if fallback_reason else [],
            candidates=sorted(candidates, key=lambda item: item.expert_id),
            explanation=explanation,
        )
        return route, diagnostics

    def _candidate(
        self,
        profile: ExpertProfile,
        request: RoutingRequest,
        support_function: str,
    ) -> RoutingCandidateDiagnostic:
        exclusion_reason = self._exclusion_reason(profile, request, support_function)
        if exclusion_reason is not None:
            return RoutingCandidateDiagnostic(
                expert_id=profile.expert_id,
                eligible=False,
                exclusion_reason=exclusion_reason,
                mandate_specificity=profile.mandate_specificity,
            )
        component_scores = self._component_scores(profile, request)
        total_score = self._weighted_score(component_scores)
        return RoutingCandidateDiagnostic(
            expert_id=profile.expert_id,
            eligible=True,
            component_scores=component_scores,
            total_score=total_score,
            mandate_specificity=profile.mandate_specificity,
        )

    def _exclusion_reason(
        self,
        profile: ExpertProfile,
        request: RoutingRequest,
        support_function: str,
    ) -> str | None:
        if not profile.active:
            return "INACTIVE_PROFILE"
        if not (
            _parse_utc(profile.effective_from)
            <= self.reference_time
            <= _parse_utc(profile.effective_to)
        ):
            return "OUTSIDE_EFFECTIVE_WINDOW"
        if profile.support_function != support_function:
            return "FUNCTION_MISMATCH"
        if request.need_type.value not in profile.mandates:
            return "MANDATE_MISMATCH"
        if request.jurisdiction and not _covers(profile.jurisdictions, request.jurisdiction):
            return "JURISDICTION_CONFLICT"
        if request.region and not _covers(profile.regions, request.region):
            return "REGION_CONFLICT"
        if request.system and not _covers(profile.systems, request.system):
            return "SYSTEM_CONFLICT"
        if not profile.accepting_new_cases:
            return "NOT_ACCEPTING_CASES"
        return None

    def _component_scores(
        self,
        profile: ExpertProfile,
        request: RoutingRequest,
    ) -> dict[str, float]:
        scores: dict[str, float] = {}
        requested_topics = {topic.strip().lower() for topic in request.topics if topic.strip()}
        if requested_topics:
            profile_topics = {topic.strip().lower() for topic in profile.topics}
            scores["expertise_match"] = len(requested_topics & profile_topics) / len(
                requested_topics
            )
        context_values: list[float] = []
        if request.jurisdiction:
            context_values.append(1.0 if request.jurisdiction in profile.jurisdictions else 0.75)
        if request.region:
            context_values.append(1.0 if request.region in profile.regions else 0.75)
        if context_values:
            scores["context_specificity"] = min(context_values)
        if request.system:
            scores["system_match"] = 1.0 if request.system in profile.systems else 0.75
        if request.requester_team:
            scores["network_proximity"] = self.network.weight(
                request.requester_team,
                profile.network_node,
            )
        scores["capacity_score"] = 1.0 - profile.workload_ratio
        return scores

    def _weighted_score(self, component_scores: dict[str, float]) -> float:
        weights = {
            "expertise_match": self.config.weights.expertise_match,
            "context_specificity": self.config.weights.context_specificity,
            "system_match": self.config.weights.system_match,
            "network_proximity": self.config.weights.network_proximity,
            "capacity_score": self.config.weights.capacity_score,
        }
        applicable = {name: weight for name, weight in weights.items() if name in component_scores}
        denominator = (
            sum(applicable.values()) if self.config.renormalize_applicable_weights else 1.0
        )
        return (
            sum(component_scores[name] * weight for name, weight in applicable.items())
            / denominator
        )


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def _covers(values: list[str], requested: str) -> bool:
    return requested in values or "GLOBAL" in values or "*" in values
