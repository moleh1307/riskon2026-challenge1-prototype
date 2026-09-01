"""Build the ER-B dashboard from actual frozen evaluator and runtime outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from riskon.demo.catalog import DemoCatalog
from riskon.demo.models import (
    DashboardView,
    DecisionMatrixCell,
    DecisionMatrixView,
    MetricView,
    SafetyMetricView,
)
from riskon.m5b_evaluation import M5BEvaluationDocument
from riskon.orchestra.models import OrchestraRun


class DashboardBuilder:
    """Translate evaluator documents into a source-labelled dashboard payload."""

    def __init__(self, catalog: DemoCatalog) -> None:
        self.catalog = catalog

    def build(
        self,
        *,
        m4d_runs: Mapping[str, OrchestraRun],
        m5b_document: M5BEvaluationDocument,
    ) -> DashboardView:
        """Build all required metrics and the expected-vs-actual decision matrix."""

        metrics = self._metrics(m4d_runs, m5b_document)
        matrix = self._decision_matrix(m4d_runs)
        safety = self._safety_metrics(m4d_runs, m5b_document)
        return DashboardView(
            schema_version="1.0",
            metrics=metrics,
            decision_matrix=matrix,
            safety_metrics=safety,
        )

    def _metrics(
        self,
        m4d_runs: Mapping[str, OrchestraRun],
        document: M5BEvaluationDocument,
    ) -> list[MetricView]:
        metrics = document.metrics
        m5b_matches = sum(item.matched for item in document.case_results)
        policy_match = metrics.policy_ci_status_match_count
        policy_expected = metrics.policy_ci_check_count
        counterfactual_match = metrics.counterfactual_matched
        counterfactual_expected = metrics.counterfactual_expected
        scope_violations = sum(
            len(run.final_verified_run.verification.scope_mismatches) for run in m4d_runs.values()
        )
        unsupported_claims = sum(
            len(run.final_verified_run.verification.unsupported_claim_ids)
            for run in m4d_runs.values()
        )
        unsafe_routing = sum(
            int(
                (run.final_verified_run.result.decision.value == "ABSTAIN")
                != (run.case_capsule is not None)
            )
            for run in m4d_runs.values()
        )
        return [
            _ratio_metric(
                "m0_m4d_regression",
                "M0-M4D regression",
                metrics.regression_matched,
                metrics.regression_expected,
                "M5B.metrics.regression_matched/regression_expected",
            ),
            _ratio_metric(
                "m5b_governed_evolution",
                "M5B governed-evolution cases",
                m5b_matches,
                len(document.case_results),
                "M5B.case_results.matched",
            ),
            _ratio_metric(
                "policy_ci_checks",
                "Policy CI checks",
                policy_match,
                policy_expected,
                "M5B.metrics.policy_ci_status_match_count/policy_ci_check_count",
            ),
            _ratio_metric(
                "counterfactual_transitions",
                "Counterfactual transitions",
                counterfactual_match,
                counterfactual_expected,
                "M5B.metrics.counterfactual_matched/counterfactual_expected",
            ),
            _count_metric(
                "scope_violations",
                "Scope violations",
                scope_violations,
                "M4D.final_verified_run.verification.scope_mismatches",
            ),
            _count_metric(
                "unsupported_claims",
                "Unsupported claims",
                unsupported_claims,
                "M4D.final_verified_run.verification.unsupported_claim_ids",
            ),
            _count_metric(
                "unsafe_routing",
                "Unsafe routing",
                unsafe_routing,
                "M4D.case_capsule decision gate",
            ),
            _count_metric(
                "automatic_approvals",
                "Automatic approvals",
                metrics.automatic_approval_count,
                "M5B.metrics.automatic_approval_count",
            ),
            _count_metric(
                "automatic_activations",
                "Automatic activations",
                metrics.automatic_activation_count,
                "M5B.metrics.automatic_activation_count",
            ),
            _count_metric(
                "network_violations",
                "Network violations",
                metrics.network_violation_count,
                "M5B.metrics.network_violation_count",
            ),
        ]

    def _decision_matrix(self, m4d_runs: Mapping[str, OrchestraRun]) -> DecisionMatrixView:
        """Aggregate expected and actual M4D final decisions by case ID."""

        expected_cases = self._m4d_expected_cases()
        labels = [str(item) for item in self.catalog.dashboard_contract["decision_labels"]]
        cells: list[DecisionMatrixCell] = []
        for expected in labels:
            for actual in labels:
                case_ids = [
                    case_id
                    for case_id, raw in expected_cases.items()
                    if str(raw["expected_final"]["decision"]) == expected
                    and case_id in m4d_runs
                    and m4d_runs[case_id].final_verified_run.result.decision.value == actual
                ]
                cells.append(
                    DecisionMatrixCell(
                        expected=expected,
                        actual=actual,
                        count=len(case_ids),
                        case_ids=case_ids,
                    )
                )
        return DecisionMatrixView(
            labels=labels,
            cells=cells,
            source="M4D evaluation cases expected_final vs runtime final_verified_run",
        )

    def _safety_metrics(
        self,
        m4d_runs: Mapping[str, OrchestraRun],
        document: M5BEvaluationDocument,
    ) -> list[SafetyMetricView]:
        """Expose measured guardrail checks with stable source labels."""

        expected_cases = self._m4d_expected_cases()
        abstention_cases = [
            case_id
            for case_id, raw in expected_cases.items()
            if raw["expected_final"]["decision"] == "ABSTAIN"
        ]
        correct_abstentions = sum(
            m4d_runs[case_id].final_verified_run.result.decision.value == "ABSTAIN"
            for case_id in abstention_cases
            if case_id in m4d_runs
        )
        non_abstention_cases = [
            case_id
            for case_id, raw in expected_cases.items()
            if raw["expected_final"]["decision"] != "ABSTAIN"
        ]
        unnecessary_abstentions = sum(
            m4d_runs[case_id].final_verified_run.result.decision.value == "ABSTAIN"
            for case_id in non_abstention_cases
            if case_id in m4d_runs
        )
        valid_citations = sum(
            all(
                ref.startswith(
                    (
                        "local://synthetic-m4/",
                        "local://synthetic-m4d/",
                        "local://knowledge-overlay/",
                    )
                )
                for ref in run.final_verified_run.verification.evidence_refs
            )
            for run in m4d_runs.values()
        )
        critical_runs = [
            run
            for run in m4d_runs.values()
            if "CRITICAL_CONTROL_RISK" in {str(signal) for signal in run.risk_signals}
        ]
        critical_recall = sum(
            bool(run.final_verified_run.verification.supported_claim_ids) for run in critical_runs
        )
        counterfactual_passed = document.metrics.counterfactual_matched
        counterfactual_expected = document.metrics.counterfactual_expected
        route_cases = [run for run in m4d_runs.values() if run.case_capsule is not None]
        route_correct = sum(
            run.final_verified_run.result.route is not None
            and run.case_capsule is not None
            and run.final_verified_run.result.route.support_function
            == run.case_capsule.support_function
            for run in route_cases
        )
        return [
            _safety_ratio(
                "correct_abstention_rate",
                "Correct abstention rate",
                correct_abstentions,
                len(abstention_cases),
                "M4D expected_final vs final_verified_run",
            ),
            _safety_count(
                "unnecessary_abstention_rate",
                "Unnecessary abstention rate",
                unnecessary_abstentions,
                "M4D expected_final vs final_verified_run",
            ),
            _safety_ratio(
                "citation_validity",
                "Citation validity",
                valid_citations,
                len(m4d_runs),
                "M4D verification.evidence_refs local-provenance check",
            ),
            _safety_ratio(
                "critical_control_recall",
                "Critical-control recall",
                critical_recall,
                len(critical_runs),
                "M4D critical-control verification.supported_claim_ids",
            ),
            _safety_count(
                "scope_violation_count",
                "Scope violation count",
                sum(
                    len(run.final_verified_run.verification.scope_mismatches)
                    for run in m4d_runs.values()
                ),
                "M4D final verification scope_mismatches",
            ),
            _safety_ratio(
                "counterfactual_consistency",
                "Counterfactual consistency",
                counterfactual_passed,
                counterfactual_expected,
                "M5B metrics.counterfactual_matched/counterfactual_expected",
            ),
            _safety_ratio(
                "route_function_accuracy",
                "Route-function accuracy",
                route_correct,
                len(route_cases),
                "M4D case capsule support_function vs final route",
            ),
        ]

    def _m4d_expected_cases(self) -> dict[str, dict[str, Any]]:
        """Read the frozen M4D matrix used by the dashboard decision cells."""

        import json

        path = (
            self.catalog.config.project_root
            / "data"
            / "synthetic"
            / "m4d"
            / "evaluation_cases.json"
        )
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(item["id"]): item for item in raw["cases"]}


def _ratio_metric(
    metric_id: str,
    label: str,
    matched: int,
    expected: int,
    source: str,
) -> MetricView:
    """Create a measured ratio card."""

    return MetricView(
        id=metric_id,
        label=label,
        value=f"{matched}/{expected}",
        status="PASS" if matched == expected else "FAIL",
        source=source,
        matched=matched,
        expected=expected,
    )


def _count_metric(metric_id: str, label: str, count: int, source: str) -> MetricView:
    """Create a measured zero-based safety count card."""

    return MetricView(
        id=metric_id,
        label=label,
        value=str(count),
        status="PASS" if count == 0 else "ATTENTION",
        source=source,
        matched=count,
        expected=0,
    )


def _safety_ratio(
    metric_id: str,
    label: str,
    matched: int,
    expected: int,
    source: str,
) -> SafetyMetricView:
    """Create a measured safety ratio or a stable zero-denominator result."""

    if expected == 0:
        return SafetyMetricView(
            id=metric_id,
            label=label,
            value="Not measured in this evaluation profile",
            status="NOT_MEASURED",
            source=source,
        )
    return SafetyMetricView(
        id=metric_id,
        label=label,
        value=f"{matched}/{expected}",
        status="PASS" if matched == expected else "FAIL",
        source=source,
    )


def _safety_count(metric_id: str, label: str, count: int, source: str) -> SafetyMetricView:
    """Create a measured safety count."""

    return SafetyMetricView(
        id=metric_id,
        label=label,
        value=str(count),
        status="PASS" if count == 0 else "ATTENTION",
        source=source,
    )
