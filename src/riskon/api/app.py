"""Small REST surface over the canonical event runtime.

The API is transport only: it loads the existing event-backed M4D/M5B pipeline once,
passes each request to run_orchestrated(), and serialises the same safe payload used
by the CLI. It does not add a second answer engine or decision authority.

Run locally with:

    uv run uvicorn riskon.api.app:app --host 127.0.0.1 --port 3000

The event runtime configuration defaults to data/private/event_runtime.toml. Set
RISKON_EVENT_RUNTIME_CONFIG to use another local configuration file.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from riskon.api.memory_ui import MEMORY_HTML
from riskon.api.ui import INDEX_HTML
from riskon.event_runtime.config import load_event_runtime_config
from riskon.event_runtime.corpus_loader import EventRuntimeCorpusError
from riskon.event_runtime.evidence_reasoning import (
    EventEvidenceReasoningResult,
    EventEvidenceReasoningRuntime,
    build_event_evidence_reasoning_runtime,
)
from riskon.event_runtime.internal_memory import (
    FeedbackRating,
    InternalMemoryStore,
    MemoryAgent,
    MemorySnapshot,
    normalize_department,
)
from riskon.event_runtime.models import EventQueryPayload
from riskon.event_runtime.reporting import query_result_payload
from riskon.models import QueryInput
from riskon.orchestra.errors import OrchestraConfigurationError, OrchestraFailClosedError
from riskon.pipeline import M4DRiskonPipeline, RiskonPipeline

API_VERSION = "1.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVENT_CONFIG = PROJECT_ROOT / "data/private/event_runtime.toml"
RUNTIME_CLARIFICATION = (
    "I could not map that request safely to the Julius Baer material. "
    "Please rephrase it with the exact client-classification term, service model, "
    "or process you mean."
)


class _State:
    """Process-local runtime handles populated by the application lifespan."""

    pipeline: M4DRiskonPipeline | None = None
    evidence_runtime: EventEvidenceReasoningRuntime | None = None
    memory: InternalMemoryStore | None = None
    memory_agent: MemoryAgent | None = None
    startup_error: str | None = None


state = _State()


class AskRequest(BaseModel):
    """A question and optional structured context for the event runtime."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    context: dict[str, str] = Field(default_factory=dict)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, max_length=80)

    @field_validator("department")
    @classmethod
    def _fixed_department(cls, value: str | None) -> str | None:
        """Keep the optional UI context on a small, auditable vocabulary."""

        return normalize_department(value)


class AskResponse(BaseModel):
    """Safe result plus server-side execution time."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=120)
    turn_id: str = Field(min_length=1, max_length=120)
    took_ms: float = Field(ge=0.0)
    result: EventQueryPayload


class FeedbackRequest(BaseModel):
    """Three-way feedback metadata; no answer or source text is accepted."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str = Field(min_length=1, max_length=120)
    turn_id: str = Field(min_length=1, max_length=120)
    rating: FeedbackRating
    department: str | None = Field(default=None, max_length=80)
    decision: str = Field(default="UNKNOWN", min_length=1, max_length=24)
    note: str | None = Field(default=None, max_length=240)

    @field_validator("department")
    @classmethod
    def _fixed_department(cls, value: str | None) -> str | None:
        return normalize_department(value)


class FeedbackResponse(BaseModel):
    """Safe acknowledgement of stored feedback."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    feedback_id: str = Field(min_length=1, max_length=120)
    action: str = Field(min_length=1, max_length=32)


class MemoryItemResponse(BaseModel):
    """One short shared-memory paragraph; identifiers and source content stay private."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    departments: list[str]
    updated_at: str


class MemoryResponse(BaseModel):
    """Safe read-only shared-memory summary used by the Memory page."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    items: list[MemoryItemResponse]
    count: int = Field(ge=0)
    capacity: int = Field(ge=0)
    updated_at: str | None


class HealthResponse(BaseModel):
    """Readiness without exposing corpus paths or source content."""

    model_config = ConfigDict(extra="forbid")

    status: str
    api_version: str
    runtime_loaded: bool


class RuntimeConfigRequest(BaseModel):
    """Local paths used to connect a teammate's private event package."""

    model_config = ConfigDict(extra="forbid")

    source_root: str = Field(min_length=1, max_length=500)
    manifest: str = Field(min_length=1, max_length=500)

    @field_validator("source_root", "manifest")
    @classmethod
    def _absolute_local_path(cls, value: str) -> str:
        """Normalise a pasted Finder path without accepting URLs or relatives."""

        clean = value.strip()
        if not clean or "\x00" in clean:
            raise ValueError("Local paths must be non-empty")
        try:
            path = Path(clean).expanduser()
        except (OSError, RuntimeError) as exc:
            raise ValueError("Local paths must be valid filesystem paths") from exc
        if not path.is_absolute():
            raise ValueError("Local paths must be absolute")
        return str(path.resolve())


