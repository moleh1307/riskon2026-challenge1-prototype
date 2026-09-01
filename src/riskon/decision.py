"""Decision engine for the three-state response contract."""

from riskon.models import Decision, EvidenceCheck

CLARIFICATION_BY_CONTEXT = {
    "channel": (
        "Did the alert arise during an interactive advice session or during "
        "overnight portfolio monitoring?"
    ),
}


class DecisionEngine:
    """Map evidence-gate output to ANSWER, CLARIFY, or ABSTAIN."""

    def decide(self, check: EvidenceCheck) -> Decision:
        if check.missing_context:
            return Decision.CLARIFY
        if check.reason_codes:
            return Decision.ABSTAIN
        return Decision.ANSWER

    def clarifying_question(self, check: EvidenceCheck) -> str:
        if not check.missing_context:
            raise ValueError("No clarification is needed")
        field = check.missing_context[0]
        return CLARIFICATION_BY_CONTEXT.get(field, f"Please provide the missing context: {field}.")
