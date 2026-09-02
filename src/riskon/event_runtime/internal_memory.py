"""Small, local memory and feedback layer for the event assistant.

This module deliberately stores compact signals instead of transcripts.  It is an
optional context layer: it never becomes source evidence, never changes the
deterministic firewall decision, and can be replaced by a structured LLM patcher
without changing the API contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

DEPARTMENTS: tuple[str, ...] = (
    "Compliance",
    "Risk Management",
    "Wealth Management",
    "Investment Advisory",
    "Operations",
    "Technology",
    "Legal",
    "Front Office",
    "Other",
)

_STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "and",
        "are",
        "can",
        "does",
        "during",
        "for",
        "from",
        "how",
        "into",
        "is",
        "mean",
        "only",
        "that",
        "the",
        "these",
        "this",
        "too",
        "what",
        "when",
        "which",
        "with",
        "would",
        "your",
    }
)


class FeedbackRating(StrEnum):
    """The three feedback signals exposed by the UI."""

    UP = "up"
    NEUTRAL = "neutral"
    DOWN = "down"


class SharedMemoryEntry(BaseModel):
    """One bounded, non-transcript company-memory item."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=420)
    topics: list[str] = Field(default_factory=list, max_length=8)
    departments: list[str] = Field(default_factory=list, max_length=4)
    negative_words: list[str] = Field(default_factory=list, max_length=8)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    origin: Literal["conversation_signal", "feedback_signal", "llm_patch"] = "conversation_signal"
    updated_at: datetime
    use_count: int = Field(default=0, ge=0)


class ConversationMemory(BaseModel):
    """Compact context retained only for the current conversation."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=120)
    department: str | None = Field(default=None, max_length=80)
    summary: str = Field(default="", max_length=700)
    topics: list[str] = Field(default_factory=list, max_length=8)
    last_decision: str = Field(default="", max_length=24)
    turn_count: int = Field(default=0, ge=0)
    updated_at: datetime


class MemoryContext(BaseModel):
    """Bounded context that may be passed to an LLM prompt."""

    model_config = ConfigDict(extra="forbid")

    department: str | None = None
    conversation: ConversationMemory | None = None
    relevant_shared_memory: list[SharedMemoryEntry] = Field(default_factory=list, max_length=6)
    soft_negative_words: list[str] = Field(default_factory=list, max_length=12)


class MemoryPatch(BaseModel):
    """Strict patch shape for an optional structured memory manager."""

    model_config = ConfigDict(extra="forbid")

    should_store: bool = False
    summary: str = Field(default="", max_length=420)
    topics: list[str] = Field(default_factory=list, max_length=8)
    departments: list[str] = Field(default_factory=list, max_length=4)
    negative_words: list[str] = Field(default_factory=list, max_length=8)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class FeedbackReview(BaseModel):
    """Intermediate interpretation of feedback; it is not an answer decision."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["reinforce", "monitor", "update_style_signal", "no_change"]
    rationale: str = Field(min_length=1, max_length=240)
    negative_words: list[str] = Field(default_factory=list, max_length=8)


class FeedbackRecord(BaseModel):
    """Auditable feedback metadata without storing the answer or source text."""

    model_config = ConfigDict(extra="forbid")

    feedback_id: str = Field(min_length=1, max_length=120)
    conversation_id: str = Field(min_length=1, max_length=120)
    turn_id: str = Field(min_length=1, max_length=120)
    rating: FeedbackRating
    department: str | None = Field(default=None, max_length=80)
    decision: str = Field(default="UNKNOWN", max_length=24)
    note: str = Field(default="", max_length=240)
    review: FeedbackReview
    created_at: datetime


class MemorySnapshot(BaseModel):
    """Read-only view of the bounded memory store for the local UI."""

    model_config = ConfigDict(extra="forbid")

    shared_memory: list[SharedMemoryEntry] = Field(default_factory=list)
    conversations: list[ConversationMemory] = Field(default_factory=list)
    feedback: list[FeedbackRecord] = Field(default_factory=list)
    shared_memory_capacity: int = Field(ge=0)
    conversation_capacity: int = Field(ge=0)
    feedback_capacity: int = Field(ge=0)


class MemoryLLMClient(Protocol):
    """Minimal optional adapter for a fixed-policy structured memory model."""

    def request_json(
        self,
        phase: Any,
        response_model: type[BaseModel],
        *,
        developer_prompt: str,
        user_prompt: str,
    ) -> tuple[BaseModel, Any]:
        """Return one validated structured memory response."""


