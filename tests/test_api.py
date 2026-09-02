"""Contract checks for Gabriel's adapted chat surface over the canonical runtime."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import riskon.api.app as api
from riskon.event_runtime.internal_memory import InternalMemoryStore, MemoryAgent
from riskon.models import QueryInput
from riskon.orchestra.errors import OrchestraFailClosedError


class _FakePipeline:
    def __init__(self, result: object | None = None, error: Exception | None = None) -> None:
        self.request: QueryInput | None = None
        self.result = result
        self.error = error

    def run_orchestrated(self, request: QueryInput) -> object:
        self.request = request
        if self.error is not None:
            raise self.error
        return self.result


def test_ui_is_served_with_canonical_contract_labels() -> None:
    page = api.index()

    assert "RiskON Assistant" in page
    assert 'fetch("/v1/ask"' in page
    assert 'fetch("/v1/feedback"' in page
    assert 'href="/memory"' in page
    assert 'id="department"' in page
    assert "res.decision" in page
    assert "evidence_refs" in page


def test_memory_page_and_view_are_read_only_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = InternalMemoryStore(tmp_path / "memory")
    store.record_turn(
        conversation_id="private-conversation",
        department="Compliance",
        question="Which alerts apply?",
        decision="ANSWER",
    )
    monkeypatch.setattr(api.state, "memory", store)

    page = api.memory_page()
    response = api.memory_view()

    assert "Memory summary" in page
    assert 'fetch("/v1/memory"' in page
    payload = response.model_dump_json()
    assert "private-conversation" not in payload
    assert "Which alerts apply?" not in payload
    assert response.items == []
    assert response.count == 0
    assert response.capacity == 64


def test_health_reports_runtime_readiness_without_source_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api.state, "pipeline", None)

    response = api.health()

    assert response.status == "not_ready"
    assert response.runtime_loaded is False
    assert "source_root" not in response.model_dump_json()


def test_ask_forwards_structured_context_and_safe_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _FakePipeline(result=object())
    monkeypatch.setattr(api.state, "pipeline", fake)
    monkeypatch.setattr(api.state, "memory", InternalMemoryStore(tmp_path / "memory"))
    monkeypatch.setattr(api.state, "memory_agent", MemoryAgent())
    monkeypatch.setattr(
        api,
        "query_result_payload",
        lambda _: {
            "decision": "ANSWER",
            "answer": "Use the declared source.",
            "clarification": None,
            "abstention_reason": [],
            "evidence_refs": ["local://event-wiki/page#table-1"],
            "route": None,
            "activation_profile": "FAST_PATH",
            "worker_roles": [],
            "worker_execution_count": 0,
        },
    )

    response = api.ask(
        api.AskRequest(
            question="What applies?",
            context={"region": "CH"},
            conversation_id="conversation-1",
            department="Compliance",
        )
    )

    assert fake.request is not None
    assert fake.request.query == "What applies?"
    assert fake.request.context["region"] == "CH"
    assert fake.request.context["department"] == "Compliance"
    assert "_riskon_memory_context" in fake.request.context
    assert fake.request.trace_id == response.turn_id
    assert response.conversation_id == "conversation-1"
    assert response.result.decision == "ANSWER"
    assert response.result.evidence_refs == ["local://event-wiki/page#table-1"]


def test_feedback_is_reviewed_before_a_soft_memory_update(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api.state, "memory", InternalMemoryStore(tmp_path / "memory"))
    monkeypatch.setattr(api.state, "memory_agent", MemoryAgent())

    response = api.feedback(
        api.FeedbackRequest(
            conversation_id="conversation-1",
            turn_id="turn-1",
            rating="down",
            department="Compliance",
            decision="ANSWER",
            note="too technical",
        )
    )

    assert response.accepted is True
    assert response.action == "update_style_signal"
    saved = (tmp_path / "memory" / "shared_memory.json").read_text(encoding="utf-8")
    assert "technical" in saved
    assert "negative_words" in saved


def test_fail_closed_runtime_error_is_not_rewritten_as_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = OrchestraFailClosedError(
        stage="worker",
        activation_profile="FULL_ORCHESTRA",
        baseline_decision="ANSWER",
    )
    monkeypatch.setattr(api.state, "pipeline", _FakePipeline(error=error))

    with pytest.raises(api.HTTPException) as caught:
        api.ask(api.AskRequest(question="What applies?"))

    assert caught.value.status_code == 409
    assert caught.value.detail == error.safe_message


def test_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        api.AskRequest(question="What applies?", unexpected="value")


def test_request_rejects_unknown_department() -> None:
    with pytest.raises(ValidationError):
        api.AskRequest(question="What applies?", department="Secret Department")