class RuntimeConfigResponse(BaseModel):
    """Safe acknowledgement without returning private corpus paths."""

    model_config = ConfigDict(extra="forbid")

    configured: bool
    runtime_loaded: bool
    message: str


def _event_config_path() -> Path:
    """Resolve the local event config without accepting a secret or URL."""

    configured = os.environ.get("RISKON_EVENT_RUNTIME_CONFIG", "").strip()
    return Path(configured).expanduser().resolve() if configured else DEFAULT_EVENT_CONFIG


def _event_runtime_config_text(source_root: Path, manifest: Path) -> str:
    """Render the ignored local config without embedding event data in the repo."""

    source_value = json.dumps(str(source_root), ensure_ascii=False)
    manifest_value = json.dumps(str(manifest), ensure_ascii=False)
    return (
        "[base]\n"
        'pipeline_config = "config/milestone5b.toml"\n\n'
        "[event_corpus]\n"
        f"source_root = {source_value}\n"
        f"manifest = {manifest_value}\n"
        "column_mapping = {}\n"
        'url_prefix = "local://event-wiki/"\n'
        'generated_root = "data/generated/event_runtime"\n\n'
        "[event_runtime]\n"
        'alias_registry = "data/generated/event_runtime/event_aliases.json"\n'
        'routing_profile = "default"\n'
        "overlay_enabled = false\n\n"
        "[security]\n"
        "event_data_copy_enabled = false\n"
        "network_enabled = false\n"
        "external_api_enabled = false\n"
    )


def _load_event_pipeline() -> M4DRiskonPipeline:
    """Build the canonical event pipeline through its existing factory."""

    event_config = load_event_runtime_config(_event_config_path())
    return RiskonPipeline.from_event_runtime_config(event_config)


def _evidence_runtime() -> EventEvidenceReasoningRuntime:
    """Build the existing bounded evidence runtime only when the M4D path lacks support."""

    if state.evidence_runtime is None:
        state.evidence_runtime = build_event_evidence_reasoning_runtime(
            load_event_runtime_config(_event_config_path()),
            use_policy_atlas=False,
        )
    return state.evidence_runtime


def _reasoning_payload(reasoned: EventEvidenceReasoningResult) -> EventQueryPayload:
    """Expose only the reasoning runtime's firewall-approved public result."""

    route = reasoned.route.model_dump(mode="json") if reasoned.route is not None else None
    evidence_refs = list(
        dict.fromkeys(
            [
                *reasoned.evidence_refs,
                *(item.source_ref for item in reasoned.result.evidence),
            ]
        )
    )
    worker_roles = ["CONTEXT_INTERPRETER"]
    if reasoned.final_analysis is not None:
        worker_roles.append("EVIDENCE_ANALYST")
    if reasoned.skeptic is not None:
        worker_roles.append("SKEPTIC")
    return EventQueryPayload(
        decision=reasoned.decision.value,
        answer=reasoned.answer,
        clarification=reasoned.clarifying_question,
        abstention_reason=[reason.value for reason in reasoned.reason_codes],
        evidence_refs=evidence_refs,
        route=route,
        activation_profile=(
            "STRUCTURED_FAST_PATH"
            if reasoned.skeptic is None
            and reasoned.final_analysis is not None
            and reasoned.final_analysis.evidence_sufficiency.value == "SUFFICIENT"
            else "EVIDENCE_REASONING"
        ),
        worker_roles=worker_roles,
        worker_execution_count=len(worker_roles),
    )


