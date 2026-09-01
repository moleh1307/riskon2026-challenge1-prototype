"""Deterministic M1, M2, M3, and M4A evaluation and metric calculation."""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riskon.audit import (
    AuditLogger,
    validate_audit_file,
    validate_m4a_audit_file,
    validate_m4b_audit_file,
    validate_m4c_audit_file,
)
from riskon.config import (
    AuditConfig,
    Milestone1Config,
    Milestone2Config,
    Milestone3Config,
    Milestone4AConfig,
    Milestone4BConfig,
    Milestone4CConfig,
)
from riskon.m4d_evaluation import (
    M4DCase,
    M4DCaseSet,
    M4DEvaluationDocument,
    M4DEvaluator,
    M4DMetrics,
    M4DScenarioResult,
)

__all__ = [
    "M4DCase",
    "M4DCaseSet",
    "M4DEvaluationDocument",
    "M4DEvaluator",
    "M4DMetrics",
    "M4DScenarioResult",
]
from riskon.models import (
    Decision,
    ExpertRoute,
    PipelineResult,
    PlannedVerifiedRun,
    QueryInput,
    QueryIntent,
    ReasonCode,
    RetrievalChannel,
    RoutedRun,
    RouteMode,
    RoutingContext,
    VerifiedRun,
)
from riskon.orchestra.counterfactual_models import (
    CounterfactualExecutionResult,
    CounterfactualOperation,
    CounterfactualVariant,
)
from riskon.orchestra.counterfactual_runner import FrozenCounterfactualRunner
from riskon.orchestra.diagnostics import route_summary, run_safe_summary, write_model_jsonl
from riskon.orchestra.models import (
    ActivationProfile,
    AgentFinding,
    AgentTask,
    MaterialObjection,
    OrchestraContext,
    OrchestraRun,
    RiskSignal,
)
from riskon.orchestra.policy import ActivationPolicy
from riskon.pipeline import RiskonPipeline
from riskon.provenance import ProvenanceIndex
from riskon.verification import VerificationEngine


class ExpectedRoute(BaseModel):
    """Expected support function and optional synthetic expert."""

    model_config = ConfigDict(extra="forbid")

    support_function: str
    expert_id: str | None = None


class M1Case(BaseModel):
    """One machine-readable M1 evaluation case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    query: str
    input_context: dict[str, str]
    expected_decision: Decision
    expected_reason_codes: list[str]
    expected_clarifying_question: str | None
    required_claim_ids: list[str]
    forbidden_claim_ids: list[str]
    required_evidence_refs: list[str]
    expected_route: ExpectedRoute | None


class M1CaseSet(BaseModel):
    """M1 case-file envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    cases: list[M1Case]


class ScenarioResult(BaseModel):
    """Human- and machine-readable result for one regression case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    matched: bool
    failures: list[str]
    expected_decision: str
    actual_decision: str
    expected_reason_codes: list[str]
    actual_reason_codes: list[str]
    required_claim_ids: list[str]
    supported_claim_ids: list[str]
    forbidden_claim_ids: list[str]
    required_evidence_refs: list[str]
    actual_evidence_refs: list[str]
    expected_route: dict[str, Any] | None
    actual_route: dict[str, Any] | None
    result: dict[str, Any]


class M1Metrics(BaseModel):
    """Required M1 metric names and values."""

    model_config = ConfigDict(extra="forbid")

    scenario_match_rate: float = Field(ge=0.0, le=1.0)
    decision_accuracy: float = Field(ge=0.0, le=1.0)
    clarification_accuracy: float = Field(ge=0.0, le=1.0)
    answer_case_claim_recall: float = Field(ge=0.0, le=1.0)
    critical_claim_recall: float = Field(ge=0.0, le=1.0)
    citation_validity: float = Field(ge=0.0, le=1.0)
    route_function_accuracy: float = Field(ge=0.0, le=1.0)
    route_expert_accuracy: float = Field(ge=0.0, le=1.0)
    correct_abstention_rate: float = Field(ge=0.0, le=1.0)
    unnecessary_abstention_rate: float = Field(ge=0.0, le=1.0)
    scope_violation_count: int = Field(ge=0)
    unsupported_claim_count: int = Field(ge=0)
    unresolved_reference_false_negative_count: int = Field(ge=0)
    network_violation_count: int = Field(ge=0)


class M1EvaluationDocument(BaseModel):
    """Canonical JSON report schema."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    metrics: M1Metrics
    m0_regression: dict[str, Any]
    scenario_results: list[ScenarioResult]
    network_enabled: bool
    audit_schema_valid: bool


@dataclass(frozen=True)
class _Execution:
    """Internal pairing of expected case, verified run, and provenance index."""

    case: Any
    verified: VerifiedRun
    provenance: ProvenanceIndex
    is_m0: bool


def compare_case(execution: _Execution) -> ScenarioResult:
    """Compare one M0 or M1 execution with field-level failure messages."""

    verified = execution.verified
    result = verified.result
    report = verified.verification
    if execution.is_m0:
        expected = execution.case
        case_id = str(expected["id"])
        expected_decision = str(expected["expected"]["decision"])
        expected_reasons = [str(reason) for reason in expected["expected"].get("reason_codes", [])]
        required_claims: list[str] = []
        forbidden_claims: list[str] = []
        required_refs: list[str] = []
        expected_question = expected["expected"].get("clarifying_question")
        expected_route = expected["expected"].get("route")
        failures = _compare_common(
            case_id,
            result,
            report,
            expected_decision,
            expected_reasons,
            expected_question,
            expected_route,
            required_claims,
            forbidden_claims,
            required_refs,
        )
        if expected["expected"].get("evidence") is True and not result.evidence:
            failures.append(f"{case_id}: evidence expected=True actual=False")
        answer_contains = expected["expected"].get("answer_contains", [])
        for phrase in answer_contains:
            if result.answer is None or phrase not in result.answer:
                failures.append(
                    f"{case_id}: answer_contains expected={phrase!r} actual={result.answer!r}"
                )
        return _scenario_result(
            case_id,
            failures,
            expected_decision,
            expected_reasons,
            required_claims,
            report.supported_claim_ids,
            forbidden_claims,
            required_refs,
            report.evidence_refs,
            expected_route,
            result,
            report,
        )

    case = execution.case
    case_id = case.id
    expected_decision = case.expected_decision.value
    expected_reasons = case.expected_reason_codes
    expected_route = case.expected_route.model_dump(mode="json") if case.expected_route else None
    failures = _compare_common(
        case_id,
        result,
        report,
        expected_decision,
        expected_reasons,
        case.expected_clarifying_question,
        expected_route,
        case.required_claim_ids,
        case.forbidden_claim_ids,
        case.required_evidence_refs,
    )
    supported = set(report.supported_claim_ids)
    missing_claims = [claim for claim in case.required_claim_ids if claim not in supported]
    if missing_claims:
        failures.append(
            f"{case_id}: required_claim_ids expected={case.required_claim_ids!r} "
            f"actual={report.supported_claim_ids!r}"
        )
    missing_refs = [ref for ref in case.required_evidence_refs if ref not in report.evidence_refs]
    if missing_refs:
        failures.append(
            f"{case_id}: required_evidence_refs expected={case.required_evidence_refs!r} "
            f"actual={report.evidence_refs!r}"
        )
    forbidden_present = [claim for claim in case.forbidden_claim_ids if claim in supported]
    if forbidden_present:
        failures.append(
            f"{case_id}: forbidden_claim_ids expected_absent={case.forbidden_claim_ids!r} "
            f"actual={forbidden_present!r}"
        )
    return _scenario_result(
        case_id,
        failures,
        expected_decision,
        expected_reasons,
        case.required_claim_ids,
        report.supported_claim_ids,
        case.forbidden_claim_ids,
        case.required_evidence_refs,
        report.evidence_refs,
        expected_route,
        result,
        report,
    )


def _compare_common(
    case_id: str,
    result: PipelineResult,
    report: Any,
    expected_decision: str,
    expected_reasons: list[str],
    expected_question: Any,
    expected_route: dict[str, Any] | None,
    required_claims: list[str],
    forbidden_claims: list[str],
    required_refs: list[str],
) -> list[str]:
    failures: list[str] = []
    actual_decision = result.decision.value
    if actual_decision != expected_decision:
        failures.append(
            f"{case_id}: decision expected={expected_decision!r} actual={actual_decision!r}"
        )
    actual_reasons = [reason.value for reason in result.reason_codes]
    if actual_reasons != expected_reasons:
        failures.append(
            f"{case_id}: reason_codes expected={expected_reasons!r} actual={actual_reasons!r}"
        )
    if expected_question is not None and result.clarifying_question != expected_question:
        failures.append(
            f"{case_id}: clarifying_question expected={expected_question!r} "
            f"actual={result.clarifying_question!r}"
        )
    actual_route = result.route.model_dump(mode="json") if result.route else None
    if expected_route is None:
        if actual_route is not None:
            failures.append(f"{case_id}: route expected=None actual={actual_route!r}")
    elif actual_route is None:
        failures.append(f"{case_id}: route expected={expected_route!r} actual=None")
    else:
        for key, expected_value in expected_route.items():
            actual_value = actual_route.get(key)
            if actual_value != expected_value:
                failures.append(
                    f"{case_id}: route.{key} expected={expected_value!r} actual={actual_value!r}"
                )
    if report.reason_codes and actual_decision == Decision.ANSWER.value:
        failures.append(
            f"{case_id}: verification_reason_codes expected=[] actual={report.reason_codes!r}"
        )
    del required_claims, forbidden_claims, required_refs
    return failures


def _scenario_result(
    case_id: str,
    failures: list[str],
    expected_decision: str,
    expected_reasons: list[str],
    required_claims: list[str],
    supported_claims: list[str],
    forbidden_claims: list[str],
    required_refs: list[str],
    actual_refs: list[str],
    expected_route: dict[str, Any] | None,
    result: PipelineResult,
    report: Any,
) -> ScenarioResult:
    return ScenarioResult(
        id=case_id,
        matched=not failures,
        failures=failures,
        expected_decision=expected_decision,
        actual_decision=result.decision.value,
        expected_reason_codes=expected_reasons,
        actual_reason_codes=[reason.value for reason in result.reason_codes],
        required_claim_ids=required_claims,
        supported_claim_ids=supported_claims,
        forbidden_claim_ids=forbidden_claims,
        required_evidence_refs=required_refs,
        actual_evidence_refs=actual_refs,
        expected_route=expected_route,
        actual_route=result.route.model_dump(mode="json") if result.route else None,
        result={
            "result": result.model_dump(mode="json"),
            "verification": report.model_dump(mode="json"),
        },
    )


