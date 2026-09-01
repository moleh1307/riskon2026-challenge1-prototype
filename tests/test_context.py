"""Context detector tests."""

from riskon.context import ContextDetector
from riskon.models import NeedType, QueryInput


def test_missing_workflow_channel_is_detected() -> None:
    context = ContextDetector().detect(
        QueryInput(query="An alert has no workflow stage; which workflow rule applies?")
    )
    assert context.missing_context == ["channel"]
    assert context.channel is None


def test_channel_and_region_are_detected_from_query_and_structured_input() -> None:
    detector = ContextDetector()
    interactive = detector.detect(
        QueryInput(query="What applies in an interactive advice session?")
    )
    assert interactive.channel == "INTERACTIVE_ADVICE"
    beta = detector.detect(QueryInput(query="Which policy applies?", context={"region": "beta"}))
    assert beta.region == "REGION_BETA"
    monitoring = detector.detect(
        QueryInput(query="Review the overnight portfolio monitoring alert.")
    )
    assert monitoring.channel == "OVERNIGHT_MONITORING"


def test_need_type_detection_is_structured() -> None:
    detector = ContextDetector()
    assert (
        detector.detect(QueryInput(query="technical network-timeout")).need_type
        is NeedType.TECHNICAL_FAILURE
    )
    assert (
        detector.detect(QueryInput(query="policy interpretation request")).need_type
        is NeedType.POLICY_INTERPRETATION
    )
    assert (
        detector.detect(QueryInput(query="approval is required")).need_type
        is NeedType.APPROVAL_REQUIRED
    )
    assert (
        detector.detect(QueryInput(query="system guidance")).need_type is NeedType.SYSTEM_GUIDANCE
    )
    assert (
        detector.detect(QueryInput(query="routine process")).need_type is NeedType.ROUTINE_PROCESS
    )
    assert (
        detector.detect(QueryInput(query="a Region Beta complex case")).need_type
        is NeedType.COMPLEX_CASE
    )
    assert detector.detect(QueryInput(query="plain question")).need_type is NeedType.UNKNOWN


def test_explicit_context_overrides_text_and_workflow_stage_is_preserved() -> None:
    context = ContextDetector().detect(
        QueryInput(
            query="overnight portfolio monitoring",
            context={
                "channel": "interactive_advice",
                "workflow_stage": "suitability review",
                "need_type": "ROUTINE_PROCESS",
            },
        )
    )
    assert context.channel == "INTERACTIVE_ADVICE"
    assert context.workflow_stage == "suitability review"
    assert context.need_type is NeedType.ROUTINE_PROCESS