def _needs_evidence_fallback(run: object) -> bool:
    """Use Task 5 only when the legacy M4D shell found no substantive claim."""

    final = getattr(run, "final_verified_run", None)
    result = getattr(final, "result", None)
    if result is None or getattr(result.decision, "value", "") != "ABSTAIN":
        return False
    # The legacy M4D shell can fail closed on generic questions before the Task 5
    # evidence runtime gets a chance to inspect the actual source.  Let the bounded
    # evidence runtime adjudicate both unsupported and legacy scope failures; its own
    # local validation and Answer Firewall remain authoritative.
    return any(
        getattr(reason, "value", "")
        in {
            "UNSUPPORTED_CLAIM",
            "SCOPE_MISMATCH",
            "NO_EXPLICIT_SUPPORT",
            "SOURCE_PACKAGE_ASSET_UNAVAILABLE",
        }
        for reason in getattr(result, "reason_codes", ())
    )


def _memory_store() -> InternalMemoryStore:
    """Return local generated memory without exposing its path over the API."""

    if state.memory is None:
        state.memory = InternalMemoryStore(
            PROJECT_ROOT / "data/generated/event_runtime/assistant_memory"
        )
    return state.memory


def _memory_agent() -> MemoryAgent:
    """Return the bounded feedback/memory coordinator."""

    if state.memory_agent is None:
        state.memory_agent = MemoryAgent()
    return state.memory_agent


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Load the corpus once and make a missing event package visible as not-ready."""

    state.pipeline = None
    state.evidence_runtime = None
    state.memory = None
    state.memory_agent = None
    state.startup_error = None
    try:
        event_config = load_event_runtime_config(_event_config_path())
        state.memory = InternalMemoryStore(event_config.generated_root / "assistant_memory")
        state.memory_agent = MemoryAgent()
        state.pipeline = RiskonPipeline.from_event_runtime_config(event_config)
    except (EventRuntimeCorpusError, FileNotFoundError, OSError, ValueError):
        state.startup_error = "Event runtime is not ready; check the local runtime configuration."
    try:
        yield
    finally:
        state.pipeline = None
        state.evidence_runtime = None
        state.memory = None
        state.memory_agent = None


app = FastAPI(
    title="RiskON Challenge 1 Assistant",
    version=API_VERSION,
    summary="Evidence-first answers from the local event corpus.",
    lifespan=lifespan,
)


def _pipeline() -> M4DRiskonPipeline:
    """Return the loaded pipeline or a safe readiness error."""

    if state.pipeline is None:
        raise HTTPException(
            status_code=503,
            detail=state.startup_error
            or "Event runtime is not ready; check the local runtime configuration.",
        )
    return state.pipeline


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> str:
    """Serve Gabriel's adapted chat UI from the same origin as the API."""

    return INDEX_HTML


@app.get("/memory", response_class=HTMLResponse, include_in_schema=False)
def memory_page() -> str:
    """Serve the redacted, read-only memory view from the same origin."""

    return MEMORY_HTML


def _memory_response(snapshot: MemorySnapshot) -> MemoryResponse:
    """Expose only compact shared memory, never operational chat state or feedback."""

    items = [
        MemoryItemResponse(
            summary=item.summary,
            departments=item.departments,
            updated_at=item.updated_at.isoformat(),
        )
        for item in snapshot.shared_memory
    ]
    latest = max((item.updated_at for item in snapshot.shared_memory), default=None)

    return MemoryResponse(
        summary=(
            "No durable shared memory has been saved yet."
            if not items
            else "A small set of reusable context is shared across the assistant."
        ),
        items=items,
        count=len(items),
        capacity=snapshot.shared_memory_capacity,
        updated_at=latest.isoformat() if latest is not None else None,
    )


@app.get("/v1/memory", response_model=MemoryResponse, tags=["assistant"])
def memory_view() -> MemoryResponse:
    """Return only bounded shared memory; never return raw Q&A, feedback, or evidence."""

    return _memory_response(_memory_store().snapshot())