class M1Evaluator:
    """Run the five M0 regression cases plus seven M1 cases."""

    def __init__(self, config: Milestone1Config) -> None:
        self.config = config

    def run(self) -> M1EvaluationDocument:
        case_set = M1CaseSet.model_validate_json(
            self.config.evaluation_cases.read_text(encoding="utf-8")
        )
        if case_set.schema_version != "1.0":
            raise ValueError("Unsupported M1 evaluation case schema")
        if len(case_set.cases) != self.config.evaluation.expected_m1_cases:
            raise ValueError("M1 case count does not match config")

        self.config.generated_root.mkdir(parents=True, exist_ok=True)
        m0_pipeline, m0_provenance = self._m0_verified_pipeline()
        m1_pipeline = RiskonPipeline.from_milestone1_config(self.config)
        m1_provenance = m1_pipeline.verification_engine.provenance

        m0_raw = json.loads(
            (self.config.base.paths.data_root / "scenarios.json").read_text(encoding="utf-8")
        )
        if len(m0_raw) != self.config.evaluation.expected_m0_cases:
            raise ValueError("M0 case count does not match config")

        executions: list[_Execution] = []
        for raw in m0_raw:
            request = QueryInput(query=raw["query"], context=raw.get("context", {}))
            executions.append(
                _Execution(
                    case=raw,
                    verified=m0_pipeline.run_verified(request),
                    provenance=m0_provenance,
                    is_m0=True,
                )
            )
        for case in case_set.cases:
            executions.append(
                _Execution(
                    case=case,
                    verified=m1_pipeline.run_verified(
                        QueryInput(query=case.query, context=case.input_context)
                    ),
                    provenance=m1_provenance,
                    is_m0=False,
                )
            )

        scenario_results = [compare_case(execution) for execution in executions]
        metrics = self._metrics(executions, scenario_results)
        audit_ok, _ = validate_audit_file(self.config.generated_root / "audit.jsonl")
        return M1EvaluationDocument(
            schema_version="1.0",
            metrics=metrics,
            m0_regression={
                "expected": self.config.evaluation.expected_m0_cases,
                "matched": sum(1 for item in scenario_results[:5] if item.matched),
            },
            scenario_results=scenario_results,
            network_enabled=self.config.security.network_enabled,
            audit_schema_valid=audit_ok,
        )

    def _m0_verified_pipeline(self) -> tuple[RiskonPipeline, ProvenanceIndex]:
        runtime_config = self.config.base.model_copy(
            update={"audit": AuditConfig(path=self.config.generated_root / "audit.jsonl")}
        )
        pipeline = RiskonPipeline.from_config(runtime_config)
        provenance = ProvenanceIndex(
            pipeline.retriever.sections,
            knowledge_root=runtime_config.paths.data_root / "knowledge",
        )
        pipeline._verification_engine = VerificationEngine(
            provenance,
            pipeline.router,
            self.config.verification,
        )
        return pipeline, provenance

    def _metrics(
        self,
        executions: list[_Execution],
        scenario_results: list[ScenarioResult],
    ) -> M1Metrics:
        total = len(scenario_results)
        matched = sum(1 for item in scenario_results if item.matched)
        decision_correct = sum(
            1 for item in scenario_results if item.actual_decision == item.expected_decision
        )
        clarification_cases = [
            item for item in scenario_results if item.expected_decision == Decision.CLARIFY.value
        ]
        clarification_correct = sum(1 for item in clarification_cases if item.matched)
        expected_claims = sum(len(item.required_claim_ids) for item in scenario_results)
        returned_claims = sum(
            len(set(item.required_claim_ids) & set(item.supported_claim_ids))
            for item in scenario_results
        )
        critical_expected = sum(
            1
            for item in scenario_results
            if item.id == "M1-008"
            for _claim in ("do_not_proceed", "client_acceptance_does_not_override")
        )
        critical_returned = sum(
            1
            for item in scenario_results
            if item.id == "M1-008"
            for claim in ("do_not_proceed", "client_acceptance_does_not_override")
            if claim in item.supported_claim_ids
        )

        citation_total = 0
        citation_valid = 0
        route_total = 0
        route_function_correct = 0
        expert_total = 0
        expert_correct = 0
        scope_violations = 0
        unsupported_claims = 0
        unresolved_false_negatives = 0
        network_violations = 1 if self.config.security.network_enabled else 0
        for execution, item in zip(executions, scenario_results, strict=True):
            refs = execution.verified.verification.evidence_refs
            citation_total += len(refs)
            citation_valid += sum(
                1 for ref in refs if execution.provenance.resolve(ref) is not None
            )
            expected_route = item.expected_route
            if expected_route is not None:
                route_total += 1
                actual_route = item.actual_route or {}
                route_function_correct += int(
                    actual_route.get("support_function") == expected_route.get("support_function")
                )
                if expected_route.get("expert_id") is not None:
                    expert_total += 1
                    expert_correct += int(
                        actual_route.get("expert_id") == expected_route.get("expert_id")
                    )
            if (
                execution.verified.verification.scope_mismatches
                and item.actual_decision != Decision.ABSTAIN.value
            ):
                scope_violations += 1
            unsupported_claims += len(execution.verified.verification.unsupported_claim_ids)
            if (
                "UNRESOLVED_REQUIRED_REFERENCE" in item.expected_reason_codes
                and "UNRESOLVED_REQUIRED_REFERENCE" not in item.actual_reason_codes
            ):
                unresolved_false_negatives += 1
            network_violations += sum(
                1
                for ref in refs
                if not (
                    ref.startswith("local://synthetic/") or ref.startswith("local://synthetic-m1/")
                )
            )

        abstention_cases = [
            item for item in scenario_results if item.expected_decision == Decision.ABSTAIN.value
        ]
        answerable_cases = [
            item for item in scenario_results if item.expected_decision == Decision.ANSWER.value
        ]
        unnecessary_abstentions = sum(
            1 for item in answerable_cases if item.actual_decision == Decision.ABSTAIN.value
        )
        return M1Metrics(
            scenario_match_rate=_rate(matched, total),
            decision_accuracy=_rate(decision_correct, total),
            clarification_accuracy=_rate(clarification_correct, len(clarification_cases)),
            answer_case_claim_recall=_rate(returned_claims, expected_claims),
            critical_claim_recall=_rate(critical_returned, critical_expected),
            citation_validity=_rate(citation_valid, citation_total),
            route_function_accuracy=_rate(route_function_correct, route_total),
            route_expert_accuracy=_rate(expert_correct, expert_total),
            correct_abstention_rate=_rate(
                sum(
                    1 for item in abstention_cases if item.actual_decision == Decision.ABSTAIN.value
                ),
                len(abstention_cases),
            ),
            unnecessary_abstention_rate=_rate(unnecessary_abstentions, len(answerable_cases)),
            scope_violation_count=scope_violations,
            unsupported_claim_count=unsupported_claims,
            unresolved_reference_false_negative_count=unresolved_false_negatives,
            network_violation_count=network_violations,
        )


class M2PlanExpectation(BaseModel):
    """Frozen M2 query-plan expectation."""

    model_config = ConfigDict(extra="forbid")

    intent: QueryIntent
    normalised_query: str
    canonical_terms: list[str]
    required_context_fields: list[str]
    missing_context_fields: list[str]
    subqueries: list[str]
    retrieval_channels: list[RetrievalChannel]
    retrieval_skipped: bool


class M2RetrievalExpectation(BaseModel):
    """Frozen M2 retrieval expectation."""

    model_config = ConfigDict(extra="forbid")

    expected_top1_refs: list[str]
    required_refs_at_k: list[str]
    forbidden_refs: list[str]
    required_table_row_refs: list[str]
    forbidden_table_row_refs: list[str]


class M2ResultExpectation(BaseModel):
    """Frozen M2 decision/claim expectation."""

    model_config = ConfigDict(extra="forbid")

    decision: Decision
    reason_codes: list[str]
    clarifying_question: str | None
    required_claim_ids: list[str]
    forbidden_claim_ids: list[str]
    expected_route: dict[str, Any] | None


class M2Case(BaseModel):
    """One machine-readable M2 evaluation case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    query: str
    input_context: dict[str, str]
    expected_plan: M2PlanExpectation
    expected_retrieval: M2RetrievalExpectation
    expected_result: M2ResultExpectation


class M2CaseSet(BaseModel):
    """M2 case-file envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    cases: list[M2Case]


class M2ScenarioResult(BaseModel):
    """Human- and machine-readable result for one M2 case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    matched: bool
    failures: list[str]
    expected_decision: str
    actual_decision: str
    expected_reason_codes: list[str]
    actual_reason_codes: list[str]
    required_claim_ids: list[str]
    supported_claim_ids: list[str]
    forbidden_claim_ids: list[str]
    expected_top1_refs: list[str]
    actual_top1_refs: list[str]
    selected_evidence_refs: list[str]
    actual_final_refs: list[str]
    plan: dict[str, Any]
    result: dict[str, Any]


class M2Metrics(BaseModel):
    """Required M2 metric names and values."""

    model_config = ConfigDict(extra="forbid")

    m2_case_match_rate: float = Field(ge=0.0, le=1.0)
    query_plan_accuracy: float = Field(ge=0.0, le=1.0)
    retrieval_top1_accuracy: float = Field(ge=0.0, le=1.0)
    required_evidence_recall_at_5: float = Field(ge=0.0, le=1.0)
    subquery_coverage: float = Field(ge=0.0, le=1.0)
    table_row_recall: float = Field(ge=0.0, le=1.0)
    clarification_short_circuit_accuracy: float = Field(ge=0.0, le=1.0)
    forbidden_evidence_count: int = Field(ge=0)
    context_filter_violation_count: int = Field(ge=0)
    unsupported_claim_count: int = Field(ge=0)
    network_violation_count: int = Field(ge=0)


class M2EvaluationDocument(BaseModel):
    """Canonical M2 JSON report schema."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    metrics: M2Metrics
    m0_regression: dict[str, Any]
    m1_regression: dict[str, Any]
    scenario_results: list[M2ScenarioResult]
    network_enabled: bool
    audit_schema_valid: bool


@dataclass(frozen=True)
class _M2Comparison:
    """Internal M2 comparison values used to calculate aggregate metrics."""

    scenario: M2ScenarioResult
    plan_match: bool
    top1_matches: int
    top1_expected: int
    required_refs_found: int
    required_refs_total: int
    table_refs_found: int
    table_refs_total: int
    subquery_expected: int
    subquery_actual: int
    clarification_short_circuit: bool
    forbidden_evidence_count: int
    context_filter_violation_count: int
    unsupported_claim_count: int
    network_violation_count: int


class M2Evaluator:
    """Run M0/M1 regressions and the eight frozen M2 cases."""

    def __init__(self, config: Milestone2Config) -> None:
        self.config = config

    def run(self) -> M2EvaluationDocument:
        case_set = M2CaseSet.model_validate_json(
            self.config.evaluation_cases.read_text(encoding="utf-8")
        )
        if case_set.schema_version != "1.0":
            raise ValueError("Unsupported M2 evaluation case schema")
        if len(case_set.cases) != self.config.evaluation.expected_m2_new_cases:
            raise ValueError("M2 case count does not match config")

        m1_document = self._m1_regression()
        m2_pipeline = RiskonPipeline.from_milestone2_config(self.config)
        comparisons: list[_M2Comparison] = []
        for case in case_set.cases:
            request = QueryInput(query=case.query, context=case.input_context)
            planned = m2_pipeline.run_planned(request)
            comparisons.append(self._compare_case(case, planned))

        audit_ok, _ = validate_audit_file(self.config.generated_root / "audit.jsonl")
        metrics = self._metrics(comparisons)
        return M2EvaluationDocument(
            schema_version="1.0",
            metrics=metrics,
            m0_regression=m1_document.m0_regression,
            m1_regression={
                "expected": self.config.evaluation.expected_m1_new_cases,
                "matched": sum(1 for item in m1_document.scenario_results[5:] if item.matched),
            },
            scenario_results=[comparison.scenario for comparison in comparisons],
            network_enabled=self.config.security.network_enabled,
            audit_schema_valid=audit_ok,
        )

    def _m1_regression(self) -> M1EvaluationDocument:
        temp_root = Path(tempfile.mkdtemp(prefix="riskon-m2-m1-regression-"))
        m1_config = self.config.base.model_copy(update={"generated_root": temp_root})
        return M1Evaluator(m1_config).run()

    def _compare_case(self, case: M2Case, planned: PlannedVerifiedRun) -> _M2Comparison:
        plan = planned.query_plan
        verified = planned.verified_run
        result = verified.result
        report = verified.verification
        expected_plan = case.expected_plan
        expected_retrieval = case.expected_retrieval
        expected_result = case.expected_result
        failures: list[str] = []

        plan_match = all(
            (
                plan.intent == expected_plan.intent,
                plan.normalised_query == expected_plan.normalised_query,
                plan.canonical_terms == expected_plan.canonical_terms,
                plan.required_context_fields == expected_plan.required_context_fields,
                plan.missing_context_fields == expected_plan.missing_context_fields,
                plan.subqueries == expected_plan.subqueries,
                plan.retrieval_channels == expected_plan.retrieval_channels,
                plan.retrieval_skipped == expected_plan.retrieval_skipped,
            )
        )
        if not plan_match:
            failures.append(
                f"{case.id}: plan expected={expected_plan.model_dump(mode='json')!r} "
                f"actual={plan.model_dump(mode='json', exclude={'plan_id'})!r}"
            )

        subqueries = [] if plan.retrieval_skipped else plan.subqueries or [plan.normalised_query]
        actual_final_refs = [
            candidate.candidate_ref
            for subquery in subqueries
            for candidate in self._final_candidates(planned, subquery)
        ]
        actual_top1_refs = [
            self._final_candidates(planned, subquery)[0].candidate_ref
            if self._final_candidates(planned, subquery)
            else ""
            for subquery in subqueries
        ]
        top1_expected = len(expected_retrieval.expected_top1_refs)
        top1_matches = sum(
            actual == expected
            for actual, expected in zip(
                actual_top1_refs,
                expected_retrieval.expected_top1_refs,
                strict=False,
            )
        )
        if actual_top1_refs != expected_retrieval.expected_top1_refs:
            failures.append(
                f"{case.id}: top1 expected={expected_retrieval.expected_top1_refs!r} "
                f"actual={actual_top1_refs!r}"
            )

        top5_refs = [
            candidate.candidate_ref
            for subquery in subqueries
            for candidate in self._final_candidates(planned, subquery)[:5]
        ]
        required_refs_found = sum(ref in top5_refs for ref in expected_retrieval.required_refs_at_k)
        required_refs_total = len(expected_retrieval.required_refs_at_k)
        if required_refs_found != required_refs_total:
            missing_required_refs = [
                ref for ref in expected_retrieval.required_refs_at_k if ref not in top5_refs
            ]
            failures.append(f"{case.id}: required_refs_at_k missing={missing_required_refs!r}")
        actual_table_refs = {ref for ref in actual_final_refs if ":table-" in ref}
        required_table_refs = set(expected_retrieval.required_table_row_refs)
        forbidden_table_refs = set(expected_retrieval.forbidden_table_row_refs)
        table_refs_found = len(actual_table_refs & required_table_refs)
        table_refs_total = len(required_table_refs)
        if actual_table_refs & forbidden_table_refs:
            failures.append(f"{case.id}: forbidden table rows entered final candidates")

        supported_claims = set(report.supported_claim_ids)
        required_claims = set(expected_result.required_claim_ids)
        forbidden_claims = set(expected_result.forbidden_claim_ids)
        if not required_claims.issubset(supported_claims):
            failures.append(
                f"{case.id}: required claims missing={sorted(required_claims - supported_claims)!r}"
            )
        if supported_claims & forbidden_claims:
            forbidden_claims_present = sorted(supported_claims & forbidden_claims)
            failures.append(f"{case.id}: forbidden claims present={forbidden_claims_present!r}")
        actual_reasons = [reason.value for reason in result.reason_codes]
        if result.decision.value != expected_result.decision.value:
            failures.append(f"{case.id}: decision mismatch")
        if actual_reasons != expected_result.reason_codes:
            failures.append(
                f"{case.id}: reasons expected={expected_result.reason_codes!r} "
                f"actual={actual_reasons!r}"
            )
        if result.clarifying_question != expected_result.clarifying_question:
            failures.append(f"{case.id}: clarifying question mismatch")
        actual_route = result.route.model_dump(mode="json") if result.route else None
        if actual_route != expected_result.expected_route:
            failures.append(f"{case.id}: route mismatch")

        selected_refs = [item.source_ref for item in result.evidence]
        forbidden_evidence = (
            (set(selected_refs) & set(expected_retrieval.forbidden_refs))
            | (actual_table_refs & forbidden_table_refs)
            | (supported_claims & forbidden_claims)
        )
        context_filter_violations = (
            len(set(actual_final_refs) & set(expected_retrieval.forbidden_refs))
            if plan.intent is QueryIntent.APPLICABILITY
            else 0
        )
        clarification_short_circuit = (
            result.decision is Decision.CLARIFY
            and plan.retrieval_skipped
            and not planned.retrieval_diagnostics.entries
        )
        network_refs = set(actual_final_refs) | set(report.evidence_refs)
        network_violation_count = sum(
            not ref.startswith("local://synthetic-m2/") for ref in network_refs
        )
        scenario = M2ScenarioResult(
            id=case.id,
            matched=not failures,
            failures=failures,
            expected_decision=expected_result.decision.value,
            actual_decision=result.decision.value,
            expected_reason_codes=expected_result.reason_codes,
            actual_reason_codes=actual_reasons,
            required_claim_ids=expected_result.required_claim_ids,
            supported_claim_ids=report.supported_claim_ids,
            forbidden_claim_ids=expected_result.forbidden_claim_ids,
            expected_top1_refs=expected_retrieval.expected_top1_refs,
            actual_top1_refs=actual_top1_refs,
            selected_evidence_refs=selected_refs,
            actual_final_refs=actual_final_refs,
            plan=plan.model_dump(mode="json"),
            result={
                "verified_run": verified.model_dump(mode="json"),
                "diagnostics": planned.retrieval_diagnostics.model_dump(mode="json"),
            },
        )
        return _M2Comparison(
            scenario=scenario,
            plan_match=plan_match,
            top1_matches=top1_matches,
            top1_expected=top1_expected,
            required_refs_found=required_refs_found,
            required_refs_total=required_refs_total,
            table_refs_found=table_refs_found,
            table_refs_total=table_refs_total,
            subquery_expected=len(expected_plan.subqueries),
            subquery_actual=len(plan.subqueries),
            clarification_short_circuit=clarification_short_circuit,
            forbidden_evidence_count=len(forbidden_evidence),
            context_filter_violation_count=context_filter_violations,
            unsupported_claim_count=len(report.unsupported_claim_ids),
            network_violation_count=network_violation_count,
        )

    @staticmethod
    def _final_candidates(
        planned: PlannedVerifiedRun,
        subquery: str,
    ) -> list[Any]:
        by_ref: dict[str, Any] = {}
        for entry in planned.retrieval_diagnostics.entries:
            if not entry.included or entry.subquery != subquery:
                continue
            current = by_ref.get(entry.candidate_ref)
            if current is None or (entry.final_rank or 10**9) < (current.final_rank or 10**9):
                by_ref[entry.candidate_ref] = entry
        return sorted(
            by_ref.values(),
            key=lambda item: (item.final_rank or 10**9, item.candidate_ref),
        )

    def _metrics(self, comparisons: list[_M2Comparison]) -> M2Metrics:
        total = len(comparisons)
        top1_expected = sum(item.top1_expected for item in comparisons)
        top1_matches = sum(item.top1_matches for item in comparisons)
        required_total = sum(item.required_refs_total for item in comparisons)
        required_found = sum(item.required_refs_found for item in comparisons)
        table_total = sum(item.table_refs_total for item in comparisons)
        table_found = sum(item.table_refs_found for item in comparisons)
        subquery_expected = sum(item.subquery_expected for item in comparisons)
        subquery_actual = sum(item.subquery_actual for item in comparisons)
        short_circuit_cases = [item for item in comparisons if item.scenario.id == "M2-017"]
        return M2Metrics(
            m2_case_match_rate=_rate(sum(item.scenario.matched for item in comparisons), total),
            query_plan_accuracy=_rate(sum(item.plan_match for item in comparisons), total),
            retrieval_top1_accuracy=_rate(top1_matches, top1_expected),
            required_evidence_recall_at_5=_rate(required_found, required_total),
            subquery_coverage=_rate(min(subquery_actual, subquery_expected), subquery_expected),
            table_row_recall=_rate(table_found, table_total),
            clarification_short_circuit_accuracy=_rate(
                sum(item.clarification_short_circuit for item in short_circuit_cases),
                len(short_circuit_cases),
            ),
            forbidden_evidence_count=sum(item.forbidden_evidence_count for item in comparisons),
            context_filter_violation_count=sum(
                item.context_filter_violation_count for item in comparisons
            ),
            unsupported_claim_count=sum(item.unsupported_claim_count for item in comparisons),
            network_violation_count=sum(item.network_violation_count for item in comparisons)
            + int(self.config.security.network_enabled),
        )


