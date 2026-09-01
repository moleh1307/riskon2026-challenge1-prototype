"""Append-only JSONL governance event storage."""

from __future__ import annotations

import json
from pathlib import Path

from riskon.governance.models import GovernanceEvent, GovernanceEventType


class GovernanceEventStore:
    """Persist safe event metadata without update or delete operations."""

    def __init__(
        self, path: Path, allowed_event_types: set[GovernanceEventType] | None = None
    ) -> None:
        self.path = path
        self.allowed_event_types = allowed_event_types or set(GovernanceEventType)
        self._events: list[GovernanceEvent] = self._load()

    @property
    def events(self) -> tuple[GovernanceEvent, ...]:
        """Return the immutable in-memory event view."""

        return tuple(self._events)

    def append(self, event: GovernanceEvent) -> None:
        """Append one unique allowed event and never overwrite history."""

        if event.event_type not in self.allowed_event_types:
            raise ValueError(f"Unsupported governance event type: {event.event_type.value}")
        if any(existing.event_id == event.event_id for existing in self._events):
            raise ValueError(f"Duplicate governance event ID: {event.event_id}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n")
        self._events.append(event)

    def append_many(self, events: list[GovernanceEvent]) -> None:
        """Append events in order through the same validation boundary."""

        for event in events:
            self.append(event)

    def _load(self) -> list[GovernanceEvent]:
        if not self.path.is_file():
            return []
        events: list[GovernanceEvent] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(GovernanceEvent.model_validate_json(line))
        return events