@app.get("/v1/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Expose readiness only; never return source paths or raw corpus content."""

    loaded = state.pipeline is not None
    return HealthResponse(
        status="ok" if loaded else "not_ready",
        api_version=API_VERSION,
        runtime_loaded=loaded,
    )


@app.post("/v1/runtime-config", response_model=RuntimeConfigResponse, tags=["ops"])
def configure_runtime(request: RuntimeConfigRequest) -> RuntimeConfigResponse:
    """Connect a local private pages package and reload the canonical runtime."""

    source_root = Path(request.source_root)
    manifest = Path(request.manifest)
    if not source_root.is_dir():
        raise HTTPException(status_code=400, detail="Pages folder was not found.")
    if not manifest.is_file() or manifest.suffix.casefold() not in {".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="Summary workbook was not found.")
    if not any(
        path.is_file() and path.suffix.casefold() in {".html", ".htm"}
        for path in source_root.rglob("*")
    ):
        raise HTTPException(status_code=400, detail="Pages folder contains no HTML pages.")

    config_path = _event_config_path()
    try:
        if not config_path.is_relative_to(PROJECT_ROOT):
            raise ValueError("Local runtime config must remain inside the repository")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=config_path.parent,
                prefix=".event_runtime.",
                suffix=".toml",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(_event_runtime_config_text(source_root, manifest))
            candidate_config = load_event_runtime_config(temporary_path)
            candidate_pipeline = RiskonPipeline.from_event_runtime_config(candidate_config)
            os.replace(temporary_path, config_path)
            state.pipeline = candidate_pipeline
            state.evidence_runtime = None
            state.startup_error = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    except (EventRuntimeCorpusError, FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail="These local event files could not be loaded. Check the pages and workbook.",
        ) from exc
    return RuntimeConfigResponse(
        configured=True,
        runtime_loaded=state.pipeline is not None,
        message="Local event data connected.",
    )


@app.post("/v1/ask", response_model=AskResponse, tags=["assistant"])
def ask(request: AskRequest) -> AskResponse:
    """Run exactly one canonical orchestration request."""

    conversation_id = request.conversation_id or str(uuid4())
    turn_id = str(uuid4())
    pipeline = _pipeline()
    memory = _memory_store()
    agent = _memory_agent()
    context = dict(request.context)
    if request.department is not None:
        context["department"] = request.department
    # This is prompt context only.  The event pipeline still validates every
    # released claim against original evidence and the Answer Firewall.
    context["_riskon_memory_context"] = memory.prompt_context(
        request.question,
        conversation_id,
        request.department,
    )
    start = time.perf_counter()
    try:
        run = pipeline.run_orchestrated(
            QueryInput(query=request.question, context=context, trace_id=turn_id)
        )
    except OrchestraFailClosedError as exc:
        raise HTTPException(status_code=409, detail=exc.safe_message) from exc
    except OrchestraConfigurationError:
        try:
            result = _reasoning_payload(
                _evidence_runtime().run(
                    QueryInput(query=request.question, context=context, trace_id=turn_id)
                )
            )
        except Exception:
            result = EventQueryPayload(
                decision="CLARIFY",
                clarification=RUNTIME_CLARIFICATION,
                abstention_reason=["ORCHESTRATION_CONFIGURATION"],
                activation_profile="RUNTIME_GUARD",
                worker_execution_count=0,
            )
    except (EventRuntimeCorpusError, FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="The event runtime could not complete this request safely.",
        ) from exc
    else:
        result = EventQueryPayload.model_validate(query_result_payload(run))
        if _needs_evidence_fallback(run):
            try:
                result = _reasoning_payload(
                    _evidence_runtime().run(
                        QueryInput(query=request.question, context=context, trace_id=turn_id)
                    )
                )
            except Exception:
                # Keep the deterministic M4D result if the optional reasoning fallback
                # is unavailable or rate-limited; it remains fail-closed.
                pass
    agent.record_turn(
        memory,
        conversation_id=conversation_id,
        department=request.department,
        question=request.question,
        decision=result.decision,
    )
    return AskResponse(
        conversation_id=conversation_id,
        turn_id=turn_id,
        took_ms=round((time.perf_counter() - start) * 1000, 1),
        result=result,
    )


@app.post("/v1/feedback", response_model=FeedbackResponse, tags=["assistant"])
def feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Store feedback through the intermediate reviewer without changing an answer."""

    memory = _memory_store()
    record = _memory_agent().review_feedback(
        memory,
        conversation_id=request.conversation_id,
        turn_id=request.turn_id,
        rating=request.rating,
        department=request.department,
        decision=request.decision,
        note=request.note,
    )
    return FeedbackResponse(
        accepted=True,
        feedback_id=record.feedback_id,
        action=record.review.action,
    )