class M3Case(BaseModel):
    """One fixture-backed M3 routing case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_scenario_id: str
    source_scenario_role: str
    upstream_fixture_ref: str
    routing_profile: str
    routing_context: RoutingContext
    expected_legacy_route_function: str
    expected_route: dict[str, Any]
    expected_candidates: dict[str, Any]
    expected_explanation: dict[str, Any]


class M3CaseSet(BaseModel):
    """M3 evaluation contract envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    cases: list[M3Case]


class M3FixtureEnvelope(BaseModel):
    """Schema-validated frozen upstream run fixture."""

    model_config = ConfigDict(extra="forbid")

    fixture_schema_version: str
    fixture_origin: str
    source_scenario_id: str
    planned_verified_run: PlannedVerifiedRun


class M3ScenarioResult(BaseModel):
    """Case-level M3 routing result and diagnostics."""

    model_config = ConfigDict(extra="forbid")

    id: str
    matched: bool
    failures: list[str]
    expected_decision: str
    actual_decision: str
    expected_route: dict[str, Any]
    actual_route: dict[str, Any] | None
    candidate_expert_ids: list[str]
    routing_status: str
    legacy_route_function: str | None
    result: dict[str, Any]


class M3Metrics(BaseModel):
    """Exact M3 acceptance metric names."""

    model_config = ConfigDict(extra="forbid")

    m3_case_match_rate: float = Field(ge=0.0, le=1.0)
    support_function_accuracy: float = Field(ge=0.0, le=1.0)
    person_or_queue_selection_accuracy: float = Field(ge=0.0, le=1.0)
    candidate_top3_recall: float = Field(ge=0.0, le=1.0)
    routing_explanation_completeness: float = Field(ge=0.0, le=1.0)
    routing_confidence_contract_accuracy: float = Field(ge=0.0, le=1.0)
    legacy_route_consistency: float = Field(ge=0.0, le=1.0)
    support_model_hot_swap_accuracy: float = Field(ge=0.0, le=1.0)
    hard_constraint_violation_count: int = Field(ge=0)
    mandate_violation_count: int = Field(ge=0)
    jurisdiction_violation_count: int = Field(ge=0)
    region_violation_count: int = Field(ge=0)
    system_violation_count: int = Field(ge=0)
    inactive_expert_selection_count: int = Field(ge=0)
    unavailable_expert_selection_count: int = Field(ge=0)
    raw_query_dependency_count: int = Field(ge=0)
    network_violation_count: int = Field(ge=0)


class M3EvaluationDocument(BaseModel):
    """Canonical M3 evaluation report schema."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    metrics: M3Metrics
    m0_regression: dict[str, Any]
    m1_regression: dict[str, Any]
    m2_regression: dict[str, Any]
    scenario_results: list[M3ScenarioResult]
    network_enabled: bool
    audit_schema_valid: bool


@dataclass(frozen=True)
class _M3Comparison:
    """Internal M3 case comparison and acceptance counters."""

    scenario: M3ScenarioResult
    support_function_correct: bool
    person_or_queue_correct: bool
    candidate_recall: bool
    explanation_complete: bool
    confidence_contract_correct: bool
    legacy_consistent: bool
    hot_swap_correct: bool
    hard_constraint_violations: int
    mandate_violations: int
    jurisdiction_violations: int
    region_violations: int
    system_violations: int
    inactive_selections: int
    unavailable_selections: int
    raw_query_dependencies: int
    network_violations: int


class M3Evaluator:
    """Evaluate routing from frozen PlannedVerifiedRun fixtures only."""

    def __init__(self, config: Milestone3Config) -> None:
        self.config = config

    def run(self) -> M3EvaluationDocument:
        case_set = M3CaseSet.model_validate_json(
            self.config.evaluation_cases.read_text(encoding="utf-8")
        )
        if case_set.schema_version != "1.1":
            raise ValueError("Unsupported M3 evaluation case schema")
        if len(case_set.cases) != self.config.evaluation.expected_m3_new_cases:
            raise ValueError("M3 case count does not match config")

        m2_document = self._m2_regression()
        pipeline = RiskonPipeline.from_milestone3_config(self.config)
        self.config.generated_root.mkdir(parents=True, exist_ok=True)
        audit_path = self.config.generated_root / "audit.jsonl"
        if audit_path.exists():
            audit_path.unlink()
        audit_logger = AuditLogger(audit_path)
        comparisons: list[_M3Comparison] = []
        for case in case_set.cases:
            fixture = self._load_fixture(case)
            planned = fixture.planned_verified_run
            before = planned.model_dump(mode="json")
            routed = pipeline.route_planned(
                planned,
                case.routing_context,
                case.routing_profile,
            )
            audit_logger.append(
                QueryInput(query=planned.query_plan.original_query),
                planned.verified_run.result,
            )
            comparisons.append(self._compare_case(case, routed, before))

        audit_ok, _ = validate_audit_file(audit_path)
        metrics = self._metrics(comparisons)
        return M3EvaluationDocument(
            schema_version="1.0",
            metrics=metrics,
            m0_regression=m2_document.m0_regression,
            m1_regression=m2_document.m1_regression,
            m2_regression={
                "expected": self.config.evaluation.expected_m2_new_cases,
                "matched": sum(item.matched for item in m2_document.scenario_results),
            },
            scenario_results=[item.scenario for item in comparisons],
            network_enabled=self.config.security.network_enabled,
            audit_schema_valid=audit_ok,
        )

    def _m2_regression(self) -> M2EvaluationDocument:
        temp_root = Path(tempfile.mkdtemp(prefix="riskon-m3-m2-regression-"))
        m2_config = self.config.base.model_copy(update={"generated_root": temp_root})
        return M2Evaluator(m2_config).run()

    def _load_fixture(self, case: M3Case) -> M3FixtureEnvelope:
        prefix = "local://synthetic-m3/upstream-runs/"
        if not case.upstream_fixture_ref.startswith(prefix):
            raise ValueError(f"Invalid M3 fixture reference: {case.upstream_fixture_ref}")
        fixture_path = (
            self.config.evaluation_cases.parent
            / "upstream_runs"
            / case.upstream_fixture_ref.removeprefix(prefix)
        )
        fixture = M3FixtureEnvelope.model_validate_json(fixture_path.read_text(encoding="utf-8"))
        if fixture.fixture_schema_version != "1.0":
            raise ValueError("Unsupported M3 upstream fixture schema")
        if fixture.fixture_origin != "SYNTHETIC_ROUTING_FIXTURE_V1":
            raise ValueError("Unexpected M3 upstream fixture origin")
        if fixture.source_scenario_id != case.source_scenario_id:
            raise ValueError(f"{case.id}: fixture lineage does not match case")
        return fixture

    def _compare_case(
        self,
        case: M3Case,
        routed: RoutedRun,
        before: dict[str, Any],
    ) -> _M3Comparison:
        result = routed.planned_verified_run.verified_run.result
        route = routed.expert_route
        route_payload = route.model_dump(mode="json") if route else None
        failures: list[str] = []
        if routed.planned_verified_run.model_dump(mode="json") != before:
            failures.append(f"{case.id}: planned_verified_run was mutated")
        if result.decision.value != "ABSTAIN":
            failures.append(f"{case.id}: fixture decision was not ABSTAIN")
        if route is None:
            failures.append(f"{case.id}: expert_route missing")
        expected_route = case.expected_route
        if route_payload is None:
            person_or_queue_correct = False
        else:
            person_or_queue_correct = all(
                route_payload.get(key) == expected_value
                for key, expected_value in expected_route.items()
            )
            if not person_or_queue_correct:
                failures.append(
                    f"{case.id}: route expected={expected_route!r} actual={route_payload!r}"
                )

        support_function_correct = (
            route is not None and route.support_function == expected_route.get("support_function")
        )
        if not support_function_correct:
            failures.append(f"{case.id}: support function mismatch")

        candidate_ids = route.candidate_expert_ids if route is not None else []
        required_candidates = case.expected_candidates.get("required_top3_ids", [])
        candidate_recall = all(item in candidate_ids[:3] for item in required_candidates)
        if not candidate_recall:
            failures.append(
                f"{case.id}: candidate top3 expected={required_candidates!r} "
                f"actual={candidate_ids!r}"
            )
        forbidden_selected = set(case.expected_candidates.get("forbidden_selected_ids", []))
        if route is not None and route.selected_expert_id in forbidden_selected:
            failures.append(f"{case.id}: forbidden expert selected")

        diagnostics_by_id = {item.expert_id: item for item in routed.routing_diagnostics.candidates}
        for required in case.expected_candidates.get("required_exclusions", []):
            candidate = diagnostics_by_id.get(required["expert_id"])
            if candidate is None or candidate.exclusion_reason != required["reason"]:
                failures.append(
                    f"{case.id}: required exclusion missing={required!r} actual="
                    f"{candidate.exclusion_reason if candidate else None!r}"
                )

        explanation_complete = False
        if route is not None:
            explanation = route.explanation.model_dump(mode="json")
            required_fields = set(case.expected_explanation.get("required_fields", []))
            required_factors = set(case.expected_explanation.get("required_decisive_factors", []))
            explanation_complete = required_fields <= set(explanation) and required_factors <= set(
                route.explanation.decisive_factors
            )
        if not explanation_complete:
            failures.append(f"{case.id}: routing explanation incomplete")

        legacy_function = result.route.support_function if result.route else None
        legacy_consistent = legacy_function == case.expected_legacy_route_function and (
            route is not None and route.support_function == legacy_function
        )
        if not legacy_consistent:
            failures.append(f"{case.id}: legacy route conflict")

        confidence_contract_correct = self._confidence_contract(route, routed)
        if not confidence_contract_correct:
            failures.append(f"{case.id}: routing confidence contract mismatch")

        selected_diagnostic = None
        if route is not None and route.selected_expert_id is not None:
            selected_diagnostic = diagnostics_by_id.get(route.selected_expert_id)
        hard_constraint_violations = int(
            selected_diagnostic is not None and not selected_diagnostic.eligible
        )
        selected_reason = selected_diagnostic.exclusion_reason if selected_diagnostic else None
        mandate_violations = int(selected_reason == "MANDATE_MISMATCH")
        jurisdiction_violations = int(selected_reason == "JURISDICTION_CONFLICT")
        region_violations = int(selected_reason == "REGION_CONFLICT")
        system_violations = int(selected_reason == "SYSTEM_CONFLICT")
        inactive_selections = int(selected_reason == "INACTIVE_PROFILE")
        unavailable_selections = int(selected_reason == "NOT_ACCEPTING_CASES")
        request_payload = (
            routed.routing_diagnostics.routing_request.model_dump(mode="json")
            if (routed.routing_diagnostics.routing_request is not None)
            else {}
        )
        forbidden_query_fields = {
            "original_query",
            "normalised_query",
            "answer_text",
            "retrieved_raw_text",
        }
        raw_query_dependencies = int(bool(forbidden_query_fields & set(request_payload)))
        network_violations = int(
            self.config.security.network_enabled
            or "http://" in json.dumps(routed.routing_diagnostics.model_dump(mode="json"))
            or "https://" in json.dumps(routed.routing_diagnostics.model_dump(mode="json"))
        )
        hot_swap_correct = case.id != "M3-028" or (
            route is not None
            and route.support_model_version == "m3-v2"
            and route.selected_expert_id == "SYN3-BRM-BETA-002"
        )
        if not hot_swap_correct:
            failures.append(f"{case.id}: support-model hot swap mismatch")

        scenario = M3ScenarioResult(
            id=case.id,
            matched=not failures,
            failures=failures,
            expected_decision="ABSTAIN",
            actual_decision=result.decision.value,
            expected_route=expected_route,
            actual_route=route_payload,
            candidate_expert_ids=candidate_ids,
            routing_status=routed.routing_diagnostics.status.value,
            legacy_route_function=legacy_function,
            result={
                "routed_run": routed.model_dump(mode="json"),
                "fixture_source_scenario_id": case.source_scenario_id,
            },
        )
        return _M3Comparison(
            scenario=scenario,
            support_function_correct=support_function_correct,
            person_or_queue_correct=person_or_queue_correct,
            candidate_recall=candidate_recall,
            explanation_complete=explanation_complete,
            confidence_contract_correct=confidence_contract_correct,
            legacy_consistent=legacy_consistent,
            hot_swap_correct=hot_swap_correct,
            hard_constraint_violations=hard_constraint_violations,
            mandate_violations=mandate_violations,
            jurisdiction_violations=jurisdiction_violations,
            region_violations=region_violations,
            system_violations=system_violations,
            inactive_selections=inactive_selections,
            unavailable_selections=unavailable_selections,
            raw_query_dependencies=raw_query_dependencies,
            network_violations=network_violations,
        )

    def _confidence_contract(
        self,
        route: ExpertRoute | None,
        routed: RoutedRun,
    ) -> bool:
        if route is None:
            return False
        if route.confidence_kind != self.config.routing.confidence_kind:
            return False
        if route.route_mode is RouteMode.FUNCTIONAL_QUEUE:
            return route.routing_confidence == self.config.routing.functional_queue_confidence
        eligible = sorted(
            [item for item in routed.routing_diagnostics.candidates if item.eligible],
            key=lambda item: item.rank or 10**9,
        )
        if not eligible:
            return False
        top_score = eligible[0].total_score or 0.0
        margin = top_score if len(eligible) == 1 else top_score - (eligible[1].total_score or 0.0)
        expected = round(0.70 * top_score + 0.30 * min(1.0, margin / 0.25), 3)
        return route.routing_confidence == expected

    def _metrics(self, comparisons: list[_M3Comparison]) -> M3Metrics:
        total = len(comparisons)
        return M3Metrics(
            m3_case_match_rate=_rate(sum(item.scenario.matched for item in comparisons), total),
            support_function_accuracy=_rate(
                sum(item.support_function_correct for item in comparisons), total
            ),
            person_or_queue_selection_accuracy=_rate(
                sum(item.person_or_queue_correct for item in comparisons), total
            ),
            candidate_top3_recall=_rate(sum(item.candidate_recall for item in comparisons), total),
            routing_explanation_completeness=_rate(
                sum(item.explanation_complete for item in comparisons), total
            ),
            routing_confidence_contract_accuracy=_rate(
                sum(item.confidence_contract_correct for item in comparisons), total
            ),
            legacy_route_consistency=_rate(
                sum(item.legacy_consistent for item in comparisons), total
            ),
            support_model_hot_swap_accuracy=_rate(
                sum(item.hot_swap_correct for item in comparisons if item.scenario.id == "M3-028"),
                1,
            ),
            hard_constraint_violation_count=sum(
                item.hard_constraint_violations for item in comparisons
            ),
            mandate_violation_count=sum(item.mandate_violations for item in comparisons),
            jurisdiction_violation_count=sum(item.jurisdiction_violations for item in comparisons),
            region_violation_count=sum(item.region_violations for item in comparisons),
            system_violation_count=sum(item.system_violations for item in comparisons),
            inactive_expert_selection_count=sum(item.inactive_selections for item in comparisons),
            unavailable_expert_selection_count=sum(
                item.unavailable_selections for item in comparisons
            ),
            raw_query_dependency_count=sum(item.raw_query_dependencies for item in comparisons),
            network_violation_count=sum(item.network_violations for item in comparisons),
        )


class M4ACase(BaseModel):
    """One selected case from the frozen M4 orchestra evaluation set."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    baseline_fixture_ref: str
    baseline_fixture_role: str
    activation_profile: ActivationProfile
    risk_signals: list[RiskSignal]
    expected_agent_roles: list[str]
    expected_task_count: int = Field(ge=0)
    required_findings: list[dict[str, Any]]
    required_material_objections: list[dict[str, Any]]
    forbidden_material_objections: list[str]
    expected_counterfactuals: list[dict[str, Any]]
    expected_final: dict[str, Any]
    expected_route: dict[str, Any] | None
    required_evidence_refs: list[str]
    forbidden_evidence_refs: list[str]
    case_capsule_required: bool


