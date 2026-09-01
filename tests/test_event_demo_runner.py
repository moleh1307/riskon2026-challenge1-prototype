"""ER-B runtime-to-story tests."""

from __future__ import annotations

from riskon.demo.runner import DemoRun


def test_runner_returns_the_five_expected_outcomes(event_demo_run: DemoRun) -> None:
    assert [(story.case_id, story.decision) for story in event_demo_run.stories] == [
        ("ERB-001", "ANSWER"),
        ("ERB-002", "CLARIFY"),
        ("ERB-003", "ANSWER"),
        ("ERB-004", "ABSTAIN"),
        ("ERB-005", "ANSWER"),
    ]


def test_runner_exposes_full_orchestra_and_human_route(event_demo_run: DemoRun) -> None:
    stories = {story.case_id: story for story in event_demo_run.stories}
    full = stories["ERB-003"]
    assert [step.actor for step in full.orchestra_activity if step.stage == "Worker activated"] == [
        "Evidence Scout",
        "Scope Sentinel",
        "Counterfactual Sentinel",
    ]
    assert len(full.counterfactuals) == 3

    routed = stories["ERB-004"]
    assert routed.route is not None
    assert routed.route.support_function == "BUSINESS_FRONT_SUPPORT"
    assert routed.route.queue_id == "QUEUE-BFS-GLOBAL"
    assert routed.case_capsule_id is not None


def test_runner_exposes_governed_evolution(event_demo_run: DemoRun) -> None:
    story = next(item for item in event_demo_run.stories if item.case_id == "ERB-005")
    assert story.governance is not None
    assert story.governance.checks.policy_ci == {"matched": 11, "expected": 11}
    assert story.governance.checks.regression == {"matched": 45, "expected": 45}
    assert story.governance.checks.counterfactual_containment == {
        "matched": 4,
        "expected": 4,
    }
    assert story.governance.checks.automatic_approval == 0
    assert story.governance.checks.automatic_activation == 0
    assert story.governance.checks.human_approval is True
    assert story.governance.checks.release_activation is True
