"""Bounded OpenAI Responses API client for event metadata and reasoning."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

LLMPhase = Literal[
    "page_card",
    "title_router",
    "router_retry",
    "context_interpreter",
    "claim_builder",
    "skeptic",
]
ReasoningEffort = Literal["none", "low", "medium"]

PAGE_CARD_MODEL: str = "gpt-5.6-luna"
PAGE_CARD_REASONING: ReasoningEffort = "none"
TITLE_ROUTER_MODEL: str = "gpt-5.6-terra"
TITLE_ROUTER_REASONING: ReasoningEffort = "low"
ROUTER_RETRY_MODEL: str = "gpt-5.6-terra"
ROUTER_RETRY_REASONING: ReasoningEffort = "medium"

CONTEXT_INTERPRETER_MODEL: str = "gpt-5.6-luna"
CONTEXT_INTERPRETER_REASONING: ReasoningEffort = "low"
CLAIM_BUILDER_MODEL: str = "gpt-5.6-terra"
CLAIM_BUILDER_REASONING: ReasoningEffort = "medium"
SKEPTIC_MODEL: str = "gpt-5.6-terra"
SKEPTIC_REASONING: ReasoningEffort = "medium"


class Task4LLMConfig(BaseModel):
    """Non-secret bounded settings; model policy is intentionally fixed above."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key_env: str = Field(default="OPENAI_API_KEY", min_length=1)
    page_card_excerpt_chars: int = Field(default=3500, ge=800, le=5000)
    router_title_shortlist: int = Field(default=48, ge=10, le=64)
    router_card_limit: int = Field(default=32, ge=8, le=48)
    max_selected_pages: int = Field(default=10, ge=1, le=10)
    page_card_workers: int = Field(default=8, ge=1, le=8)
    request_timeout_seconds: float = Field(default=60.0, gt=0.0, le=120.0)


class Task5LLMConfig(Task4LLMConfig):
    """Bounded Task 5 settings; the model policy remains fixed in this module."""

    max_evidence_units: int = Field(default=8, ge=1, le=8)
    max_evidence_chars: int = Field(default=12_000, ge=1000, le=12_000)
    max_nearby_units: int = Field(default=2, ge=0, le=2)
    max_claims: int = Field(default=8, ge=1, le=8)


@dataclass(frozen=True)
class LLMCallRecord:
    """Safe API accounting record; it contains no prompt, response, or secret."""

    phase: LLMPhase
    model: str
    reasoning_effort: ReasoningEffort
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    latency_ms: float


@dataclass
class LLMUsage:
    """Aggregate call and token accounting for one bounded event run."""

    page_card_calls: int = 0
    title_router_calls: int = 0
    router_retry_calls: int = 0
    context_interpreter_calls: int = 0
    claim_builder_calls: int = 0
    skeptic_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    latency_ms: float = 0.0
    _lock: Lock = field(default_factory=Lock, init=False, repr=False, compare=False)

    def record(self, call: LLMCallRecord) -> None:
        """Accumulate one call without retaining its content."""

        with self._lock:
            if call.phase == "page_card":
                self.page_card_calls += 1
            elif call.phase == "title_router":
                self.title_router_calls += 1
            elif call.phase == "router_retry":
                self.router_retry_calls += 1
            elif call.phase == "context_interpreter":
                self.context_interpreter_calls += 1
            elif call.phase == "claim_builder":
                self.claim_builder_calls += 1
            else:
                self.skeptic_calls += 1
            self.input_tokens += call.input_tokens
            self.output_tokens += call.output_tokens
            self.cached_input_tokens += call.cached_input_tokens
            self.latency_ms += call.latency_ms

    @property
    def total_calls(self) -> int:
        """Return total external LLM calls."""

        with self._lock:
            return (
                self.page_card_calls
                + self.title_router_calls
                + self.router_retry_calls
                + self.context_interpreter_calls
                + self.claim_builder_calls
                + self.skeptic_calls
            )


class SemanticLLMError(RuntimeError):
    """Raised when an exact-policy structured LLM call cannot complete safely."""


class LLMConfigurationError(SemanticLLMError):
    """Raised when the required event-approved credential or SDK is unavailable."""