class M4ACaseSet(BaseModel):
    """Frozen M4 case-set envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    milestone: str
    cases: list[M4ACase]


class M4AFixtureEnvelope(BaseModel):
    """Schema-validated frozen M4 upstream input wrapper."""

    model_config = ConfigDict(extra="forbid")

    fixture_schema_version: str
    fixture_origin: str
    case_id: str
    planned_verified_run: PlannedVerifiedRun


class M4AScenarioResult(BaseModel):
    """Safe case-level M4A result summary without raw query/source text."""

    model_config = ConfigDict(extra="forbid")

    id: str
    matched: bool
    failures: list[str]
    expected_profile: str
    actual_profile: str | None
    expected_decision: str
    actual_decision: str | None
    actual_reason_codes: list[str]
    expected_route: dict[str, Any] | None
    actual_route: dict[str, Any] | None
    route_mode: str | None
    case_capsule_id: str | None
    active_agent_count: int
    worker_execution_count: int
    baseline_unchanged: bool
    result: dict[str, Any]


class M4AMetrics(BaseModel):
    """M4A acceptance metrics, including explicit zero-worker counters."""

    model_config = ConfigDict(extra="forbid")

    m4a_case_match_rate: float = Field(ge=0.0, le=1.0)
    fast_path_accuracy: float = Field(ge=0.0, le=1.0)
    short_circuit_clarify_accuracy: float = Field(ge=0.0, le=1.0)
    human_first_accuracy: float = Field(ge=0.0, le=1.0)
    active_agent_count: int = Field(ge=0)
    worker_execution_count: int = Field(ge=0)
    baseline_mutation_count: int = Field(ge=0)
    network_violation_count: int = Field(ge=0)


class M4AEvaluationDocument(BaseModel):
    """Canonical M4A evaluation report schema."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    metrics: M4AMetrics
    m0_regression: dict[str, Any]
    m1_regression: dict[str, Any]
    m2_regression: dict[str, Any]
    m3_regression: dict[str, Any]
    scenario_results: list[M4AScenarioResult]
    network_enabled: bool
    audit_schema_valid: bool


@dataclass(frozen=True)
class _M4AComparison:
    """Internal M4A comparison counters."""

    scenario: M4AScenarioResult
    profile: ActivationProfile
    baseline_mutated: bool
    network_violations: int