class FeedbackAgent:
    """Interpret feedback conservatively before it can affect soft memory."""

    def review(self, rating: FeedbackRating, note: str | None = None) -> FeedbackReview:
        """Treat a bare thumbs-down as a signal to monitor, not proof of failure."""

        terms = _topic_tokens(note or "")[:8]
        if rating is FeedbackRating.UP:
            return FeedbackReview(
                action="reinforce",
                rationale=(
                    "Positive feedback is a weak signal; no source or firewall change is made."
                ),
            )
        if rating is FeedbackRating.NEUTRAL:
            return FeedbackReview(
                action="no_change",
                rationale="Neutral feedback is recorded without changing memory or answer policy.",
            )
        if terms:
            return FeedbackReview(
                action="update_style_signal",
                rationale="The optional note supplies a soft style signal for future responses.",
                negative_words=terms,
            )
        return FeedbackReview(
            action="monitor",
            rationale=(
                "A bare negative signal is monitored because it does not prove the answer is wrong."
            ),
        )


class MemoryAgent:
    """Bounded memory coordinator with an optional structured-LLM hook.

    The default path is fully local and deterministic.  If a fixed-policy client is
    injected later, it can propose a ``MemoryPatch``; the store still bounds and
    sanitises the result before persistence.
    """

    def __init__(self, client: MemoryLLMClient | None = None) -> None:
        self.client = client
        self.feedback_agent = FeedbackAgent()

    def record_turn(
        self,
        store: InternalMemoryStore,
        *,
        conversation_id: str,
        department: str | None,
        question: str,
        decision: str,
    ) -> None:
        """Keep a compact conversation signal and promote only repeated topics."""

        store.record_turn(
            conversation_id=conversation_id,
            department=department,
            question=question,
            decision=decision,
        )
        if self.client is None:
            return
        try:
            patch, _ = self.client.request_json(
                "memory_manager",
                MemoryPatch,
                developer_prompt=(
                    "You manage a tiny internal memory. Extract only durable, non-sensitive "
                    "context variables from the supplied turn. Never store a transcript, answer, "
                    "source text, citation, or secret. Return only the requested schema."
                ),
                user_prompt=json.dumps(
                    {
                        "question": question,
                        "department": department,
                        "decision": decision,
                        "existing_context": store.prompt_context(
                            question, conversation_id, department
                        ),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            if isinstance(patch, MemoryPatch):
                store.apply_patch(patch, origin="llm_patch")
        except Exception:
            # Memory enrichment is optional.  A transient model failure must not
            # affect the source-backed answer already released by the firewall.
            return

    def review_feedback(
        self,
        store: InternalMemoryStore,
        *,
        conversation_id: str,
        turn_id: str,
        rating: FeedbackRating,
        department: str | None,
        decision: str,
        note: str | None,
    ) -> FeedbackRecord:
        """Record feedback and apply only the bounded review outcome."""

        review = self.feedback_agent.review(rating, note)
        if self.client is not None and rating is FeedbackRating.DOWN and note:
            try:
                output, _ = self.client.request_json(
                    "feedback_reviewer",
                    FeedbackReview,
                    developer_prompt=(
                        "Interpret user feedback conservatively. It is not proof that an answer "
                        "is wrong and it cannot change evidence, citations, or the firewall. "
                        "Return only the requested schema."
                    ),
                    user_prompt=json.dumps(
                        {
                            "rating": rating.value,
                            "note": note,
                            "department": department,
                            "decision": decision,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                if isinstance(output, FeedbackReview):
                    review = _safe_review(output)
            except Exception:
                pass
        return store.record_feedback(
            conversation_id=conversation_id,
            turn_id=turn_id,
            rating=rating,
            department=department,
            decision=decision,
            note=note,
            review=review,
        )


class InternalMemoryStore:
    """Process-local, file-backed and size-bounded memory store."""

    def __init__(
        self,
        root: Path,
        *,
        max_entries: int = 64,
        max_conversations: int = 128,
        max_feedback: int = 200,
    ) -> None:
        self.root = root
        self.max_entries = max_entries
        self.max_conversations = max_conversations
        self.max_feedback = max_feedback
        self._memory_path = root / "shared_memory.json"
        self._conversation_path = root / "conversation_context.json"
        self._feedback_path = root / "feedback.jsonl"
        self._lock = RLock()
        self._memories = self._load_memories()
        self._conversations = self._load_conversations()
        self._feedback = self._load_feedback()

    def prompt_context(
        self,
        question: str,
        conversation_id: str,
        department: str | None,
    ) -> str:
        """Return only relevant, bounded context for a downstream LLM prompt."""

        return self.relevant_context(question, conversation_id, department).model_dump_json(
            exclude_none=True
        )

    def snapshot(self) -> MemorySnapshot:
        """Return a stable, read-only snapshot without recording a new lookup."""

        with self._lock:
            memories = sorted(
                self._memories.values(),
                key=lambda item: (item.importance, item.updated_at, item.memory_id),
                reverse=True,
            )
            conversations = sorted(
                self._conversations.values(),
                key=lambda item: (item.updated_at, item.conversation_id),
                reverse=True,
            )
            return MemorySnapshot(
                shared_memory=[item.model_copy(deep=True) for item in memories],
                conversations=[item.model_copy(deep=True) for item in conversations],
                feedback=[item.model_copy(deep=True) for item in self._feedback],
                shared_memory_capacity=self.max_entries,
                conversation_capacity=self.max_conversations,
                feedback_capacity=self.max_feedback,
            )

    def relevant_context(
        self,
        question: str,
        conversation_id: str,
        department: str | None,
    ) -> MemoryContext:
        """Select by topic and department instead of sending the whole memory."""

        terms = set(_topic_tokens(question))
        with self._lock:
            conversation = self._conversations.get(conversation_id)
            scored: list[tuple[float, str, SharedMemoryEntry]] = []
            for memory_id, entry in self._memories.items():
                topic_overlap = len(terms & set(entry.topics))
                department_match = bool(
                    department
                    and department.casefold() in {item.casefold() for item in entry.departments}
                )
                score = float(topic_overlap) + (2.0 if department_match else 0.0)
                if score > 0:
                    scored.append((score + entry.importance * 0.1, memory_id, entry))
            scored.sort(key=lambda item: (-item[0], item[1]))
            selected = [
                item[2].model_copy(update={"use_count": item[2].use_count + 1})
                for item in scored[:6]
            ]
            for entry in selected:
                if entry.memory_id in self._memories:
                    self._memories[entry.memory_id] = entry
            negative_entries = sorted(
                (
                    entry
                    for entry in self._memories.values()
                    if entry.negative_words
                    and (
                        not entry.departments
                        or (
                            department is not None
                            and department.casefold()
                            in {item.casefold() for item in entry.departments}
                        )
                    )
                ),
                key=lambda item: (-item.importance, item.memory_id),
            )
            negative_words = _dedupe(
                word
                for entry in [*selected, *negative_entries]
                for word in entry.negative_words
                if word
            )[:12]
            return MemoryContext(
                department=department,
                conversation=conversation,
                relevant_shared_memory=selected,
                soft_negative_words=negative_words,
            )

    def record_turn(
        self,
        *,
        conversation_id: str,
        department: str | None,
        question: str,
        decision: str,
    ) -> None:
        """Persist topic-level context, never the raw question or answer."""

        clean_department = normalize_department(department)
        topics = _topic_tokens(question)[:8]
        now = _now()
        with self._lock:
            previous = self._conversations.get(conversation_id)
            merged_topics = _dedupe([*(previous.topics if previous else []), *topics])[:8]
            summary_parts = []
            if merged_topics:
                summary_parts.append("Topics: " + ", ".join(merged_topics[:6]))
            if clean_department:
                summary_parts.append("Department: " + clean_department)
            summary_parts.append("Last outcome: " + decision)
            conversation = ConversationMemory(
                conversation_id=conversation_id,
                department=clean_department or (previous.department if previous else None),
                summary=". ".join(summary_parts)[:700],
                topics=merged_topics,
                last_decision=decision,
                turn_count=(previous.turn_count if previous else 0) + 1,
                updated_at=now,
            )
            self._conversations[conversation_id] = conversation
            self._trim_conversations()
            self._write_json(self._conversation_path, list(self._conversations.values()))

            # Promote topic signals only after they recur in one conversation.  This
            # is the small cross-chat memory; individual Q&A turns stay ephemeral.
            if previous is not None and topics:
                repeated = [topic for topic in topics if topic in previous.topics]
                if repeated:
                    patch = MemoryPatch(
                        should_store=True,
                        summary="Recurring context: " + ", ".join(repeated[:6]),
                        topics=repeated[:8],
                        departments=[clean_department] if clean_department else [],
                        importance=0.55,
                    )
                    self.apply_patch(patch, origin="conversation_signal", persist=False)
                    self._write_json(self._memory_path, list(self._memories.values()))

    def record_feedback(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        rating: FeedbackRating,
        department: str | None,
        decision: str,
        note: str | None,
        review: FeedbackReview,
    ) -> FeedbackRecord:
        """Persist feedback and turn an explicit note into a soft style signal only."""

        clean_note = " ".join((note or "").split())[:240]
        record = FeedbackRecord(
            feedback_id=_id("feedback"),
            conversation_id=conversation_id,
            turn_id=turn_id,
            rating=rating,
            department=normalize_department(department),
            decision=decision[:24],
            note=clean_note,
            review=review,
            created_at=_now(),
        )
        with self._lock:
            self._feedback.append(record)
            self._feedback = self._feedback[-self.max_feedback :]
            self._append_feedback(record)
            if review.negative_words:
                self.apply_patch(
                    MemoryPatch(
                        should_store=True,
                        summary="Soft response-style signal from feedback",
                        topics=review.negative_words[:8],
                        departments=[record.department] if record.department else [],
                        negative_words=review.negative_words[:8],
                        importance=0.35,
                    ),
                    origin="feedback_signal",
                )
        return record

    def apply_patch(
        self,
        patch: MemoryPatch,
        *,
        origin: Literal["conversation_signal", "feedback_signal", "llm_patch"] = "llm_patch",
        persist: bool = True,
    ) -> None:
        """Validate, merge, and cap a proposed memory update."""

        if not patch.should_store or not patch.summary.strip():
            return
        topics = _dedupe(_topic_tokens(" ".join(patch.topics)))[:8]
        negative_words = _dedupe(_topic_tokens(" ".join(patch.negative_words)))[:8]
        departments = _dedupe(normalize_department(value) or "" for value in patch.departments)[:4]
        summary = " ".join(patch.summary.split())[:420]
        key_material = "|".join([summary.casefold(), *topics, *departments, *negative_words])
        memory_id = "memory:" + hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:20]
        now = _now()
        with self._lock:
            current = self._memories.get(memory_id)
            self._memories[memory_id] = SharedMemoryEntry(
                memory_id=memory_id,
                summary=summary,
                topics=topics,
                departments=departments,
                negative_words=negative_words,
                importance=max(patch.importance, current.importance if current else 0.0),
                origin=origin,
                updated_at=now,
                use_count=current.use_count if current else 0,
            )
            self._trim_memories()
            if persist:
                self._write_json(self._memory_path, list(self._memories.values()))

    def _trim_memories(self) -> None:
        ordered = sorted(
            self._memories.values(),
            key=lambda item: (item.importance, item.updated_at, item.memory_id),
            reverse=True,
        )[: self.max_entries]
        self._memories = {item.memory_id: item for item in ordered}

    def _trim_conversations(self) -> None:
        ordered = sorted(
            self._conversations.values(),
            key=lambda item: (item.updated_at, item.conversation_id),
            reverse=True,
        )[: self.max_conversations]
        self._conversations = {item.conversation_id: item for item in ordered}

    def _load_memories(self) -> dict[str, SharedMemoryEntry]:
        raw = self._read_json(self._memory_path)
        if not isinstance(raw, list):
            return {}
        result: dict[str, SharedMemoryEntry] = {}
        for item in raw:
            try:
                entry = SharedMemoryEntry.model_validate(item)
            except (TypeError, ValueError):
                continue
            result[entry.memory_id] = entry
        return result

    def _load_conversations(self) -> dict[str, ConversationMemory]:
        raw = self._read_json(self._conversation_path)
        if not isinstance(raw, list):
            return {}
        result: dict[str, ConversationMemory] = {}
        for item in raw:
            try:
                entry = ConversationMemory.model_validate(item)
            except (TypeError, ValueError):
                continue
            result[entry.conversation_id] = entry
        return result

    def _load_feedback(self) -> list[FeedbackRecord]:
        if not self._feedback_path.is_file():
            return []
        result: list[FeedbackRecord] = []
        try:
            lines = self._feedback_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return result
        for line in lines[-self.max_feedback :]:
            try:
                result.append(FeedbackRecord.model_validate(json.loads(line)))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return result

    @staticmethod
    def _read_json(path: Path) -> object:
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        except (OSError, json.JSONDecodeError):
            return None

    def _write_json(self, path: Path, value: object) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps(_jsonable(value), ensure_ascii=False, indent=2) + "\n")

    def _append_feedback(self, record: FeedbackRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            record.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
        )
        with self._feedback_path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        lines = self._feedback_path.read_text(encoding="utf-8").splitlines()
        if len(lines) > self.max_feedback:
            _atomic_write(self._feedback_path, "\n".join(lines[-self.max_feedback :]) + "\n")


def normalize_department(value: str | None) -> str | None:
    """Normalise the fixed UI department vocabulary."""

    if value is None or not value.strip():
        return None
    clean = " ".join(value.split())
    for department in DEPARTMENTS:
        if department.casefold() == clean.casefold():
            return department
    raise ValueError("department must be one of the fixed RiskON department values")


def _safe_review(review: FeedbackReview) -> FeedbackReview:
    """Constrain model-proposed style signals to the same local token policy."""

    words = _topic_tokens(" ".join(review.negative_words))[:8]
    action = review.action
    if action == "update_style_signal" and not words:
        action = "monitor"
    return review.model_copy(update={"action": action, "negative_words": words})


def _topic_tokens(value: str) -> list[str]:
    tokens = re.findall(r"[\w][\w'-]{1,}", value.casefold(), flags=re.UNICODE)
    return _dedupe(token for token in tokens if token not in _STOP_WORDS and len(token) >= 3)


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = str(value).strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def _now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix}:{os.urandom(8).hex()}"


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
