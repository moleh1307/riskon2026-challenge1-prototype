"""Append-only governance event storage."""

from pathlib import Path

import pytest
from m5b_helpers import REFERENCE_TIME

from riskon.governance.event_store import GovernanceEventStore
from riskon.governance.models import GovernanceEvent, GovernanceEventType, PatchStatus


def event(
    event_id: str, event_type: GovernanceEventType = GovernanceEventType.PATCH_PROPOSED
) -> GovernanceEvent:
    return GovernanceEvent(
        event_id=event_id,
        event_type=event_type,
        timestamp_utc=REFERENCE_TIME,
        patch_id="patch-1",
        previous_status=None,
        new_status=PatchStatus.PROPOSED,
    )


def test_empty_event_store_loads_without_creating_file(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    store = GovernanceEventStore(path)
    assert store.events == ()
    assert path.exists() is False


def test_append_persists_and_reload_preserves_order(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "events.jsonl"
    store = GovernanceEventStore(path)
    first = event("event-1")
    second = event("event-2", GovernanceEventType.POLICY_CI_COMPLETED)
    store.append(first)
    store.append_many([second])
    reloaded = GovernanceEventStore(path)
    assert reloaded.events == (first, second)
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_duplicate_event_ids_are_rejected_without_mutating_store(tmp_path: Path) -> None:
    store = GovernanceEventStore(tmp_path / "events.jsonl")
    item = event("same")
    store.append(item)
    with pytest.raises(ValueError, match="Duplicate"):
        store.append(item)
    assert len(store.events) == 1


def test_custom_allowed_event_type_set_is_enforced(tmp_path: Path) -> None:
    store = GovernanceEventStore(
        tmp_path / "events.jsonl",
        allowed_event_types={GovernanceEventType.PATCH_PROPOSED},
    )
    with pytest.raises(ValueError, match="Unsupported"):
        store.append(event("event", GovernanceEventType.RELEASE_CREATED))


def test_append_many_stops_at_invalid_event_and_keeps_previous_rows(tmp_path: Path) -> None:
    store = GovernanceEventStore(tmp_path / "events.jsonl")
    store.append(event("first"))
    with pytest.raises(ValueError):
        store.append_many([event("second"), event("first")])
    assert [item.event_id for item in store.events] == ["first", "second"]


def test_event_view_is_tuple_and_event_is_immutable(tmp_path: Path) -> None:
    store = GovernanceEventStore(tmp_path / "events.jsonl")
    item = event("event")
    store.append(item)
    assert isinstance(store.events, tuple)
    with pytest.raises(ValueError):
        item.reason_codes = ["changed"]


def test_existing_malformed_jsonl_is_rejected_on_load(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError):
        GovernanceEventStore(path)