class M4AEvaluator:
    """Evaluate M4A only from frozen upstream ``PlannedVerifiedRun`` fixtures."""

    def __init__(self, config: Milestone4AConfig) -> None:
        self.config = config

    def run(self) -> M4AEvaluationDocument:
        """Run the five configured zero-worker cases and M0-M3 regressions."""

        case_set = M4ACaseSet.model_validate_json(
            self.config.orchestra.evaluation_cases.read_text(encoding="utf-8")
        )
        if case_set.schema_version != "1.0" or case_set.milestone != "M4_ORCHESTRA_CONTRACT":
            raise ValueError("Unsupported M4 evaluation case schema")
        cases_by_id = {case.id: case for case in case_set.cases}
        included_ids = self.config.evaluation.included_cases
        if len(included_ids) != self.config.evaluation.expected_cases:
            raise ValueError("M4A included case count does not match config")
        if len(set(included_ids)) != len(included_ids) or any(
            case_id not in cases_by_id for case_id in included_ids
        ):
            raise ValueError("M4A included cases are not present in the frozen case set")
        cases = [cases_by_id[case_id] for case_id in included_ids]

        policy = ActivationPolicy.from_file(self.config.orchestra.activation_policy)
        for case in cases:
            policy.profile(case.activation_profile)
            policy.validate_risk_signals(tuple(case.risk_signals))
        m3_document = self._m3_regression()
        pipeline = RiskonPipeline.from_milestone4a_config(self.config)
        self.config.orchestra.generated_root.mkdir(parents=True, exist_ok=True)
        audit_path = self.config.orchestra.generated_root / "audit.jsonl"
        if audit_path.exists():
            audit_path.unlink()

        comparisons: list[_M4AComparison] = []
        for case in cases:
            fixture = self._load_fixture(case)
            planned = fixture.planned_verified_run
            before = planned.model_dump(mode="json")
            try:
                context = self._context(case, planned)
                orchestra = pipeline.orchestrate_planned(
                    planned,
                    context,
                    case.activation_profile.value,
                )
                comparisons.append(self._compare_case(case, orchestra, before))
            except Exception as exc:
                comparisons.append(self._failed_comparison(case, planned, before, str(exc)))

        audit_ok, _ = validate_m4a_audit_file(audit_path)
        metrics = self._metrics(comparisons)
        m3_matched = sum(item.matched for item in m3_document.scenario_results)
        return M4AEvaluationDocument(
            schema_version="1.0",
            metrics=metrics,
            m0_regression=m3_document.m0_regression,
            m1_regression=m3_document.m1_regression,
            m2_regression=m3_document.m2_regression,
            m3_regression={
                "expected": self.config.base.evaluation.expected_m3_new_cases,
                "matched": m3_matched,
            },
            scenario_results=[item.scenario for item in comparisons],
            network_enabled=self.config.security.network_enabled,
            audit_schema_valid=audit_ok,
        )

    def _m3_regression(self) -> M3EvaluationDocument:
        temp_root = Path(tempfile.mkdtemp(prefix="riskon-m4a-m3-regression-"))
        m3_config = self.config.base.model_copy(update={"generated_root": temp_root})
        return M3Evaluator(m3_config).run()

    def _load_fixture(self, case: M4ACase) -> M4AFixtureEnvelope:
        prefix = "local://synthetic-m4/upstream-runs/"
        if not case.baseline_fixture_ref.startswith(prefix):
            raise ValueError(f"Invalid M4 fixture reference: {case.baseline_fixture_ref}")
        filename = case.baseline_fixture_ref.removeprefix(prefix)
        if "/" in filename or "\\" in filename:
            raise ValueError(f"M4 fixture reference must name one upstream file: {filename}")
        fixture_path = self.config.orchestra.upstream_runs_root / filename
        fixture = M4AFixtureEnvelope.model_validate_json(fixture_path.read_text(encoding="utf-8"))
        if fixture.fixture_schema_version != "1.0":
            raise ValueError("Unsupported M4 upstream fixture schema")
        if fixture.fixture_origin != "SYNTHETIC_ORCHESTRA_BASELINE_V1":
            raise ValueError("Unexpected M4 upstream fixture origin")
        if fixture.case_id != case.id:
            raise ValueError(f"{case.id}: fixture lineage does not match case")
        return fixture

    @staticmethod
    def _context(case: M4ACase, planned: PlannedVerifiedRun) -> OrchestraContext:
        result = planned.verified_run.result
        routing_context: RoutingContext | None = None
        if case.activation_profile is ActivationProfile.HUMAN_FIRST:
            routing_context = RoutingContext(
                need_type=result.detected_context.need_type,
                reason_codes=list(result.reason_codes),
                topics=[],
                jurisdiction=None,
                region=result.detected_context.region,
                system=None,
                requester_team=None,
            )
        return OrchestraContext(
            risk_signals=tuple(case.risk_signals),
            routing_context=routing_context,
            routing_profile="default",
        )

    def _compare_case(
        self,
        case: M4ACase,
        orchestra: OrchestraRun,
        before: dict[str, Any],
    ) -> _M4AComparison:
        result = orchestra.final_verified_run.result
        expected_final = case.expected_final
        failures: list[str] = []
        baseline_unchanged = orchestra.baseline_run.model_dump(
            mode="json"
        ) == before and orchestra.final_verified_run.model_dump(
            mode="json"
        ) == orchestra.baseline_run.verified_run.model_dump(mode="json")
        if not baseline_unchanged:
            failures.append(f"{case.id}: baseline or final verified run changed")
        if orchestra.activation_profile is not case.activation_profile:
            failures.append(f"{case.id}: activation profile mismatch")
        if list(map(str, orchestra.risk_signals)) != list(map(str, case.risk_signals)):
            failures.append(f"{case.id}: risk signal mismatch")

        metrics = orchestra.orchestra_metrics
        if any(
            (
                metrics.active_agent_count,
                metrics.task_count,
                metrics.finding_count,
                metrics.candidate_claim_count,
                metrics.material_objection_count,
                metrics.counterfactual_count,
                metrics.worker_execution_count,
            )
        ):
            failures.append(f"{case.id}: M4A zero-worker metrics are non-zero")
        if any(
            (
                orchestra.agent_tasks,
                orchestra.findings,
                orchestra.candidate_claims,
                orchestra.material_objections,
                orchestra.counterfactual_results,
            )
        ):
            failures.append(f"{case.id}: M4A worker collections are not empty")

        expected_decision = str(expected_final.get("decision"))
        actual_decision = result.decision.value
        if actual_decision != expected_decision:
            failures.append(
                f"{case.id}: decision expected={expected_decision!r} actual={actual_decision!r}"
            )
        actual_reasons = [reason.value for reason in result.reason_codes]
        expected_reasons = [str(reason) for reason in expected_final.get("reason_codes", [])]
        if actual_reasons != expected_reasons:
            failures.append(f"{case.id}: reason codes mismatch")
        answer_required = expected_final.get("answer_required")
        if answer_required is True and result.answer is None:
            failures.append(f"{case.id}: answer was required")
        if answer_required is False and result.answer is not None:
            failures.append(f"{case.id}: answer was not allowed")
        if "clarifying_question" in expected_final and (
            result.clarifying_question != expected_final["clarifying_question"]
        ):
            failures.append(f"{case.id}: clarification mismatch")

        required_claims = set(expected_final.get("required_claim_ids", []))
        supported_claims = set(orchestra.final_verified_run.verification.supported_claim_ids)
        if not required_claims.issubset(supported_claims):
            failures.append(f"{case.id}: required claims missing")
        forbidden_claims = set(expected_final.get("forbidden_claim_ids", []))
        if supported_claims & forbidden_claims:
            failures.append(f"{case.id}: forbidden claims present")

        actual_route = self._route_summary(orchestra)
        if case.expected_route is None:
            if actual_route is not None or orchestra.routed_run is not None:
                failures.append(f"{case.id}: unexpected route")
        else:
            if actual_route is None or orchestra.routed_run is None:
                failures.append(f"{case.id}: expected HUMAN_FIRST route")
            else:
                if actual_route.get("support_function") != case.expected_route.get(
                    "support_function"
                ):
                    failures.append(f"{case.id}: support function mismatch")
                expected_selected = case.expected_route.get("selected_expert_id")
                if (
                    expected_selected is not None
                    and actual_route.get("selected_expert_id") != expected_selected
                ):
                    failures.append(f"{case.id}: selected expert mismatch")
        if case.case_capsule_required != (orchestra.case_capsule is not None):
            failures.append(f"{case.id}: case capsule requirement mismatch")
        if (
            case.case_capsule_required
            and orchestra.case_capsule is not None
            and case.expected_route is not None
        ):
            if orchestra.case_capsule.support_function != case.expected_route.get(
                "support_function"
            ):
                failures.append(f"{case.id}: capsule support function mismatch")
            if orchestra.case_capsule.baseline_trace_id != result.trace_id:
                failures.append(f"{case.id}: capsule baseline trace mismatch")

        evidence_refs = set(orchestra.final_verified_run.verification.evidence_refs)
        evidence_refs.update(item.source_ref for item in result.evidence)
        evidence_refs.update(item.source_ref for item in result.retrieved_sections)
        if result.decision is Decision.ANSWER and not set(case.required_evidence_refs).issubset(
            evidence_refs
        ):
            failures.append(f"{case.id}: required evidence reference missing")
        if evidence_refs & set(case.forbidden_evidence_refs):
            failures.append(f"{case.id}: forbidden evidence reference present")

        network_violations = int(self.config.security.network_enabled) + sum(
            not ref.startswith("local://synthetic-m4/") for ref in evidence_refs
        )
        route_mode = actual_route.get("route_mode") if actual_route else None
        scenario = M4AScenarioResult(
            id=case.id,
            matched=not failures,
            failures=failures,
            expected_profile=case.activation_profile.value,
            actual_profile=orchestra.activation_profile.value,
            expected_decision=expected_decision,
            actual_decision=actual_decision,
            actual_reason_codes=actual_reasons,
            expected_route=case.expected_route,
            actual_route=actual_route,
            route_mode=route_mode,
            case_capsule_id=(
                orchestra.case_capsule.capsule_id if orchestra.case_capsule is not None else None
            ),
            active_agent_count=metrics.active_agent_count,
            worker_execution_count=metrics.worker_execution_count,
            baseline_unchanged=baseline_unchanged,
            result={
                "baseline_trace_id": result.trace_id,
                "decision": actual_decision,
                "reason_codes": actual_reasons,
                "verification_status": orchestra.final_verified_run.verification.status.value,
                "route": actual_route,
                "case_capsule_id": (
                    orchestra.case_capsule.capsule_id
                    if orchestra.case_capsule is not None
                    else None
                ),
                "orchestra_metrics": metrics.model_dump(mode="json"),
            },
        )
        return _M4AComparison(
            scenario=scenario,
            profile=case.activation_profile,
            baseline_mutated=not baseline_unchanged,
            network_violations=network_violations,
        )

    @staticmethod
    def _route_summary(orchestra: OrchestraRun) -> dict[str, Any] | None:
        if orchestra.case_capsule is None:
            return None
        capsule = orchestra.case_capsule
        return {
            "support_function": capsule.support_function,
            "route_mode": capsule.route_mode.value,
            "selected_expert_id": capsule.selected_expert_id,
            "queue_id": capsule.queue_id,
            "routing_confidence": capsule.routing_confidence,
            "confidence_kind": capsule.confidence_kind,
        }

    @staticmethod
    def _failed_comparison(
        case: M4ACase,
        planned: PlannedVerifiedRun,
        before: dict[str, Any],
        failure: str,
    ) -> _M4AComparison:
        result = planned.verified_run.result
        scenario = M4AScenarioResult(
            id=case.id,
            matched=False,
            failures=[failure],
            expected_profile=case.activation_profile.value,
            actual_profile=None,
            expected_decision=str(case.expected_final.get("decision")),
            actual_decision=result.decision.value,
            actual_reason_codes=[reason.value for reason in result.reason_codes],
            expected_route=case.expected_route,
            actual_route=None,
            route_mode=None,
            case_capsule_id=None,
            active_agent_count=0,
            worker_execution_count=0,
            baseline_unchanged=planned.model_dump(mode="json") == before,
            result={"baseline_trace_id": result.trace_id},
        )
        return _M4AComparison(
            scenario=scenario,
            profile=case.activation_profile,
            baseline_mutated=planned.model_dump(mode="json") != before,
            network_violations=0,
        )

    @staticmethod
    def _metrics(comparisons: list[_M4AComparison]) -> M4AMetrics:
        total = len(comparisons)
        return M4AMetrics(
            m4a_case_match_rate=_rate(sum(item.scenario.matched for item in comparisons), total),
            fast_path_accuracy=_rate(
                sum(
                    item.scenario.matched
                    for item in comparisons
                    if item.profile is ActivationProfile.FAST_PATH
                ),
                sum(item.profile is ActivationProfile.FAST_PATH for item in comparisons),
            ),
            short_circuit_clarify_accuracy=_rate(
                sum(
                    item.scenario.matched
                    for item in comparisons
                    if item.profile is ActivationProfile.SHORT_CIRCUIT_CLARIFY
                ),
                sum(
                    item.profile is ActivationProfile.SHORT_CIRCUIT_CLARIFY for item in comparisons
                ),
            ),
            human_first_accuracy=_rate(
                sum(
                    item.scenario.matched
                    for item in comparisons
                    if item.profile is ActivationProfile.HUMAN_FIRST
                ),
                sum(item.profile is ActivationProfile.HUMAN_FIRST for item in comparisons),
            ),
            active_agent_count=sum(item.scenario.active_agent_count for item in comparisons),
            worker_execution_count=sum(
                item.scenario.worker_execution_count for item in comparisons
            ),
            baseline_mutation_count=sum(item.baseline_mutated for item in comparisons),
            network_violation_count=sum(item.network_violations for item in comparisons),
        )


