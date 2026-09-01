"""Deterministic M2 query normalisation, intent detection, and decomposition."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from riskon.config import M2QueryPlanningConfig
from riskon.models import QueryInput, QueryIntent, QueryPlan, RetrievalChannel


@dataclass(frozen=True)
class AliasRule:
    """One version-controlled alias mapping."""

    canonical: str
    variants: tuple[str, ...]
    kind: str


class QueryPlanner:
    """Build closed-world plans without fuzzy or model-based correction."""

    _allowed_alias_kinds = {"DECLARED_TYPO", "DECLARED_SYNONYM", "DECLARED_ACRONYM"}
    _term_lexicon: tuple[str, ...] = (
        "control delta",
        "service basic",
        "service plus",
        "region beta",
        "region alpha",
        "interactive session",
        "overnight monitoring",
        "session alerts",
        "advisory location alpha",
        "premium mandate",
        "elected tier",
        "eligibility conditions",
        "application form",
        "suitable proposal",
        "delegated operator",
    )

    def __init__(self, aliases: list[AliasRule], config: M2QueryPlanningConfig) -> None:
        self.aliases = aliases
        self.config = config

    @classmethod
    def from_file(cls, path: Path, config: M2QueryPlanningConfig) -> QueryPlanner:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "1.0":
            raise ValueError("Unsupported M2 alias registry schema")
        aliases: list[AliasRule] = []
        for item in payload.get("aliases", []):
            kind = str(item["kind"])
            if kind not in cls._allowed_alias_kinds:
                raise ValueError(f"Unsupported alias kind: {kind}")
            aliases.append(
                AliasRule(
                    canonical=str(item["canonical"]).strip().lower(),
                    variants=tuple(str(value).strip() for value in item["variants"]),
                    kind=kind,
                )
            )
        return cls(aliases, config)

    def plan(self, request: QueryInput) -> QueryPlan:
        """Return the same plan for the same query, context, and alias registry."""

        normalised_query = self._normalise(request.query)
        intent = self._intent(normalised_query)
        required_fields = self._required_context_fields(intent)
        supplied_context = self._context_values(request, normalised_query)
        missing_fields = [field for field in required_fields if field not in supplied_context]
        retrieval_skipped = bool(missing_fields and self.config.require_explicit_context)
        subqueries = [] if retrieval_skipped else self._decompose(normalised_query)
        channels = [] if retrieval_skipped else self._channels(intent)
        canonical_terms = self._canonical_terms(normalised_query, supplied_context)
        plan_id = self._plan_id(
            request,
            normalised_query,
            intent,
            canonical_terms,
            required_fields,
            missing_fields,
            subqueries,
            channels,
            retrieval_skipped,
        )
        return QueryPlan(
            plan_id=plan_id,
            original_query=request.query,
            normalised_query=normalised_query,
            intent=intent,
            canonical_terms=canonical_terms,
            required_context_fields=required_fields,
            missing_context_fields=missing_fields,
            subqueries=subqueries,
            retrieval_channels=channels,
            retrieval_skipped=retrieval_skipped,
        )

    def context_values(self, request: QueryInput, plan: QueryPlan) -> dict[str, str]:
        """Expose the normalised context used by scope filtering."""

        return self._context_values(request, plan.normalised_query)

    def _normalise(self, query: str) -> str:
        result = query
        matched_aliases: set[str] = set()
        for alias in self.aliases:
            for variant in sorted(alias.variants, key=len, reverse=True):
                pattern = re.compile(re.escape(variant), re.IGNORECASE)
                if pattern.search(result):
                    matched_aliases.add(alias.canonical)
                    if alias.kind != "DECLARED_SYNONYM":
                        result = pattern.sub(alias.canonical, result, count=1)
                    break
        for alias in self.aliases:
            if alias.canonical in matched_aliases:
                continue
            pattern = re.compile(re.escape(alias.canonical), re.IGNORECASE)
            result = pattern.sub(alias.canonical, result)
        return " ".join(result.split())

    @staticmethod
    def _intent(query: str) -> QueryIntent:
        lowered = query.lower()
        if "suitable proposal" in lowered or "what is" in lowered or "definition" in lowered:
            return QueryIntent.DEFINITION
        if "does " in lowered and " apply" in lowered or "apply to" in lowered:
            return QueryIntent.APPLICABILITY
        if "which " in lowered and " active" in lowered or "configuration" in lowered:
            return QueryIntent.CONFIGURATION_LOOKUP
        if "trigger" in lowered or ("resolve" in lowered and "alert" in lowered):
            return QueryIntent.ALERT_RESOLUTION
        if "meaning" in lowered or " acronym" in lowered or " use arc" in lowered:
            return QueryIntent.REFERENCE_LOOKUP
        if (
            "procedure" in lowered
            or lowered.startswith("how ")
            or "eligibility" in lowered
            or "application form" in lowered
        ):
            return QueryIntent.PROCEDURE
        return QueryIntent.REFERENCE_LOOKUP

    @staticmethod
    def _required_context_fields(intent: QueryIntent) -> list[str]:
        if intent is QueryIntent.ALERT_RESOLUTION:
            return ["workflow_stage"]
        if intent is QueryIntent.APPLICABILITY:
            return ["region", "service_model"]
        if intent is QueryIntent.CONFIGURATION_LOOKUP:
            return ["location", "mandate"]
        return []

    def _context_values(self, request: QueryInput, query: str) -> dict[str, str]:
        lowered = query.lower()
        supplied = {key.lower(): value.strip() for key, value in request.context.items()}
        values: dict[str, str] = {}

        workflow_stage = supplied.get("workflow_stage", "").lower()
        if (
            workflow_stage in {"interactive_session", "interactive"}
            or "interactive session" in lowered
        ):
            values["workflow_stage"] = "interactive_session"
        elif (
            workflow_stage in {"overnight_monitoring", "overnight"}
            or "overnight monitoring" in lowered
        ):
            values["workflow_stage"] = "overnight_monitoring"

        region = supplied.get("region", "").upper().replace("REGION_", "")
        if region in {"ALPHA", "BETA"}:
            values["region"] = region
        elif "region alpha" in lowered:
            values["region"] = "ALPHA"
        elif "region beta" in lowered:
            values["region"] = "BETA"

        service_model = supplied.get("service_model", "").upper().replace("SERVICE_", "")
        if service_model in {"BASIC", "PLUS"}:
            values["service_model"] = service_model
        elif "service basic" in lowered:
            values["service_model"] = "BASIC"
        elif "service plus" in lowered:
            values["service_model"] = "PLUS"

        location = supplied.get("location", "").upper().replace("LOCATION_", "")
        if location in {"ALPHA", "BETA"}:
            values["location"] = location
        elif "location alpha" in lowered:
            values["location"] = "ALPHA"
        elif "location beta" in lowered:
            values["location"] = "BETA"

        mandate = supplied.get("mandate", "").upper()
        if mandate in {"PREMIUM", "STANDARD"}:
            values["mandate"] = mandate
        elif "premium mandate" in lowered:
            values["mandate"] = "PREMIUM"
        elif "standard mandate" in lowered:
            values["mandate"] = "STANDARD"
        return values

    def _canonical_terms(self, query: str, context: dict[str, str]) -> list[str]:
        lowered = query.lower()
        terms: list[str] = []
        for alias in self.aliases:
            if alias.canonical in lowered or any(
                variant.lower() in lowered for variant in alias.variants
            ):
                terms.append(alias.canonical)
        for term in self._term_lexicon:
            if term in lowered and term not in terms:
                terms.append(term)
        del context
        return terms

    def _decompose(self, query: str) -> list[str]:
        lowered = query.lower()
        marker = next((item for item in self.config.split_markers if item in lowered), None)
        if marker is None:
            return []
        if len(query.split()) < 4:
            return []
        pattern = re.compile(r",?\s+and\s+(where|how|what)\s+", re.IGNORECASE)
        match = pattern.search(query)
        if match is None:
            return []
        first = query[: match.start()].strip().rstrip("?.,") + "?"
        second = (
            match.group(1).capitalize() + " " + query[match.end() :].strip().rstrip("?.,") + "?"
        )
        return [first, second][: self.config.max_subqueries]

    @staticmethod
    def _channels(intent: QueryIntent) -> list[RetrievalChannel]:
        if intent is QueryIntent.CONFIGURATION_LOOKUP:
            return [
                RetrievalChannel.EXACT,
                RetrievalChannel.TABLE_ROW,
                RetrievalChannel.WORD_TFIDF,
                RetrievalChannel.CHAR_TFIDF,
            ]
        return [
            RetrievalChannel.EXACT,
            RetrievalChannel.WORD_TFIDF,
            RetrievalChannel.CHAR_TFIDF,
        ]

    @staticmethod
    def _plan_id(
        request: QueryInput,
        normalised_query: str,
        intent: QueryIntent,
        canonical_terms: list[str],
        required_fields: list[str],
        missing_fields: list[str],
        subqueries: list[str],
        channels: list[RetrievalChannel],
        retrieval_skipped: bool,
    ) -> str:
        payload = {
            "query": request.query,
            "context": dict(sorted(request.context.items())),
            "normalised_query": normalised_query,
            "intent": intent.value,
            "canonical_terms": canonical_terms,
            "required_fields": required_fields,
            "missing_fields": missing_fields,
            "subqueries": subqueries,
            "channels": [channel.value for channel in channels],
            "retrieval_skipped": retrieval_skipped,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return f"plan-{digest[:16]}"


class M4DQueryPlanner(QueryPlanner):
    """M4D planner for the additive synthetic corpus.

    M4D deliberately keeps the original query spelling intact.  The runtime
    needs to detect the ambiguous ``ARC`` input before a declared M2 acronym
    expansion can make it appear unambiguous, and counterfactual runs must
    derive scope only from supplied structured context.
    """

    _term_lexicon = QueryPlanner._term_lexicon + (
        "synthetic stability marker",
        "arc",
        "synthetic atlas exception request",
        "synthetic atlas control",
        "control meridian",
    )

    @classmethod
    def from_file(cls, path: Path, config: M2QueryPlanningConfig) -> M4DQueryPlanner:
        """Load the shared M2 aliases while returning the M4D planner type."""

        base = QueryPlanner.from_file(path, config)
        return cls(base.aliases, config)

    def _normalise(self, query: str) -> str:
        """Normalize whitespace without rewriting domain terms or acronyms."""

        return " ".join(query.split())

    @staticmethod
    def _intent(query: str) -> QueryIntent:
        """Recognize the small M4D vocabulary before falling back to M2 rules."""

        lowered = query.lower()
        if "synthetic stability marker" in lowered:
            return QueryIntent.DEFINITION
        if "synthetic atlas exception request" in lowered:
            return QueryIntent.PROCEDURE
        if "synthetic atlas control" in lowered:
            return QueryIntent.PROCEDURE
        if "control meridian" in lowered and ("apply" in lowered or "does " in lowered):
            return QueryIntent.APPLICABILITY
        if "arc" in lowered and "delegated operator" in lowered:
            return QueryIntent.REFERENCE_LOOKUP
        return QueryPlanner._intent(query)

    def plan(self, request: QueryInput) -> QueryPlan:
        """Build a deterministic M4D plan and short-circuit the ambiguous ARC query."""

        normalised_query = self._normalise(request.query)
        intent = self._intent(normalised_query)
        required_fields = self._required_context_fields(intent)
        supplied_context = self._context_values(request, normalised_query)
        missing_fields = [field for field in required_fields if field not in supplied_context]
        lowered = normalised_query.lower()
        ambiguous_arc = "arc" in lowered and "delegated operator" in lowered
        retrieval_skipped = ambiguous_arc or bool(
            missing_fields and self.config.require_explicit_context
        )
        subqueries = [] if retrieval_skipped else self._decompose(normalised_query)
        channels = [] if retrieval_skipped else self._channels(intent)
        canonical_terms = self._canonical_terms(normalised_query, supplied_context)
        plan_id = self._plan_id(
            request,
            normalised_query,
            intent,
            canonical_terms,
            required_fields,
            missing_fields,
            subqueries,
            channels,
            retrieval_skipped,
        )
        return QueryPlan(
            plan_id=plan_id,
            original_query=request.query,
            normalised_query=normalised_query,
            intent=intent,
            canonical_terms=canonical_terms,
            required_context_fields=required_fields,
            missing_context_fields=missing_fields,
            subqueries=subqueries,
            retrieval_channels=channels,
            retrieval_skipped=retrieval_skipped,
        )

    def _canonical_terms(self, query: str, context: dict[str, str]) -> list[str]:
        """Return M4D terms without importing M2 acronym semantics."""

        lowered = query.lower()
        del context
        return [term for term in self._term_lexicon if term in lowered]

    def _context_values(self, request: QueryInput, query: str) -> dict[str, str]:
        """Read only explicit caller context; never infer a removed dimension from text."""

        del query
        supplied = {
            key.strip().lower(): value.strip()
            for key, value in request.context.items()
            if key.strip() and value.strip()
        }
        values: dict[str, str] = {}
        for key in (
            "workflow_stage",
            "region",
            "service_model",
            "jurisdiction",
            "solicitation_type",
            "location",
            "mandate",
        ):
            raw = supplied.get(key)
            if raw is None:
                continue
            normalized = raw.upper().replace("-", "_").replace(" ", "_")
            if key == "region" and normalized in {"ALPHA", "BETA"}:
                normalized = f"REGION_{normalized}"
            elif key == "service_model" and normalized in {"BASIC", "PLUS"}:
                normalized = f"SERVICE_{normalized}"
            values[key] = normalized
        return values
