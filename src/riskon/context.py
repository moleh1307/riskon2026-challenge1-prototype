"""Small deterministic context detector used before evidence gating."""

from riskon.models import DetectedContext, NeedType, QueryInput


class ContextDetector:
    """Extract structured hints from query text and explicit context fields."""

    def detect(self, request: QueryInput) -> DetectedContext:
        query = request.query.lower()
        supplied = {key.lower(): value.strip() for key, value in request.context.items()}
        region = self._region(query, supplied)
        channel = self._channel(query, supplied)
        workflow_stage = supplied.get("workflow_stage") or self._workflow_stage(query)
        need_type = self._need_type(query, supplied)

        missing_context: list[str] = []
        if "workflow stage" in query and channel is None:
            missing_context.append("channel")
        if supplied.get("workflow_stage") == "missing" and channel is None:
            missing_context.append("channel")

        return DetectedContext(
            region=region,
            channel=channel,
            workflow_stage=workflow_stage,
            need_type=need_type,
            missing_context=list(dict.fromkeys(missing_context)),
        )

    @staticmethod
    def _region(query: str, supplied: dict[str, str]) -> str | None:
        value = supplied.get("region", "").upper().replace(" ", "_")
        if value in {"REGION_ALPHA", "ALPHA"}:
            return "REGION_ALPHA"
        if value in {"REGION_BETA", "BETA"}:
            return "REGION_BETA"
        if "region beta" in query:
            return "REGION_BETA"
        if "region alpha" in query:
            return "REGION_ALPHA"
        return None

    @staticmethod
    def _channel(query: str, supplied: dict[str, str]) -> str | None:
        value = supplied.get("channel", "").lower().replace("-", "_").replace(" ", "_")
        if value in {"interactive_advice", "advice_session", "interactive"}:
            return "INTERACTIVE_ADVICE"
        if value in {"overnight_monitoring", "monitoring", "overnight"}:
            return "OVERNIGHT_MONITORING"
        if "interactive advice" in query or "advice session" in query:
            return "INTERACTIVE_ADVICE"
        if "overnight" in query or "portfolio monitoring" in query:
            return "OVERNIGHT_MONITORING"
        return None

    @staticmethod
    def _workflow_stage(query: str) -> str | None:
        for phrase, value in (
            ("intake", "INTAKE"),
            ("suitability review", "SUITABILITY_REVIEW"),
            ("approval", "APPROVAL"),
            ("post-trade", "POST_TRADE"),
        ):
            if phrase in query:
                return value
        return None

    @staticmethod
    def _need_type(query: str, supplied: dict[str, str]) -> NeedType:
        supplied_need = supplied.get("need_type", "").upper()
        try:
            return NeedType(supplied_need)
        except ValueError:
            pass
        if "network-timeout" in query or "network timeout" in query or "technical failure" in query:
            return NeedType.TECHNICAL_FAILURE
        if "approval" in query or "mandate" in query:
            return NeedType.APPROVAL_REQUIRED
        if "policy interpretation" in query or "interpret the policy" in query:
            return NeedType.POLICY_INTERPRETATION
        if "system guidance" in query:
            return NeedType.SYSTEM_GUIDANCE
        if "routine process" in query:
            return NeedType.ROUTINE_PROCESS
        if "region beta" in query or "complex case" in query:
            return NeedType.COMPLEX_CASE
        return NeedType.UNKNOWN
