"""Structured, synthetic expert routing policy."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from riskon.models import DetectedContext, NeedType, ReasonCode, Route


class ExpertRecord(BaseModel):
    """Synthetic expert directory record."""

    model_config = ConfigDict(extra="forbid")

    expert_id: str
    display_name: str
    support_function: str
    jurisdiction: str | None = None
    need_types: list[str]


class RoutingRule(BaseModel):
    """One ordered rule from routing_policy.json."""

    model_config = ConfigDict(extra="forbid")

    priority: int
    reason_code: str | None = None
    need_type: str | None = None
    fallback: bool = False
    support_function: str


class ExpertRouter:
    """Route only from structured need/reason/region values."""

    def __init__(self, experts: list[ExpertRecord], rules: list[RoutingRule]) -> None:
        self.experts = experts
        self.rules = sorted(rules, key=lambda rule: rule.priority)

    @classmethod
    def from_files(cls, experts_path: Path, policy_path: Path) -> "ExpertRouter":
        experts_raw = json.loads(experts_path.read_text(encoding="utf-8"))
        policy_raw = json.loads(policy_path.read_text(encoding="utf-8"))
        experts = [ExpertRecord.model_validate(item) for item in experts_raw]
        rules = [RoutingRule.model_validate(item) for item in policy_raw]
        return cls(experts=experts, rules=rules)

    def route(self, context: DetectedContext, reason_codes: list[ReasonCode]) -> Route:
        reason_values = {reason.value for reason in reason_codes}
        special_route = self._m1_route(context, reason_values)
        if special_route is not None:
            return special_route
        for rule in self.rules:
            if rule.fallback:
                continue
            reason_match = rule.reason_code is not None and rule.reason_code in reason_values
            need_match = rule.need_type is not None and rule.need_type == context.need_type.value
            if not (reason_match or need_match):
                continue
            expert = self._find_expert(rule.support_function, context)
            if expert is not None:
                return Route(
                    support_function=expert.support_function,
                    expert_id=expert.expert_id,
                    routing_reason=self._reason(rule, context, expert.display_name),
                    routing_confidence=1.0,
                )
            return Route(
                support_function=rule.support_function,
                expert_id=None,
                routing_reason=self._reason(rule, context, "functional queue"),
                routing_confidence=0.5,
            )

        fallback = next((rule for rule in self.rules if rule.fallback), None)
        if fallback is None:
            return Route(
                support_function="BRM_SUITABILITY_LEAD",
                expert_id=None,
                routing_reason="No exact structured route; functional fallback queue",
                routing_confidence=0.5,
            )
        return Route(
            support_function=fallback.support_function,
            expert_id=None,
            routing_reason="No exact structured route; functional fallback queue",
            routing_confidence=0.5,
        )

    def _m1_route(self, context: DetectedContext, reason_values: set[str]) -> Route | None:
        """Handle M1 evidence-gate reasons without changing the M0 policy file."""

        special: dict[str, str] = {
            "NO_EXPLICIT_SUPPORT": "SUITABILITY_EXPERT_LEGAL",
            "UNRESOLVED_REQUIRED_REFERENCE": "BUSINESS_FRONT_SUPPORT",
            "UNSUPPORTED_MODALITY": "BRM_SUITABILITY_LEAD",
            "APPROVAL_REQUIRED": "SUITABILITY_EXPERT_COMPLIANCE",
        }
        matched = next((reason for reason in special if reason in reason_values), None)
        if matched is None:
            return None
        support_function = special[matched]
        expert = self._find_expert(support_function, context)
        return Route(
            support_function=support_function,
            expert_id=expert.expert_id if expert else None,
            routing_reason=f"Structured M1 selector {matched} matched {support_function}",
            routing_confidence=1.0 if expert else 0.5,
        )

    def _find_expert(self, support_function: str, context: DetectedContext) -> ExpertRecord | None:
        candidates = [
            expert for expert in self.experts if expert.support_function == support_function
        ]
        if support_function == "BRM_SUITABILITY_LEAD":
            if context.region is None:
                return None
            candidates = [expert for expert in candidates if expert.jurisdiction == context.region]
        for expert in candidates:
            if (
                context.need_type is NeedType.UNKNOWN
                or context.need_type.value in expert.need_types
            ):
                return expert
        return candidates[0] if candidates else None

    @staticmethod
    def _reason(rule: RoutingRule, context: DetectedContext, target: str) -> str:
        selector = rule.reason_code or rule.need_type or "fallback"
        jurisdiction = f" for {context.region}" if context.region else ""
        return f"Structured selector {selector}{jurisdiction} matched {target}"