_ModelT = TypeVar("_ModelT", bound=BaseModel)


class EventOpenAIClient:
    """Minimal Responses API adapter with fixed Task 4 and Task 5 routing."""

    _specs: dict[LLMPhase, tuple[str, ReasoningEffort, int]] = {
        "page_card": (PAGE_CARD_MODEL, PAGE_CARD_REASONING, 500),
        "title_router": (TITLE_ROUTER_MODEL, TITLE_ROUTER_REASONING, 900),
        "router_retry": (ROUTER_RETRY_MODEL, ROUTER_RETRY_REASONING, 900),
        "context_interpreter": (CONTEXT_INTERPRETER_MODEL, CONTEXT_INTERPRETER_REASONING, 900),
        "claim_builder": (CLAIM_BUILDER_MODEL, CLAIM_BUILDER_REASONING, 5000),
        "skeptic": (SKEPTIC_MODEL, SKEPTIC_REASONING, 1600),
    }

    def __init__(
        self,
        config: Task4LLMConfig | None = None,
        *,
        client: Any | None = None,
    ) -> None:
        self.config = config or Task4LLMConfig()
        self.usage = LLMUsage()
        if client is not None:
            self._client = client
            return
        api_key = os.environ.get(self.config.api_key_env)
        if not api_key:
            raise LLMConfigurationError(
                f"Required API key environment variable is missing: {self.config.api_key_env}"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency is locked for production
            raise LLMConfigurationError("The OpenAI SDK is not installed") from exc
        self._client = OpenAI(
            api_key=api_key,
            max_retries=0,
            timeout=self.config.request_timeout_seconds,
        )

    def request_json(
        self,
        phase: LLMPhase,
        response_model: type[_ModelT],
        *,
        developer_prompt: str,
        user_prompt: str,
    ) -> tuple[_ModelT, LLMCallRecord]:
        """Request one strictly structured JSON object from the fixed policy model."""

        model, reasoning_effort, max_output_tokens = self._specs[phase]
        schema_name = {
            "page_card": "riskon_page_card",
            "title_router": "riskon_title_router",
            "router_retry": "riskon_title_router_retry",
            "context_interpreter": "riskon_context_interpreter",
            "claim_builder": "riskon_evidence_claim_builder",
            "skeptic": "riskon_evidence_skeptic",
        }[phase]
        started = time.perf_counter()
        try:
            response = self._client.responses.create(
                model=model,
                reasoning={"effort": reasoning_effort},
                input=[
                    {"role": "developer", "content": developer_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema_name,
                        "schema": response_model.model_json_schema(),
                        "strict": True,
                    },
                    "verbosity": "low",
                },
                max_output_tokens=max_output_tokens,
                store=False,
            )
            output_text = getattr(response, "output_text", "")
            if not isinstance(output_text, str) or not output_text.strip():
                raise ValueError("structured response was empty")
            payload = json.loads(output_text)
            parsed = response_model.model_validate(payload)
        except Exception as exc:
            raise SemanticLLMError(
                f"Structured event {phase} request failed: {type(exc).__name__}"
            ) from exc

        call = LLMCallRecord(
            phase=phase,
            model=model,
            reasoning_effort=reasoning_effort,
            input_tokens=_usage_value(response, "input_tokens"),
            output_tokens=_usage_value(response, "output_tokens"),
            cached_input_tokens=_cached_usage_value(response),
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )
        self.usage.record(call)
        return parsed, call


def _usage_value(response: Any, field: str) -> int:
    """Read a numeric usage field from either SDK models or test doubles."""

    usage = getattr(response, "usage", None)
    if usage is None:
        return 0
    value = getattr(usage, field, None)
    if value is None and isinstance(usage, dict):
        value = usage.get(field)
    return int(value or 0)


def _cached_usage_value(response: Any) -> int:
    """Read cached input-token usage without serializing the response."""

    usage = getattr(response, "usage", None)
    if usage is None:
        return 0
    details = getattr(usage, "input_tokens_details", None)
    if details is None and isinstance(usage, dict):
        details = usage.get("input_tokens_details")
    value = getattr(details, "cached_tokens", None)
    if value is None and isinstance(details, dict):
        value = details.get("cached_tokens")
    return int(value or 0)
