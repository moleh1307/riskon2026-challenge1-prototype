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

import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from riskon.api.ui import INDEX_HTML
from riskon.event_runtime.config import load_event_runtime_config
from riskon.event_runtime.corpus_loader import EventRuntimeCorpusError
from riskon.event_runtime.models import EventQueryPayload
from riskon.event_runtime.reporting import query_result_payload
from riskon.models import QueryInput
from riskon.orchestra.errors import OrchestraFailClosedError
from riskon.pipeline import M4DRiskonPipeline, RiskonPipeline

API_VERSION = "1.0.0"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVENT_CONFIG = PROJECT_ROOT / "data/private/event_runtime.toml"


class _State:
    """Process-local runtime handles populated by the application lifespan."""

    pipeline: M4DRiskonPipeline | None = None
    startup_error: str | None = None


state = _State()


class AskRequest(BaseModel):
    """A question and optional structured context for the event runtime."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    context: dict[str, str] = Field(default_factory=dict)


class AskResponse(BaseModel):
    """Safe result plus server-side execution time."""

    model_config = ConfigDict(extra="forbid")

    took_ms: float = Field(ge=0.0)
    result: EventQueryPayload


class HealthResponse(BaseModel):
    """Readiness without exposing corpus paths or source content."""

    model_config = ConfigDict(extra="forbid")

    status: str
    api_version: str
    runtime_loaded: bool


def _event_config_path() -> Path:
    """Resolve the local event config without accepting a secret or URL."""

    configured = os.environ.get("RISKON_EVENT_RUNTIME_CONFIG", "").strip()
    return Path(configured).expanduser().resolve() if configured else DEFAULT_EVENT_CONFIG


def _load_event_pipeline() -> M4DRiskonPipeline:
    """Build the canonical event pipeline through its existing factory."""

    event_config = load_event_runtime_config(_event_config_path())
    return RiskonPipeline.from_event_runtime_config(event_config)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Load the corpus once and make a missing event package visible as not-ready."""

    state.pipeline = None
    state.startup_error = None
    try:
        state.pipeline = _load_event_pipeline()
    except (EventRuntimeCorpusError, FileNotFoundError, OSError, ValueError):
        state.startup_error = "Event runtime is not ready; check the local runtime configuration."
    try:
        yield
    finally:
        state.pipeline = None


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


@app.get("/v1/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Expose readiness only; never return source paths or raw corpus content."""

    loaded = state.pipeline is not None
    return HealthResponse(
        status="ok" if loaded else "not_ready",
        api_version=API_VERSION,
        runtime_loaded=loaded,
    )


@app.post("/v1/ask", response_model=AskResponse, tags=["assistant"])
def ask(request: AskRequest) -> AskResponse:
    """Run exactly one canonical orchestration request."""

    pipeline = _pipeline()
    start = time.perf_counter()
    try:
        run = pipeline.run_orchestrated(
            QueryInput(query=request.question, context=dict(request.context))
        )
    except OrchestraFailClosedError as exc:
        raise HTTPException(status_code=409, detail=exc.safe_message) from exc
    except (EventRuntimeCorpusError, FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="The event runtime could not complete this request safely.",
        ) from exc
    return AskResponse(
        took_ms=round((time.perf_counter() - start) * 1000, 1),
        result=EventQueryPayload.model_validate(query_result_payload(run)),
    )