def _rate(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


class M4BScenarioResult(BaseModel):
    """Safe case-level M4B result without query or source-document text."""

    model_config = ConfigDict(extra="forbid")

    id: str
    matched: bool
    failures: list[str]
    expected_profile: str
    actual_profile: str | None
    expected_agent_roles: list[str]
    actual_agent_roles: list[str]
    expected_task_count: int
    actual_task_count: int
    expected_decision: str
    actual_decision: str | None
    expected_claim_ids: list[str]
    actual_claim_ids: list[str]
    required_finding_count: int
    matched_required_finding_count: int
    required_finding_recall: float = Field(ge=0.0, le=1.0)
    required_material_objection_count: int
    matched_required_material_objection_count: int
    required_material_objection_recall: float = Field(ge=0.0, le=1.0)
    required_evidence_refs: list[str]
    actual_evidence_refs: list[str]
    forbidden_evidence_count: int
    open_material_objection_count: int
    diagnostic_codes: list[str]
    expected_route: dict[str, Any] | None
    actual_route: dict[str, Any] | None
    case_capsule_id: str | None
    worker_execution_count: int
    baseline_unchanged: bool
    baseline_mutation_count: int
    agent_to_agent_citation_count: int
    recursive_delegation_count: int
    network_violation_count: int
    result: dict[str, Any]


class M4BMetrics(BaseModel):
    """M4B worker, safety, and regression acceptance metrics."""

    model_config = ConfigDict(extra="forbid")

    m4b_case_match_rate: float = Field(ge=0.0, le=1.0)
    dual_check_accuracy: float = Field(ge=0.0, le=1.0)
    full_orchestra_non_counterfactual_accuracy: float = Field(ge=0.0, le=1.0)
    recovered_answer_accuracy: float = Field(ge=0.0, le=1.0)
    final_safe_abstention_accuracy: float = Field(ge=0.0, le=1.0)
    prompt_injection_safe_answer_accuracy: float = Field(ge=0.0, le=1.0)
    worker_task_count: int = Field(ge=0)
    expected_worker_task_count: int = Field(ge=0)
    worker_task_accuracy: float = Field(ge=0.0, le=1.0)
    worker_role_selection_accuracy: float = Field(ge=0.0, le=1.0)
    required_finding_recall: float = Field(ge=0.0, le=1.0)
    required_material_objection_recall: float = Field(ge=0.0, le=1.0)
    forbidden_evidence_count: int = Field(ge=0)
    open_material_objection_answer_count: int = Field(ge=0)
    agent_to_agent_citation_count: int = Field(ge=0)
    recursive_delegation_count: int = Field(ge=0)
    baseline_mutation_count: int = Field(ge=0)
    network_violation_count: int = Field(ge=0)


class M4BEvaluationDocument(BaseModel):
    """Canonical M4B evaluation report schema."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    metrics: M4BMetrics
    m4_contract: dict[str, Any]
    m4a_regression: dict[str, Any]
    m0_regression: dict[str, Any]
    m1_regression: dict[str, Any]
    m2_regression: dict[str, Any]
    m3_regression: dict[str, Any]
    scenario_results: list[M4BScenarioResult]
    network_enabled: bool
    audit_schema_valid: bool


@dataclass(frozen=True)
class _M4BComparison:
    """Internal counters retained while one M4B case is compared."""

    scenario: M4BScenarioResult
    profile: ActivationProfile
    expected_final_decision: str


class M4BEvaluator:
    """Evaluate the bounded deterministic M4B orchestra over frozen fixtures."""

    def __init__(self, config: Milestone4BConfig) -> None:
        self.config = config

    def run(self) -> M4BEvaluationDocument:
        """Run M4B, M4A regression, M0-M3 regression, and artifact generation."""

        case_set = M4ACaseSet.model_validate_json(
            self.config.orchestra.evaluation_cases.read_text(encoding="utf-8")
        )
        if case_set.schema_version != "1.0" or case_set.milestone != "M4_ORCHESTRA_CONTRACT":
            raise ValueError("Unsupported M4 evaluation case schema")
        cases_by_id = {case.id: case for case in case_set.cases}
        included_ids = self.config.evaluation.included_cases
        if len(included_ids) != self.config.evaluation.expected_cases:
            raise ValueError("M4B included case count does not match config")
        if len(set(included_ids)) != len(included_ids) or any(
            case_id not in cases_by_id for case_id in included_ids
        ):
            raise ValueError("M4B included cases are not present in the frozen case set")
        cases = [cases_by_id[case_id] for case_id in included_ids]

        m4a_document = M4AEvaluator(self.config.base).run()
        self._clear_generated_outputs()
        pipeline = RiskonPipeline.from_milestone4b_config(self.config)
        orchestrator = pipeline._m4b_orchestrator
        if orchestrator is None:
            raise RuntimeError("M4B evaluator requires a configured M4B orchestrator")

        comparisons: list[_M4BComparison] = []
        all_tasks: list[AgentTask] = []
        all_findings: list[AgentFinding] = []
        all_objections: list[MaterialObjection] = []
        for case in cases:
            fixture = self._load_fixture(case)
            planned = fixture.planned_verified_run
            before = planned.model_dump(mode="json")
            try:
                context = self._context(case, planned)
                orchestra = pipeline.orchestrate_planned(
                    planned,
                    context,
                    case.activation_profile.value,
                )
                comparisons.append(
                    self._compare_case(
                        case,
                        orchestra,
                        before,
                        list(orchestrator.last_worker_diagnostics),
                    )
                )
                all_tasks.extend(orchestra.agent_tasks)
                all_findings.extend(orchestra.findings)
                all_objections.extend(orchestra.material_objections)
            except Exception as exc:
                comparisons.append(self._failed_comparison(case, planned, type(exc).__name__))

        generated_root = self.config.orchestra.generated_root
        write_model_jsonl(generated_root / "agent_tasks.jsonl", all_tasks)
        write_model_jsonl(generated_root / "evidence_ledger.jsonl", all_findings)
        write_model_jsonl(generated_root / "material_objections.jsonl", all_objections)
        audit_ok, _ = validate_m4b_audit_file(generated_root / "audit.jsonl")
        m4_contract = self._m4_contract(case_set)
        metrics = self._metrics(comparisons)
        m4a_matched = sum(item.matched for item in m4a_document.scenario_results)
        return M4BEvaluationDocument(
            schema_version="1.0",
            metrics=metrics,
            m4_contract=m4_contract,
            m4a_regression={
                "expected": len(m4a_document.scenario_results),
                "matched": m4a_matched,
            },
            m0_regression=m4a_document.m0_regression,
            m1_regression=m4a_document.m1_regression,
            m2_regression=m4a_document.m2_regression,
            m3_regression=m4a_document.m3_regression,
            scenario_results=[item.scenario for item in comparisons],
            network_enabled=self.config.security.network_enabled,
            audit_schema_valid=audit_ok,
        )

    def _clear_generated_outputs(self) -> None:
        """Remove only known ignored M4B outputs before a deterministic rerun."""

        root = self.config.orchestra.generated_root
        for name in (
            "evaluation.json",
            "evaluation.md",
            "agent_tasks.jsonl",
            "evidence_ledger.jsonl",
            "material_objections.jsonl",
            "audit.jsonl",
        ):
            path = root / name
            if path.is_file():
                path.unlink()

    def _load_fixture(self, case: M4ACase) -> M4AFixtureEnvelope:
        """Load one local frozen M4 upstream wrapper."""

        prefix = "local://synthetic-m4/upstream-runs/"
        if not case.baseline_fixture_ref.startswith(prefix):
            raise ValueError("M4 fixture reference is outside the local upstream namespace")
        filename = case.baseline_fixture_ref.removeprefix(prefix)
        if "/" in filename or "\\" in filename:
            raise ValueError("M4 fixture reference must name one upstream file")
        fixture_path = self.config.orchestra.upstream_runs_root / filename
        fixture = M4AFixtureEnvelope.model_validate_json(fixture_path.read_text(encoding="utf-8"))
        if fixture.fixture_schema_version != "1.0":
            raise ValueError("Unsupported M4 upstream fixture schema")
        if fixture.fixture_origin != "SYNTHETIC_ORCHESTRA_BASELINE_V1":
            raise ValueError("Unexpected M4 upstream fixture origin")
        if fixture.case_id != case.id:
            raise ValueError("M4 fixture lineage does not match the case")
        return fixture

    @staticmethod
    def _context(case: M4ACase, planned: PlannedVerifiedRun) -> OrchestraContext:
        """Build worker context from structured fixture state only."""

        result = planned.verified_run.result
        routing_context: RoutingContext | None = None
        if result.decision is Decision.ABSTAIN:
            routing_context = RoutingContext(
                need_type=result.detected_context.need_type,
                reason_codes=list(result.reason_codes),
                region=result.detected_context.region,
            )
        return OrchestraContext(
            risk_signals=tuple(case.risk_signals),
            routing_context=routing_context,
            routing_profile="default",
        )

    def _compare_case(
        self,
        case: M4ACase,
        orchestra: OrchestraRun,
        before: dict[str, Any],
        diagnostics: list[Any],
    ) -> _M4BComparison:
        """Compare one execution against frozen semantic expectations."""

        result = orchestra.final_verified_run.result
        expected_final = case.expected_final
        failures: list[str] = []
        baseline_unchanged = orchestra.baseline_run.model_dump(mode="json") == before
        if not baseline_unchanged:
            failures.append(f"{case.id}: baseline was mutated")
        if orchestra.activation_profile is not case.activation_profile:
            failures.append(f"{case.id}: activation profile mismatch")
        actual_roles = list(orchestra.investigation_plan.required_agent_roles)
        if actual_roles != case.expected_agent_roles:
            failures.append(f"{case.id}: worker-role selection mismatch")
        if len(orchestra.agent_tasks) != case.expected_task_count:
            failures.append(f"{case.id}: task count mismatch")
        for task in orchestra.agent_tasks:
            expected_task_id = f"task:{task.plan_id}:{task.agent_role.lower()}"
            if task.task_id != expected_task_id:
                failures.append(f"{case.id}: task ID contract mismatch")
            expected_wave = "CHALLENGE" if task.agent_role == "SKEPTIC" else "DISCOVERY"
            if task.execution_wave.value != expected_wave:
                failures.append(f"{case.id}: execution wave mismatch")
        expected_decision = str(expected_final.get("decision"))
        actual_decision = result.decision.value
        if actual_decision != expected_decision:
            failures.append(f"{case.id}: final decision mismatch")
        expected_reasons = [str(item) for item in expected_final.get("reason_codes", [])]
        actual_reasons = [reason.value for reason in result.reason_codes]
        if actual_reasons != expected_reasons:
            failures.append(f"{case.id}: final reason codes mismatch")
        answer_required = expected_final.get("answer_required")
        if answer_required is True and result.answer is None:
            failures.append(f"{case.id}: answer was required")
        if answer_required is False and result.answer is not None:
            failures.append(f"{case.id}: answer was not allowed")

        actual_finding_dicts = [finding.model_dump(mode="json") for finding in orchestra.findings]
        matched_findings = _matched_semantic_records(
            case.required_findings,
            actual_finding_dicts,
            ignored_keys={"finding_id", "task_id"},
        )
        if matched_findings != len(case.required_findings):
            failures.append(f"{case.id}: required finding recall mismatch")

        actual_objection_dicts = [
            objection.model_dump(mode="json") for objection in orchestra.material_objections
        ]
        matched_objections = _matched_semantic_records(
            case.required_material_objections,
            actual_objection_dicts,
            ignored_keys={"objection_id"},
        )
        if matched_objections != len(case.required_material_objections):
            failures.append(f"{case.id}: required material-objection recall mismatch")
        actual_objection_codes = {item["reason_code"] for item in actual_objection_dicts}
        forbidden_objection_codes = actual_objection_codes.intersection(
            case.forbidden_material_objections
        )
        if forbidden_objection_codes:
            failures.append(f"{case.id}: forbidden objection code present")

        actual_claim_ids = sorted(orchestra.final_verified_run.verification.supported_claim_ids)
        expected_claim_ids = sorted(
            str(item) for item in expected_final.get("required_claim_ids", [])
        )
        if not set(expected_claim_ids).issubset(actual_claim_ids):
            failures.append(f"{case.id}: required final claim missing")
        forbidden_claim_ids = set(
            str(item) for item in expected_final.get("forbidden_claim_ids", [])
        )
        if forbidden_claim_ids.intersection(actual_claim_ids):
            failures.append(f"{case.id}: forbidden final claim present")

        actual_evidence_refs = sorted(
            set(orchestra.final_verified_run.verification.evidence_refs).union(
                item.source_ref for item in result.evidence
            )
        )
        required_evidence = set(case.required_evidence_refs)
        if not required_evidence.issubset(actual_evidence_refs):
            failures.append(f"{case.id}: required evidence reference missing")
        forbidden_evidence_count = len(
            set(actual_evidence_refs).intersection(case.forbidden_evidence_refs)
        )
        if forbidden_evidence_count:
            failures.append(f"{case.id}: forbidden evidence reference present")

        open_objections = sum(
            item.materiality == "MATERIAL" and item.status == "OPEN"
            for item in orchestra.material_objections
        )
        expected_open = int(expected_final.get("open_material_objection_count", 0))
        if open_objections != expected_open:
            failures.append(f"{case.id}: open material-objection count mismatch")
        if result.decision is Decision.ANSWER and open_objections:
            failures.append(f"{case.id}: ANSWER crossed an open material objection")

        actual_route = route_summary(orchestra)
        if not _route_matches(case.expected_route, actual_route):
            failures.append(f"{case.id}: route mismatch")
        capsule_required = case.case_capsule_required
        if capsule_required != (orchestra.case_capsule is not None):
            failures.append(f"{case.id}: case-capsule requirement mismatch")
        diagnostic_codes = sorted({str(item.code) for item in diagnostics})
        expected_diagnostics = [
            str(item) for item in expected_final.get("required_diagnostics", [])
        ]
        if not set(expected_diagnostics).issubset(diagnostic_codes):
            failures.append(f"{case.id}: required diagnostic missing")
        if orchestra.counterfactual_results:
            failures.append(f"{case.id}: counterfactual results are outside M4B")

        citation_count = _agent_citation_count(actual_finding_dicts + actual_objection_dicts)
        network_count = int(self.config.security.network_enabled) + sum(
            not ref.startswith("local://synthetic-m4/") for ref in actual_evidence_refs
        )
        if citation_count:
            failures.append(f"{case.id}: agent-to-agent citation detected")
        if network_count:
            failures.append(f"{case.id}: network or non-local evidence detected")
        metrics = orchestra.orchestra_metrics
        if metrics.worker_execution_count != len(orchestra.agent_tasks):
            failures.append(f"{case.id}: worker execution count mismatch")

        scenario = M4BScenarioResult(
            id=case.id,
            matched=not failures,
            failures=failures,
            expected_profile=case.activation_profile.value,
            actual_profile=orchestra.activation_profile.value,
            expected_agent_roles=list(case.expected_agent_roles),
            actual_agent_roles=actual_roles,
            expected_task_count=case.expected_task_count,
            actual_task_count=len(orchestra.agent_tasks),
            expected_decision=expected_decision,
            actual_decision=actual_decision,
            expected_claim_ids=expected_claim_ids,
            actual_claim_ids=actual_claim_ids,
            required_finding_count=len(case.required_findings),
            matched_required_finding_count=matched_findings,
            required_finding_recall=_rate(matched_findings, len(case.required_findings)),
            required_material_objection_count=len(case.required_material_objections),
            matched_required_material_objection_count=matched_objections,
            required_material_objection_recall=_rate(
                matched_objections, len(case.required_material_objections)
            ),
            required_evidence_refs=list(case.required_evidence_refs),
            actual_evidence_refs=actual_evidence_refs,
            forbidden_evidence_count=forbidden_evidence_count,
            open_material_objection_count=open_objections,
            diagnostic_codes=diagnostic_codes,
            expected_route=case.expected_route,
            actual_route=actual_route,
            case_capsule_id=orchestra.case_capsule.capsule_id
            if orchestra.case_capsule is not None
            else None,
            worker_execution_count=metrics.worker_execution_count,
            baseline_unchanged=baseline_unchanged,
            baseline_mutation_count=0 if baseline_unchanged else 1,
            agent_to_agent_citation_count=citation_count,
            recursive_delegation_count=0,
            network_violation_count=network_count,
            result=run_safe_summary(orchestra),
        )
        return _M4BComparison(
            scenario=scenario,
            profile=case.activation_profile,
            expected_final_decision=expected_decision,
        )

    @staticmethod
    def _failed_comparison(
        case: M4ACase,
        planned: PlannedVerifiedRun,
        error_type: str,
    ) -> _M4BComparison:
        """Represent a failed case without serializing exception/source content."""

        result = planned.verified_run.result
        scenario = M4BScenarioResult(
            id=case.id,
            matched=False,
            failures=[f"{case.id}: deterministic execution failed ({error_type})"],
            expected_profile=case.activation_profile.value,
            actual_profile=None,
            expected_agent_roles=list(case.expected_agent_roles),
            actual_agent_roles=[],
            expected_task_count=case.expected_task_count,
            actual_task_count=0,
            expected_decision=str(case.expected_final.get("decision")),
            actual_decision=result.decision.value,
            expected_claim_ids=[
                str(item) for item in case.expected_final.get("required_claim_ids", [])
            ],
            actual_claim_ids=[],
            required_finding_count=len(case.required_findings),
            matched_required_finding_count=0,
            required_finding_recall=0.0 if case.required_findings else 1.0,
            required_material_objection_count=len(case.required_material_objections),
            matched_required_material_objection_count=0,
            required_material_objection_recall=0.0 if case.required_material_objections else 1.0,
            required_evidence_refs=list(case.required_evidence_refs),
            actual_evidence_refs=[],
            forbidden_evidence_count=0,
            open_material_objection_count=0,
            diagnostic_codes=[],
            expected_route=case.expected_route,
            actual_route=None,
            case_capsule_id=None,
            worker_execution_count=0,
            baseline_unchanged=True,
            baseline_mutation_count=0,
            agent_to_agent_citation_count=0,
            recursive_delegation_count=0,
            network_violation_count=0,
            result={"baseline_trace_id": result.trace_id},
        )
        return _M4BComparison(
            scenario=scenario,
            profile=case.activation_profile,
            expected_final_decision=str(case.expected_final.get("decision")),
        )

    def _m4_contract(self, case_set: M4ACaseSet) -> dict[str, Any]:
        """Validate the complete twelve-fixture M4 contract envelope."""

        expected = 12
        matched = 0
        for case in case_set.cases:
            try:
                self._load_fixture(case)
            except (OSError, ValueError):
                continue
            matched += 1
        return {"expected": expected, "matched": matched}

    def _metrics(self, comparisons: list[_M4BComparison]) -> M4BMetrics:
        """Aggregate all M4B acceptance counters from safe scenario fields."""

        scenarios = [item.scenario for item in comparisons]
        dual = [item for item in comparisons if item.profile is ActivationProfile.DUAL_CHECK]
        full = [item for item in comparisons if item.profile is ActivationProfile.FULL_ORCHESTRA]
        answer_cases = [item for item in comparisons if item.expected_final_decision == "ANSWER"]
        abstain_cases = [item for item in comparisons if item.expected_final_decision == "ABSTAIN"]
        injection_cases = [
            item
            for item in comparisons
            if "PROMPT_INJECTION_SIGNAL" in item.scenario.result.get("risk_signals", [])
        ]
        task_count = sum(item.actual_task_count for item in scenarios)
        expected_task_count = self.config.evaluation.expected_worker_tasks
        required_findings = sum(item.required_finding_count for item in scenarios)
        found_findings = sum(item.matched_required_finding_count for item in scenarios)
        required_objections = sum(item.required_material_objection_count for item in scenarios)
        found_objections = sum(item.matched_required_material_objection_count for item in scenarios)
        return M4BMetrics(
            m4b_case_match_rate=_rate(sum(item.matched for item in scenarios), len(scenarios)),
            dual_check_accuracy=_rate(sum(item.scenario.matched for item in dual), len(dual)),
            full_orchestra_non_counterfactual_accuracy=_rate(
                sum(item.scenario.matched for item in full), len(full)
            ),
            recovered_answer_accuracy=_rate(
                sum(item.scenario.matched for item in answer_cases), len(answer_cases)
            ),
            final_safe_abstention_accuracy=_rate(
                sum(item.scenario.matched for item in abstain_cases), len(abstain_cases)
            ),
            prompt_injection_safe_answer_accuracy=_rate(
                sum(item.scenario.matched for item in injection_cases), len(injection_cases)
            ),
            worker_task_count=task_count,
            expected_worker_task_count=expected_task_count,
            worker_task_accuracy=_rate(task_count, expected_task_count),
            worker_role_selection_accuracy=_rate(
                sum(item.actual_agent_roles == item.expected_agent_roles for item in scenarios),
                len(scenarios),
            ),
            required_finding_recall=_rate(found_findings, required_findings),
            required_material_objection_recall=_rate(found_objections, required_objections),
            forbidden_evidence_count=sum(item.forbidden_evidence_count for item in scenarios),
            open_material_objection_answer_count=sum(
                item.open_material_objection_count
                for item in scenarios
                if item.actual_decision == Decision.ANSWER.value
            ),
            agent_to_agent_citation_count=sum(
                item.agent_to_agent_citation_count for item in scenarios
            ),
            recursive_delegation_count=sum(item.recursive_delegation_count for item in scenarios),
            baseline_mutation_count=sum(item.baseline_mutation_count for item in scenarios),
            network_violation_count=sum(item.network_violation_count for item in scenarios),
        )


def _matched_semantic_records(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    *,
    ignored_keys: set[str],
) -> int:
    """Match each expected record to at most one actual semantic record."""

    remaining = list(actual)
    matched = 0
    for required in expected:
        for index, candidate in enumerate(remaining):
            if all(
                key in ignored_keys or candidate.get(key) == value
                for key, value in required.items()
            ):
                matched += 1
                remaining.pop(index)
                break
    return matched


def _route_matches(
    expected: dict[str, Any] | None,
    actual: dict[str, Any] | None,
) -> bool:
    """Compare only the frozen route fields declared by the case."""

    if expected is None:
        return actual is None
    if actual is None:
        return False
    return all(actual.get(key) == value for key, value in expected.items())


def _agent_citation_count(records: list[dict[str, Any]]) -> int:
    """Count forbidden worker-to-worker reference namespaces."""

    return sum(
        reference.startswith(("agent://", "task://", "worker://"))
        for record in records
        for reference in record.get("evidence_refs", [])
    )


class M4CCaseVariant(BaseModel):
    """One evaluator-requested M4C variant specification."""

    model_config = ConfigDict(extra="forbid")

    variant_id: str
    dimension: str
    operation: CounterfactualOperation
    from_value: str
    to_value: str | None = None
    expectation_rule_id: str
    expected_decision: Decision
    expected_reason_codes: list[str]
    actual_fixture_ref: str


class M4CCase(BaseModel):
    """One frozen M4C case with evaluator-only expectations."""

    model_config = ConfigDict(extra="forbid")

    id: str
    m4_contract_ref: str
    baseline_fixture_ref: str
    runner_backend: str
    expected_agent_roles: list[str]
    expected_task_count: int = Field(ge=1)
    variants: list[M4CCaseVariant] = Field(min_length=1)
    expected_material_objections: list[dict[str, Any]]
    expected_final: dict[str, Any]
    expected_route: dict[str, Any] | None


class M4CCaseSet(BaseModel):
    """Frozen M4C evaluation-case envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    milestone: str
    cases: list[M4CCase]


class M4CScenarioResult(BaseModel):
    """Safe case-level M4C transition and final-decision summary."""

    model_config = ConfigDict(extra="forbid")

    id: str
    matched: bool
    failures: list[str]
    expected_agent_roles: list[str]
    actual_agent_roles: list[str]
    expected_task_count: int
    actual_task_count: int
    expected_variant_count: int
    actual_variant_count: int
    expected_safe_transition_count: int
    actual_safe_transition_count: int
    expected_scope_leak_count: int
    actual_scope_leak_count: int
    expected_decision: str
    actual_decision: str | None
    expected_reason_codes: list[str]
    actual_reason_codes: list[str]
    material_objection_count: int
    open_material_objection_count: int
    expected_route: dict[str, Any] | None
    actual_route: dict[str, Any] | None
    case_capsule_id: str | None
    counterfactual_routing_execution_count: int
    recursive_orchestration_count: int
    baseline_unchanged: bool
    baseline_mutation_count: int
    agent_to_agent_citation_count: int
    network_violation_count: int
    result: dict[str, Any]


class M4CMetrics(BaseModel):
    """M4C counterfactual, safety, and worker acceptance metrics."""

    model_config = ConfigDict(extra="forbid")

    m4c_case_match_rate: float = Field(ge=0.0, le=1.0)
    consistency_pass_rate: float = Field(ge=0.0, le=1.0)
    safe_transition_count: int = Field(ge=0)
    expected_safe_transition_count: int = Field(ge=0)
    scope_leak_count: int = Field(ge=0)
    expected_scope_leak_count: int = Field(ge=0)
    unsafe_answer_block_count: int = Field(ge=0)
    expected_unsafe_answer_block_count: int = Field(ge=0)
    counterfactual_variant_count: int = Field(ge=0)
    expected_counterfactual_variant_count: int = Field(ge=0)
    worker_task_count: int = Field(ge=0)
    expected_worker_task_count: int = Field(ge=0)
    brm_queue_route_count: int = Field(ge=0)
    expected_brm_queue_route_count: int = Field(ge=0)
    recursive_orchestration_count: int = Field(ge=0)
    counterfactual_routing_count: int = Field(ge=0)
    baseline_mutation_count: int = Field(ge=0)
    agent_to_agent_citation_count: int = Field(ge=0)
    network_violation_count: int = Field(ge=0)


class M4CEvaluationDocument(BaseModel):
    """Canonical M4C evaluation report schema."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    metrics: M4CMetrics
    m4_contract: dict[str, Any]
    m4a_regression: dict[str, Any]
    m4b_regression: dict[str, Any]
    m0_regression: dict[str, Any]
    m1_regression: dict[str, Any]
    m2_regression: dict[str, Any]
    m3_regression: dict[str, Any]
    m0_m3_regression: dict[str, Any]
    scenario_results: list[M4CScenarioResult]
    network_enabled: bool
    audit_schema_valid: bool


@dataclass(frozen=True)
class _M4CComparison:
    """Internal M4C counters retained while comparing one case."""

    scenario: M4CScenarioResult
    expected_final_decision: str
    consistency_pass: bool


class M4CEvaluator:
    """Evaluate M4C from frozen baselines and evaluator-supplied variant specs."""

    def __init__(self, config: Milestone4CConfig) -> None:
        self.config = config

    def run(self) -> M4CEvaluationDocument:
        """Run M4C and all required upstream regressions."""

        case_set = M4CCaseSet.model_validate_json(
            self.config.orchestra.m4c.evaluation_cases.read_text(encoding="utf-8")
        )
        if case_set.schema_version != "1.0" or case_set.milestone != "M4C_COUNTERFACTUAL_SENTINEL":
            raise ValueError("Unsupported M4C evaluation case schema")
        cases_by_id = {case.id: case for case in case_set.cases}
        included_ids = self.config.evaluation.included_cases
        if len(included_ids) != self.config.evaluation.expected_cases:
            raise ValueError("M4C included case count does not match config")
        if len(set(included_ids)) != len(included_ids) or any(
            case_id not in cases_by_id for case_id in included_ids
        ):
            raise ValueError("M4C included cases are not present in the frozen case set")
        cases = [cases_by_id[case_id] for case_id in included_ids]
        self._validate_worker_extension()
        m4b_document = M4BEvaluator(self.config.base).run()
        self._clear_generated_outputs()
        pipeline = RiskonPipeline.from_milestone4c_config(self.config)
        orchestrator = pipeline._m4c_orchestrator
        if orchestrator is None:
            raise RuntimeError("M4C evaluator requires a configured M4C orchestrator")
        runner = FrozenCounterfactualRunner(
            self.config.orchestra.m4c.fixture_catalog,
            self.config.orchestra.m4c.fixture_root,
            self.config.orchestra.m4c.maximum_counterfactual_depth,
        )

        comparisons: list[_M4CComparison] = []
        all_tasks: list[AgentTask] = []
        all_counterfactual_results: list[CounterfactualExecutionResult] = []
        all_objections: list[MaterialObjection] = []
        for case in cases:
            fixture = self._load_fixture(case)
            planned = fixture.planned_verified_run
            before = planned.model_dump(mode="json")
            try:
                structured_context = orchestrator.planner.context_for(planned)
                context = OrchestraContext(
                    risk_signals=(
                        RiskSignal("SCOPE_SENSITIVE"),
                        RiskSignal("COUNTERFACTUAL_REQUIRED"),
                    ),
                    routing_profile="default",
                    structured_context=structured_context,
                    requested_agent_roles=tuple(case.expected_agent_roles),
                )
                requested_variants = self._requested_variants(case)
                plan = orchestrator.planner.plan(
                    planned,
                    structured_context,
                    requested_variants=requested_variants,
                )
                if plan.baseline_plan_id != planned.query_plan.plan_id:
                    raise ValueError("M4C evaluator built a mismatched counterfactual plan")
                orchestra = pipeline.orchestrate_planned(
                    planned,
                    context,
                    ActivationProfile.FULL_ORCHESTRA.value,
                    counterfactual_plan=plan,
                    counterfactual_runner=runner,
                )
                summary = orchestrator.last_counterfactual_summary
                comparison = self._compare_case(
                    case,
                    orchestra,
                    before,
                    summary.routing_execution_count,
                )
                comparisons.append(comparison)
                all_tasks.extend(orchestra.agent_tasks)
                all_counterfactual_results.extend(orchestra.counterfactual_results)
                all_objections.extend(orchestra.material_objections)
            except Exception as exc:
                comparisons.append(
                    self._failed_comparison(case, planned, before, type(exc).__name__)
                )

        generated_root = self.config.orchestra.m4c.generated_root
        write_model_jsonl(generated_root / "agent_tasks.jsonl", all_tasks)
        write_model_jsonl(
            generated_root / "counterfactual_results.jsonl", all_counterfactual_results
        )
        write_model_jsonl(generated_root / "material_objections.jsonl", all_objections)
        audit_ok, _ = validate_m4c_audit_file(generated_root / "audit.jsonl")
        metrics = self._metrics(comparisons)
        m4b_matched = sum(item.matched for item in m4b_document.scenario_results)
        m0_m3_matched = sum(
            document["matched"]
            for document in (
                m4b_document.m0_regression,
                m4b_document.m1_regression,
                m4b_document.m2_regression,
                m4b_document.m3_regression,
            )
        )
        m0_m3_expected = sum(
            document["expected"]
            for document in (
                m4b_document.m0_regression,
                m4b_document.m1_regression,
                m4b_document.m2_regression,
                m4b_document.m3_regression,
            )
        )
        return M4CEvaluationDocument(
            schema_version="1.0",
            metrics=metrics,
            m4_contract=m4b_document.m4_contract,
            m4a_regression=m4b_document.m4a_regression,
            m4b_regression={"expected": len(m4b_document.scenario_results), "matched": m4b_matched},
            m0_regression=m4b_document.m0_regression,
            m1_regression=m4b_document.m1_regression,
            m2_regression=m4b_document.m2_regression,
            m3_regression=m4b_document.m3_regression,
            m0_m3_regression={"expected": m0_m3_expected, "matched": m0_m3_matched},
            scenario_results=[item.scenario for item in comparisons],
            network_enabled=self.config.security.network_enabled,
            audit_schema_valid=audit_ok,
        )

    def _validate_worker_extension(self) -> None:
        """Validate the small M4C extension without changing the M4B policy."""

        path = self.config.orchestra.m4c.worker_selection_extension
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or set(raw) != {
            "schema_version",
            "extends",
            "backend",
            "implemented_roles",
        }:
            raise ValueError("M4C worker-selection extension fields do not match the contract")
        if raw != {
            "schema_version": "1.0",
            "extends": "local://synthetic-m4b/worker-selection-policy.json",
            "backend": "DETERMINISTIC_WORKER_V1",
            "implemented_roles": ["COUNTERFACTUAL_SENTINEL"],
        }:
            raise ValueError("M4C worker-selection extension does not match the contract")

    def _clear_generated_outputs(self) -> None:
        """Remove only known ignored M4C outputs before a deterministic rerun."""

        root = self.config.orchestra.m4c.generated_root
        for name in (
            "evaluation.json",
            "evaluation.md",
            "agent_tasks.jsonl",
            "counterfactual_results.jsonl",
            "material_objections.jsonl",
            "audit.jsonl",
        ):
            path = root / name
            if path.is_file():
                path.unlink()

    def _load_fixture(self, case: M4CCase) -> M4AFixtureEnvelope:
        """Load one local frozen M4 baseline wrapper."""

        prefix = "local://synthetic-m4/upstream-runs/"
        if not case.baseline_fixture_ref.startswith(prefix):
            raise ValueError("M4C baseline fixture is outside the local upstream namespace")
        filename = case.baseline_fixture_ref.removeprefix(prefix)
        if not filename or "/" in filename or "\\" in filename:
            raise ValueError("M4C baseline fixture reference must name one upstream file")
        fixture_path = self.config.base.orchestra.upstream_runs_root / filename
        fixture = M4AFixtureEnvelope.model_validate_json(fixture_path.read_text(encoding="utf-8"))
        if fixture.fixture_schema_version != "1.0":
            raise ValueError("Unsupported M4 upstream fixture schema")
        if fixture.fixture_origin != "SYNTHETIC_ORCHESTRA_BASELINE_V1":
            raise ValueError("Unexpected M4 upstream fixture origin")
        if fixture.case_id != case.id:
            raise ValueError("M4C fixture lineage does not match the case")
        return fixture

    @staticmethod
    def _requested_variants(case: M4CCase) -> list[CounterfactualVariant]:
        """Pass variant identities and inputs; production derives expected outcomes."""

        return [
            CounterfactualVariant(
                variant_id=item.variant_id,
                dimension=item.dimension,
                operation=item.operation,
                from_value=item.from_value,
                to_value=item.to_value,
                expectation_rule_id=item.expectation_rule_id,
                expected_decision=item.expected_decision,
                expected_reason_codes=[ReasonCode(value) for value in item.expected_reason_codes],
            )
            for item in case.variants
        ]

    def _compare_case(
        self,
        case: M4CCase,
        orchestra: OrchestraRun,
        before: dict[str, Any],
        counterfactual_routing_count: int,
    ) -> _M4CComparison:
        """Compare transition, objection, safety, and final-result contracts."""

        result = orchestra.final_verified_run.result
        expected_final = case.expected_final
        failures: list[str] = []
        baseline_unchanged = orchestra.baseline_run.model_dump(mode="json") == before
        if not baseline_unchanged:
            failures.append(f"{case.id}: baseline was mutated")
        actual_roles = list(orchestra.investigation_plan.required_agent_roles)
        if actual_roles != case.expected_agent_roles:
            failures.append(f"{case.id}: worker-role selection mismatch")
        if len(orchestra.agent_tasks) != case.expected_task_count:
            failures.append(f"{case.id}: task count mismatch")
        for task in orchestra.agent_tasks:
            expected_wave = (
                "VALIDATION"
                if task.agent_role == "COUNTERFACTUAL_SENTINEL"
                else "CHALLENGE"
                if task.agent_role == "SKEPTIC"
                else "DISCOVERY"
            )
            if task.execution_wave.value != expected_wave:
                failures.append(f"{case.id}: execution wave mismatch")

        actual_by_id = {item.variant_id: item for item in orchestra.counterfactual_results}
        for variant in case.variants:
            actual = actual_by_id.get(variant.variant_id)
            if actual is None:
                failures.append(f"{case.id}: missing variant {variant.variant_id}")
                continue
            if actual.expected_decision.value != variant.expected_decision.value:
                failures.append(f"{case.id}: variant expected decision mismatch")
            if [
                item.value for item in actual.expected_reason_codes
            ] != variant.expected_reason_codes:
                failures.append(f"{case.id}: variant expected reason mismatch")
            if actual.context_delta.model_dump(mode="json") != {
                "dimension": variant.dimension,
                "before": variant.from_value,
                "after": variant.to_value,
            }:
                failures.append(f"{case.id}: variant context delta mismatch")
        actual_variant_count = len(orchestra.counterfactual_results)
        actual_safe_count = sum(item.passed for item in orchestra.counterfactual_results)
        actual_scope_leaks = sum(not item.passed for item in orchestra.counterfactual_results)
        expected_variant_count = int(expected_final.get("counterfactual_count", len(case.variants)))
        expected_safe_count = len(case.variants) - len(case.expected_material_objections)
        expected_scope_leaks = len(case.expected_material_objections)
        if actual_variant_count != expected_variant_count:
            failures.append(f"{case.id}: counterfactual count mismatch")
        if actual_scope_leaks != expected_scope_leaks:
            failures.append(f"{case.id}: scope-leak count mismatch")
        if actual_safe_count != expected_safe_count:
            failures.append(f"{case.id}: safe-transition count mismatch")

        actual_objections = [
            objection.model_dump(mode="json") for objection in orchestra.material_objections
        ]
        matched_objections = _matched_semantic_records(
            case.expected_material_objections,
            actual_objections,
            ignored_keys={"objection_id"},
        )
        if matched_objections != len(case.expected_material_objections):
            failures.append(f"{case.id}: material-objection contract mismatch")
        open_objections = sum(
            item.materiality == "MATERIAL" and item.status == "OPEN"
            for item in orchestra.material_objections
        )
        expected_open = int(expected_final.get("open_material_objection_count", 0))
        if open_objections != expected_open:
            failures.append(f"{case.id}: open material-objection count mismatch")
        if result.decision is Decision.ANSWER and open_objections:
            failures.append(f"{case.id}: ANSWER crossed an open material objection")

        expected_decision = str(expected_final.get("decision"))
        actual_decision = result.decision.value
        if actual_decision != expected_decision:
            failures.append(f"{case.id}: final decision mismatch")
        expected_reasons = [str(item) for item in expected_final.get("reason_codes", [])]
        actual_reasons = [reason.value for reason in result.reason_codes]
        if actual_reasons != expected_reasons:
            failures.append(f"{case.id}: final reason codes mismatch")
        if expected_final.get("answer_required") is True and result.answer is None:
            failures.append(f"{case.id}: answer was required")
        if expected_final.get("answer_required") is False and result.answer is not None:
            failures.append(f"{case.id}: answer was not allowed")
        if "clarifying_question" in expected_final and (
            result.clarifying_question != expected_final["clarifying_question"]
        ):
            failures.append(f"{case.id}: clarification mismatch")

        actual_route = route_summary(orchestra)
        if not _route_matches(case.expected_route, actual_route):
            failures.append(f"{case.id}: route mismatch")
        if case.expected_final.get("case_capsule_required") != (orchestra.case_capsule is not None):
            failures.append(f"{case.id}: case-capsule requirement mismatch")

        evidence_refs = set(orchestra.final_verified_run.verification.evidence_refs)
        evidence_refs.update(item.source_ref for item in result.evidence)
        evidence_refs.update(
            reference
            for item in orchestra.counterfactual_results
            for reference in item.actual_evidence_refs
        )
        citation_count = _agent_citation_count(
            [
                *[finding.model_dump(mode="json") for finding in orchestra.findings],
                *actual_objections,
            ]
        )
        network_count = int(self.config.security.network_enabled) + sum(
            not ref.startswith("local://synthetic-m4/") for ref in evidence_refs
        )
        if counterfactual_routing_count:
            failures.append(f"{case.id}: counterfactual routing was executed")
        if citation_count:
            failures.append(f"{case.id}: agent-to-agent citation detected")
        if network_count:
            failures.append(f"{case.id}: network or non-local evidence detected")
        metrics = orchestra.orchestra_metrics
        if metrics.worker_execution_count != len(orchestra.agent_tasks):
            failures.append(f"{case.id}: worker execution count mismatch")

        safe_result = run_safe_summary(orchestra)
        safe_result["counterfactual_results"] = [
            item.model_dump(mode="json") for item in orchestra.counterfactual_results
        ]
        scenario = M4CScenarioResult(
            id=case.id,
            matched=not failures,
            failures=failures,
            expected_agent_roles=list(case.expected_agent_roles),
            actual_agent_roles=actual_roles,
            expected_task_count=case.expected_task_count,
            actual_task_count=len(orchestra.agent_tasks),
            expected_variant_count=expected_variant_count,
            actual_variant_count=actual_variant_count,
            expected_safe_transition_count=expected_safe_count,
            actual_safe_transition_count=actual_safe_count,
            expected_scope_leak_count=expected_scope_leaks,
            actual_scope_leak_count=actual_scope_leaks,
            expected_decision=expected_decision,
            actual_decision=actual_decision,
            expected_reason_codes=expected_reasons,
            actual_reason_codes=actual_reasons,
            material_objection_count=len(orchestra.material_objections),
            open_material_objection_count=open_objections,
            expected_route=case.expected_route,
            actual_route=actual_route,
            case_capsule_id=(
                orchestra.case_capsule.capsule_id if orchestra.case_capsule is not None else None
            ),
            counterfactual_routing_execution_count=counterfactual_routing_count,
            recursive_orchestration_count=0,
            baseline_unchanged=baseline_unchanged,
            baseline_mutation_count=0 if baseline_unchanged else 1,
            agent_to_agent_citation_count=citation_count,
            network_violation_count=network_count,
            result=safe_result,
        )
        return _M4CComparison(
            scenario=scenario,
            expected_final_decision=expected_decision,
            consistency_pass=not actual_scope_leaks and not failures,
        )

    @staticmethod
    def _failed_comparison(
        case: M4CCase,
        planned: PlannedVerifiedRun,
        before: dict[str, Any],
        error_type: str,
    ) -> _M4CComparison:
        """Represent a failed case without serializing exception/source content."""

        result = planned.verified_run.result
        expected_final = case.expected_final
        scenario = M4CScenarioResult(
            id=case.id,
            matched=False,
            failures=[f"{case.id}: deterministic execution failed ({error_type})"],
            expected_agent_roles=list(case.expected_agent_roles),
            actual_agent_roles=[],
            expected_task_count=case.expected_task_count,
            actual_task_count=0,
            expected_variant_count=int(
                expected_final.get("counterfactual_count", len(case.variants))
            ),
            actual_variant_count=0,
            expected_safe_transition_count=len(case.variants)
            - len(case.expected_material_objections),
            actual_safe_transition_count=0,
            expected_scope_leak_count=len(case.expected_material_objections),
            actual_scope_leak_count=0,
            expected_decision=str(expected_final.get("decision")),
            actual_decision=result.decision.value,
            expected_reason_codes=[str(item) for item in expected_final.get("reason_codes", [])],
            actual_reason_codes=[reason.value for reason in result.reason_codes],
            material_objection_count=0,
            open_material_objection_count=0,
            expected_route=case.expected_route,
            actual_route=None,
            case_capsule_id=None,
            counterfactual_routing_execution_count=0,
            recursive_orchestration_count=0,
            baseline_unchanged=planned.model_dump(mode="json") == before,
            baseline_mutation_count=0,
            agent_to_agent_citation_count=0,
            network_violation_count=0,
            result={"baseline_trace_id": result.trace_id},
        )
        return _M4CComparison(
            scenario=scenario,
            expected_final_decision=str(expected_final.get("decision")),
            consistency_pass=False,
        )

    def _metrics(self, comparisons: list[_M4CComparison]) -> M4CMetrics:
        """Aggregate M4C counters from safe scenario summaries."""

        scenarios = [item.scenario for item in comparisons]
        expected_answers = sum(item.expected_final_decision == "ANSWER" for item in comparisons)
        consistency_passes = sum(item.consistency_pass for item in comparisons)
        unsafe_blocks = sum(
            item.expected_final_decision == "ABSTAIN"
            and item.scenario.actual_decision == "ABSTAIN"
            and item.scenario.actual_scope_leak_count > 0
            for item in comparisons
        )
        brm_routes = sum(
            item.scenario.actual_route is not None
            and item.scenario.actual_route.get("support_function") == "BRM_SUITABILITY_LEAD"
            and item.scenario.actual_route.get("route_mode") == "FUNCTIONAL_QUEUE"
            and item.scenario.actual_route.get("selected_expert_id") is None
            for item in comparisons
        )
        return M4CMetrics(
            m4c_case_match_rate=_rate(sum(item.matched for item in scenarios), len(scenarios)),
            consistency_pass_rate=_rate(consistency_passes, expected_answers),
            safe_transition_count=sum(item.actual_safe_transition_count for item in scenarios),
            expected_safe_transition_count=self.config.evaluation.expected_safe_transition_passes,
            scope_leak_count=sum(item.actual_scope_leak_count for item in scenarios),
            expected_scope_leak_count=self.config.evaluation.expected_scope_leaks,
            unsafe_answer_block_count=unsafe_blocks,
            expected_unsafe_answer_block_count=self.config.evaluation.expected_final_abstentions,
            counterfactual_variant_count=sum(item.actual_variant_count for item in scenarios),
            expected_counterfactual_variant_count=(
                self.config.evaluation.expected_counterfactual_variants
            ),
            worker_task_count=sum(item.actual_task_count for item in scenarios),
            expected_worker_task_count=self.config.evaluation.expected_worker_tasks,
            brm_queue_route_count=brm_routes,
            expected_brm_queue_route_count=self.config.evaluation.expected_brm_queue_routes,
            recursive_orchestration_count=sum(
                item.scenario.recursive_orchestration_count for item in comparisons
            ),
            counterfactual_routing_count=sum(
                item.scenario.counterfactual_routing_execution_count for item in comparisons
            ),
            baseline_mutation_count=sum(
                item.scenario.baseline_mutation_count for item in comparisons
            ),
            agent_to_agent_citation_count=sum(
                item.scenario.agent_to_agent_citation_count for item in comparisons
            ),
            network_violation_count=sum(
                item.scenario.network_violation_count for item in comparisons
            ),
        )
