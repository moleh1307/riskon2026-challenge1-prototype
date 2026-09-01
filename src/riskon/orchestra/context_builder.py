"""Safe structured context construction for M4D orchestration."""

from riskon.models import NeedType, PlannedVerifiedRun, QueryInput, RoutingContext
from riskon.orchestra.models import OrchestraContext, RiskAssessment


def build_orchestra_context(
    request: QueryInput,
    baseline: PlannedVerifiedRun,
    assessment: RiskAssessment,
    *,
    default_routing_profile: str = "default",
) -> OrchestraContext:
    """Copy caller-supplied structured fields without copying the raw query."""

    structured_context = {
        key.strip(): value.strip()
        for key, value in request.context.items()
        if key.strip() and value.strip() and key.lower() != "routing_profile"
    }
    routing_profile = request.context.get("routing_profile", default_routing_profile)
    routing_context = None
    if baseline.verified_run.result.decision.value == "ABSTAIN":
        result = baseline.verified_run.result
        supplied_need = request.context.get("routing_need_type") or request.context.get("need_type")
        need_type = result.detected_context.need_type
        if supplied_need:
            need_type = NeedType(supplied_need)
        topics_value = request.context.get("routing_topics") or request.context.get("topics", "")
        topics = [
            item.strip() for item in topics_value.replace("|", ",").split(",") if item.strip()
        ]
        routing_context = RoutingContext(
            need_type=need_type,
            reason_codes=list(result.reason_codes),
            topics=topics,
            jurisdiction=request.context.get("jurisdiction"),
            region=request.context.get("region") or result.detected_context.region,
            system=request.context.get("system"),
            requester_team=request.context.get("requester_team"),
        )
    return OrchestraContext(
        risk_signals=assessment.risk_signals,
        routing_context=routing_context,
        routing_profile=routing_profile,
        structured_context=structured_context,
        requested_agent_roles=(),
    )
