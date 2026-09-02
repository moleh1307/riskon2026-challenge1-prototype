"""Tests for compact conversation memory and conservative feedback handling."""

from __future__ import annotations

from pathlib import Path

from riskon.event_runtime.internal_memory import (
    FeedbackAgent,
    FeedbackRating,
    InternalMemoryStore,
    MemoryPatch,
)


def test_memory_keeps_topic_context_without_persisting_the_transcript(tmp_path: Path) -> None:
    store = InternalMemoryStore(tmp_path / "memory")
    question = "Which alerts apply for an Advice Premium mandate?"

    store.record_turn(
        conversation_id="conversation-1",
        department="Compliance",
        question=question,
        decision="ANSWER",
    )
    store.record_turn(
        conversation_id="conversation-1",
        department="Compliance",
        question="Which alerts apply for the same Advice Premium mandate?",
        decision="ANSWER",
    )

    context = store.relevant_context(question, "conversation-1", "Compliance")
    assert context.conversation is not None
    assert context.conversation.turn_count == 2
    assert context.relevant_shared_memory
    persisted = (tmp_path / "memory" / "conversation_context.json").read_text(encoding="utf-8")
    assert question not in persisted
    assert "alerts" in persisted


def test_negative_feedback_is_soft_and_bounded(tmp_path: Path) -> None:
    agent = FeedbackAgent()
    assert agent.review(FeedbackRating.DOWN).action == "monitor"
    review = agent.review(FeedbackRating.DOWN, "too technical and too long")
    assert review.action == "update_style_signal"
    assert review.negative_words == ["technical", "long"]

    store = InternalMemoryStore(tmp_path / "memory", max_entries=1)
    store.apply_patch(
        MemoryPatch(
            should_store=True,
            summary="Avoid overly technical explanations",
            topics=["technical"],
            negative_words=review.negative_words,
            importance=0.4,
        ),
        origin="feedback_signal",
    )
    store.apply_patch(
        MemoryPatch(
            should_store=True,
            summary="Prefer concise explanations",
            topics=["concise"],
            importance=0.8,
        ),
        origin="feedback_signal",
    )
    restored = InternalMemoryStore(tmp_path / "memory", max_entries=1)
    context = restored.relevant_context("technical explanation", "new-chat", None)
    assert len(context.relevant_shared_memory) == 0
    assert len(restored._memories) == 1  # bounded storage, not an API contract


def test_feedback_note_becomes_style_metadata_not_answer_evidence(tmp_path: Path) -> None:
    store = InternalMemoryStore(tmp_path / "memory")
    review = FeedbackAgent().review(FeedbackRating.DOWN, "please make the answer less jargon-heavy")
    record = store.record_feedback(
        conversation_id="conversation-1",
        turn_id="turn-1",
        rating=FeedbackRating.DOWN,
        department="Compliance",
        decision="ANSWER",
        note="please make the answer less jargon-heavy",
        review=review,
    )

    assert record.review.action == "update_style_signal"
    prompt_context = store.prompt_context("jargon explanation", "new-chat", "Compliance")
    assert "soft_negative_words" in prompt_context
    assert "evidence_refs" not in prompt_context
