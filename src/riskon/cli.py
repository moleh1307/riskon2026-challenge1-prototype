"""CLI entry points; M0 intentionally has no HTTP server command."""

import argparse
import json
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from riskon.audit import validate_audit_file
from riskon.config import (
    load_config,
    load_event_readiness_config,
    load_milestone1_config,
    load_milestone2_config,
    load_milestone3_config,
    load_milestone4a_config,
    load_milestone4b_config,
    load_milestone4c_config,
    load_milestone4d_config,
    load_milestone5b_config,
)
from riskon.demo.errors import DemoContractError, DemoSecurityError
from riskon.demo.live_query import load_context_file, run_live_query
from riskon.demo.reporting import build_demo, build_demo_case
from riskon.evaluation import (
    M1Evaluator,
    M2Evaluator,
    M3Evaluator,
    M4AEvaluator,
    M4BEvaluator,
    M4CEvaluator,
    M4DEvaluator,
)
from riskon.event_intake import (
    CorpusIntakeReport,
    CorpusIntakeRequest,
    CorpusStatus,
    EventCorpusAdapter,
)
from riskon.event_intake.errors import EventIntakeError
from riskon.event_intake.manifest import load_smoke_cases
from riskon.event_intake.reporting import (
    write_compatibility_report,
    write_inspection_reports,
    write_prepared_corpus,
)
from riskon.m5b_evaluation import M5BEvaluator
from riskon.models import PipelineResult, QueryInput
from riskon.orchestra.errors import OrchestraFailClosedError
from riskon.pipeline import M5BRiskonPipeline, RiskonPipeline
from riskon.reporting import (
    write_m2_reports,
    write_m3_reports,
    write_m4a_reports,
    write_m4b_reports,
    write_m4c_reports,
    write_m4d_reports,
    write_m5b_reports,
    write_reports,
)


def _matches(result: PipelineResult, expected: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    expected_decision = expected.get("decision")
    if result.decision.value != expected_decision:
        failures.append(f"decision={result.decision.value!r}, expected={expected_decision!r}")

    expected_reasons = expected.get("reason_codes")
    actual_reasons = [reason.value for reason in result.reason_codes]
    if expected_reasons is not None and actual_reasons != expected_reasons:
        failures.append(f"reason_codes={actual_reasons!r}, expected={expected_reasons!r}")

    if "answer" in expected and result.answer != expected["answer"]:
        failures.append(f"answer={result.answer!r}, expected={expected['answer']!r}")
    if (
        "clarifying_question" in expected
        and result.clarifying_question != expected["clarifying_question"]
    ):
        failures.append("clarifying question did not match")
    if expected.get("evidence") is True and not result.evidence:
        failures.append("expected evidence")
    for phrase in expected.get("answer_contains", []):
        if result.answer is None or phrase not in result.answer:
            failures.append(f"answer missing {phrase!r}")

    expected_route = expected.get("route")
    if expected_route is None:
        if result.route is not None:
            failures.append("expected no route")
    elif result.route is None:
        failures.append("expected a route")
    else:
        for key in ("support_function", "expert_id"):
            if result.route.model_dump(mode="json").get(key) != expected_route.get(key):
                failures.append(f"route {key} did not match")
    return not failures, failures


def evaluate(config_path: Path) -> int:
    """Run all five synthetic scenarios and write the evaluation artifact."""

    if _is_milestone5b_config(config_path):
        return evaluate_milestone5b(config_path)
    if _is_milestone4d_config(config_path):
        return evaluate_milestone4d(config_path)
    if _is_milestone4c_config(config_path):
        return evaluate_milestone4c(config_path)
    if _is_milestone4b_config(config_path):
        return evaluate_milestone4b(config_path)
    if _is_milestone4a_config(config_path):
        return evaluate_milestone4a(config_path)
    if _is_milestone3_config(config_path):
        return evaluate_milestone3(config_path)
    if _is_milestone2_config(config_path):
        return evaluate_milestone2(config_path)
    if _is_milestone1_config(config_path):
        return evaluate_milestone1(config_path)

    config = load_config(config_path)
    pipeline = RiskonPipeline.from_config(config)
    scenarios_path = config.paths.data_root / "scenarios.json"
    scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
    scenario_results: list[dict[str, Any]] = []
    matched_count = 0

    for scenario in scenarios:
        request = QueryInput(query=scenario["query"], context=scenario.get("context", {}))
        try:
            result = pipeline.run(request)
            matched, failures = _matches(result, scenario["expected"])
            if matched:
                matched_count += 1
            scenario_results.append(
                {
                    "id": scenario["id"],
                    "matched": matched,
                    "failures": failures,
                    "result": result.model_dump(mode="json"),
                }
            )
        except Exception as exc:  # pragma: no cover - captured in the evaluation artifact
            scenario_results.append(
                {"id": scenario["id"], "matched": False, "failures": [str(exc)]}
            )

    audit_ok, audit_message = validate_audit_file(config.audit.path)
    evaluation = {
        "scenario_count": len(scenarios),
        "matched_count": matched_count,
        "network_enabled": config.security.network_enabled,
        "audit_schema_valid": audit_ok,
        "audit_message": audit_message,
        "scenarios": scenario_results,
    }
    config.paths.generated_root.mkdir(parents=True, exist_ok=True)
    (config.paths.generated_root / "evaluation.json").write_text(
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if matched_count == len(scenarios) and audit_ok and not config.security.network_enabled:
        print(
            f"M0 PASS: {matched_count}/{len(scenarios)} scenarios matched; network disabled; "
            "audit schema valid."
        )
        return 0
    print(
        f"M0 FAIL: {matched_count}/{len(scenarios)} scenarios matched; "
        f"network_enabled={config.security.network_enabled}; audit={audit_message}."
    )
    return 1


def inspect_corpus(
    root: Path,
    manifest: Path,
    output: Path,
    column_mapping: dict[str, str] | None = None,
) -> int:
    """Inspect one external event corpus and emit only safe inventories."""

    adapter = _event_adapter()
    request = CorpusIntakeRequest(
        source_root=root,
        manifest_path=manifest,
        column_mapping=column_mapping or {},
        output_root=output,
    )
    try:
        report = adapter.inspect(request)
    except (EventIntakeError, ValueError, FileNotFoundError) as exc:
        print(f"Corpus intake BLOCKED: 1 blocking issues; no prepared corpus created. ({exc})")
        return 1
    if not _output_is_blocked(report):
        write_inspection_reports(report, output.resolve())
        prepared = adapter.prepare(request)
        if prepared is not None:
            write_prepared_corpus(prepared, output.resolve())
    return _print_inspection_status(report)


def smoke_corpus(
    root: Path,
    manifest: Path,
    cases_path: Path,
    output: Path,
    column_mapping: dict[str, str] | None = None,
) -> int:
    """Inspect, prepare, and run the bounded compatibility smoke suite."""

    adapter = _event_adapter()
    request = CorpusIntakeRequest(
        source_root=root,
        manifest_path=manifest,
        column_mapping=column_mapping or {},
        output_root=output,
    )
    try:
        report = adapter.inspect(request)
    except (EventIntakeError, ValueError, FileNotFoundError) as exc:
        print(f"Corpus compatibility FAIL: unable to inspect corpus. ({exc})")
        return 1
    if not _output_is_blocked(report):
        write_inspection_reports(report, output.resolve())
    if report.status is CorpusStatus.BLOCKED:
        _print_inspection_status(report)
        return 1
    prepared = adapter.prepare(request)
    if prepared is None:
        print("Corpus compatibility FAIL: no prepared corpus created.")
        return 1
    if not _output_is_blocked(report):
        write_prepared_corpus(prepared, output.resolve())
    try:
        cases = load_smoke_cases(cases_path)
        compatibility = adapter.smoke_test(prepared, cases)
    except (EventIntakeError, ValueError, FileNotFoundError) as exc:
        print(f"Corpus compatibility FAIL: smoke cases could not run. ({exc})")
        return 1
    if not _output_is_blocked(report):
        write_compatibility_report(compatibility, output.resolve())
    if compatibility.passed:
        print(
            f"Corpus compatibility PASS: {compatibility.matched_case_count}/"
            f"{compatibility.expected_case_count} smoke cases; source mutations "
            f"{compatibility.source_mutations}; external fetches "
            f"{compatibility.external_fetches}; network disabled."
        )
        return 0
    print(
        f"Corpus compatibility FAIL: {compatibility.matched_case_count}/"
        f"{compatibility.expected_case_count} smoke cases; source mutations "
        f"{compatibility.source_mutations}; external fetches "
        f"{compatibility.external_fetches}; network disabled."
    )
    return 1


def _event_adapter() -> EventCorpusAdapter:
    """Load the repository-local ER-A policy for the CLI."""

    project_root = Path(__file__).resolve().parents[2]
    # Loading the config here keeps CLI defaults tied to the frozen contract.
    load_event_readiness_config(project_root / "config" / "event_readiness.toml")
    return EventCorpusAdapter.from_project_root(project_root)


def _output_is_blocked(report: CorpusIntakeReport) -> bool:
    """Prevent report writers from ever writing inside a read-only source root."""

    return any(issue.code == "OUTPUT_INSIDE_SOURCE_ROOT" for issue in report.blocking_issues)


def _print_inspection_status(report: CorpusIntakeReport) -> int:
    """Print the exact intake status contract."""

    if report.status is CorpusStatus.READY:
        print(
            f"Corpus intake READY: {report.manifest_row_count} manifest rows; "
            f"{report.matched_html_count} HTML files matched; "
            f"{report.blocking_issue_count} blocking issues; external fetches 0."
        )
        return 0
    if report.status is CorpusStatus.READY_WITH_WARNINGS:
        print(
            f"Corpus intake READY_WITH_WARNINGS: {report.warning_count} warnings; "
            f"{report.blocking_issue_count} blocking issues; external fetches 0."
        )
        return 0
    print(
        f"Corpus intake BLOCKED: {report.blocking_issue_count} blocking issues; "
        "no prepared corpus created."
    )
    return 1


def evaluate_milestone5b(config_path: Path) -> int:
    """Run the final governed-overlay acceptance matrix."""

    config = load_milestone5b_config(config_path)
    document = M5BEvaluator(config).run()
    write_m5b_reports(document, config.governance.generated_root)
    metrics = document.metrics
    passed = (
        len(document.case_results) == config.evaluation.expected_cases
        and all(item.matched for item in document.case_results)
        and metrics.governed_evolution_count == 1
        and metrics.awaiting_approval_count == 1
        and metrics.rejected_unsafe_patch_count == 2
        and metrics.expired_patch_exclusion_count == 1
        and metrics.policy_ci_check_count == metrics.expected_policy_ci_check_count == 55
        and metrics.policy_ci_status_match_count == 55
        and metrics.regression_expected == metrics.regression_matched == 45
        and metrics.counterfactual_expected == metrics.counterfactual_matched == 4
        and metrics.exact_scope_answer_count == 1
        and metrics.alternate_region_abstention_count == 1
        and metrics.alternate_service_abstention_count == 1
        and metrics.missing_context_clarification_count == 1
        and metrics.automatic_approval_count == 0
        and metrics.automatic_activation_count == 0
        and metrics.self_approval_count == 0
        and metrics.failed_check_override_count == 0
        and metrics.official_corpus_mutation_count == 0
        and metrics.expired_evidence_retrieval_count == 0
        and metrics.network_violation_count == 0
        and not document.security["network_enabled"]
    )
    if passed:
        print(
            "M5B PASS: governed evolution 5/5; activated patches 1/1; awaiting approval 1/1; "
            "rejected unsafe patches 2/2; expired patches excluded 1/1; Policy CI checks 55/55; "
            "regression gate 45/45; scope transitions 4/4; automatic approvals 0; "
            "automatic activations 0; self-approvals 0; official corpus mutations 0; "
            "expired evidence retrievals 0; network disabled."
        )
        return 0
    matched = sum(item.matched for item in document.case_results)
    print(
        f"M5B FAIL: governed evolution cases {matched}/{len(document.case_results)}; "
        f"Policy CI statuses {metrics.policy_ci_status_match_count}/55; "
        f"regression gate {metrics.regression_matched}/{metrics.regression_expected}."
    )
    return 1


def evaluate_milestone1(config_path: Path) -> int:
    """Run the M0 regression plus all seven M1 selective-QA cases."""

    config = load_milestone1_config(config_path)
    document = M1Evaluator(config).run()
    write_reports(document, config.generated_root)
    metrics = document.metrics
    m0_matched = document.m0_regression["matched"]
    m0_expected = document.m0_regression["expected"]
    passed = (
        metrics.scenario_match_rate == 1.0
        and metrics.decision_accuracy == 1.0
        and metrics.answer_case_claim_recall == 1.0
        and metrics.critical_claim_recall == 1.0
        and metrics.citation_validity == 1.0
        and metrics.route_function_accuracy == 1.0
        and metrics.route_expert_accuracy == 1.0
        and metrics.scope_violation_count == 0
        and metrics.unsupported_claim_count == 0
        and metrics.unresolved_reference_false_negative_count == 0
        and metrics.network_violation_count == 0
        and m0_matched == m0_expected == config.evaluation.expected_m0_cases
        and document.audit_schema_valid
        and not document.network_enabled
    )
    if passed:
        print(
            "M1 PASS: 12/12 scenarios matched; M0 regression 5/5; "
            "claim support valid; network disabled."
        )
        return 0
    print(
        f"M1 FAIL: {int(metrics.scenario_match_rate * 12)}/12 scenarios matched; "
        f"M0 regression {m0_matched}/{m0_expected}; claim support invalid or a gate failed."
    )
    return 1


def evaluate_milestone2(config_path: Path) -> int:
    """Run M0/M1 regressions plus all eight M2 planned-retrieval cases."""

    config = load_milestone2_config(config_path)
    document = M2Evaluator(config).run()
    write_m2_reports(document, config.generated_root)
    metrics = document.metrics
    m0_matched = document.m0_regression["matched"]
    m0_expected = document.m0_regression["expected"]
    m1_matched = document.m1_regression["matched"]
    m1_expected = document.m1_regression["expected"]
    passed = (
        metrics.m2_case_match_rate == 1.0
        and metrics.query_plan_accuracy == 1.0
        and metrics.retrieval_top1_accuracy == 1.0
        and metrics.required_evidence_recall_at_5 == 1.0
        and metrics.subquery_coverage == 1.0
        and metrics.table_row_recall == 1.0
        and metrics.clarification_short_circuit_accuracy == 1.0
        and metrics.forbidden_evidence_count == 0
        and metrics.context_filter_violation_count == 0
        and metrics.unsupported_claim_count == 0
        and metrics.network_violation_count == 0
        and m0_matched == m0_expected == config.evaluation.expected_m0_cases
        and m1_matched == m1_expected == config.evaluation.expected_m1_new_cases
        and document.audit_schema_valid
        and not document.network_enabled
    )
    if passed:
        print(
            "M2 PASS: aggregate 20/20; M0 5/5; M1-new 7/7; M2-new 8/8; "
            "query plans 8/8; evidence recall@5 1.000; context violations 0; "
            "network disabled."
        )
        return 0
    matched = sum(1 for item in document.scenario_results if item.matched)
    print(
        f"M2 FAIL: aggregate incomplete; M0 {m0_matched}/{m0_expected}; "
        f"M1-new {m1_matched}/{m1_expected}; M2-new {matched}/"
        f"{len(document.scenario_results)}; one or more M2 gates failed."
    )
    return 1


def evaluate_milestone3(config_path: Path) -> int:
    """Run fixture-backed M3 routing plus M0-M2 regressions."""

    config = load_milestone3_config(config_path)
    document = M3Evaluator(config).run()
    write_m3_reports(document, config.generated_root)
    metrics = document.metrics
    m0_matched = document.m0_regression["matched"]
    m0_expected = document.m0_regression["expected"]
    m1_matched = document.m1_regression["matched"]
    m1_expected = document.m1_regression["expected"]
    m2_matched = document.m2_regression["matched"]
    m2_expected = document.m2_regression["expected"]
    passed = (
        metrics.m3_case_match_rate == 1.0
        and metrics.support_function_accuracy == 1.0
        and metrics.person_or_queue_selection_accuracy == 1.0
        and metrics.candidate_top3_recall == 1.0
        and metrics.routing_explanation_completeness == 1.0
        and metrics.routing_confidence_contract_accuracy == 1.0
        and metrics.legacy_route_consistency == 1.0
        and metrics.support_model_hot_swap_accuracy == 1.0
        and metrics.hard_constraint_violation_count == 0
        and metrics.mandate_violation_count == 0
        and metrics.jurisdiction_violation_count == 0
        and metrics.region_violation_count == 0
        and metrics.system_violation_count == 0
        and metrics.inactive_expert_selection_count == 0
        and metrics.unavailable_expert_selection_count == 0
        and metrics.raw_query_dependency_count == 0
        and metrics.network_violation_count == 0
        and m0_matched == m0_expected == config.evaluation.expected_m0_cases
        and m1_matched == m1_expected == config.evaluation.expected_m1_new_cases
        and m2_matched == m2_expected == config.evaluation.expected_m2_new_cases
        and document.audit_schema_valid
        and not document.network_enabled
    )
    if passed:
        print(
            "M3 PASS: aggregate 28/28; M0 5/5; M1-new 7/7; M2-new 8/8; "
            "M3-new 8/8; support functions 8/8; person-or-queue 8/8; "
            "hot-swap 1/1; hard-constraint violations 0; network disabled."
        )
        return 0
    matched = sum(1 for item in document.scenario_results if item.matched)
    print(
        f"M3 FAIL: aggregate incomplete; M0 {m0_matched}/{m0_expected}; "
        f"M1-new {m1_matched}/{m1_expected}; M2-new {m2_matched}/{m2_expected}; "
        f"M3-new {matched}/{len(document.scenario_results)}; one or more M3 gates failed."
    )
    return 1


def evaluate_milestone4a(config_path: Path) -> int:
    """Run the M4A zero-worker cases plus the complete M0-M3 regression."""

    config = load_milestone4a_config(config_path)
    document = M4AEvaluator(config).run()
    write_m4a_reports(document, config.orchestra.generated_root)
    metrics = document.metrics
    regression_expected = config.base.evaluation.expected_aggregate_cases
    regression_matched = (
        document.m0_regression["matched"]
        + document.m1_regression["matched"]
        + document.m2_regression["matched"]
        + document.m3_regression["matched"]
    )
    passed = (
        metrics.m4a_case_match_rate == 1.0
        and metrics.fast_path_accuracy == 1.0
        and metrics.short_circuit_clarify_accuracy == 1.0
        and metrics.human_first_accuracy == 1.0
        and metrics.active_agent_count == config.evaluation.expected_active_agents
        and metrics.worker_execution_count == 0
        and metrics.baseline_mutation_count == 0
        and metrics.network_violation_count == 0
        and document.m0_regression["matched"] == document.m0_regression["expected"]
        and document.m1_regression["matched"] == document.m1_regression["expected"]
        and document.m2_regression["matched"] == document.m2_regression["expected"]
        and document.m3_regression["matched"] == document.m3_regression["expected"]
        and regression_matched == regression_expected == 28
        and document.audit_schema_valid
        and not document.network_enabled
    )
    if passed:
        print(
            "M4A PASS: zero-worker paths 5/5; FAST_PATH 1/1; "
            "SHORT_CIRCUIT_CLARIFY 1/1; HUMAN_FIRST 3/3; M0-M3 regression 28/28; "
            "active agents 0; baseline mutations 0; network disabled."
        )
        return 0
    matched = sum(item.matched for item in document.scenario_results)
    print(
        f"M4A FAIL: zero-worker paths {matched}/{len(document.scenario_results)}; "
        f"M0-M3 regression {regression_matched}/{regression_expected}; "
        "one or more zero-worker or audit gates failed."
    )
    return 1


def evaluate_milestone4b(config_path: Path) -> int:
    """Run bounded M4B workers plus M4A and M0-M3 regressions."""

    config = load_milestone4b_config(config_path)
    document = M4BEvaluator(config).run()
    write_m4b_reports(document, config.orchestra.generated_root)
    metrics = document.metrics
    m4b_matched = sum(item.matched for item in document.scenario_results)
    regression_matched = (
        document.m4a_regression["matched"]
        + document.m0_regression["matched"]
        + document.m1_regression["matched"]
        + document.m2_regression["matched"]
        + document.m3_regression["matched"]
    )
    regression_expected = (
        document.m4a_regression["expected"]
        + document.m0_regression["expected"]
        + document.m1_regression["expected"]
        + document.m2_regression["expected"]
        + document.m3_regression["expected"]
    )
    passed = (
        m4b_matched == config.evaluation.expected_cases
        and metrics.m4b_case_match_rate == 1.0
        and metrics.dual_check_accuracy == 1.0
        and metrics.full_orchestra_non_counterfactual_accuracy == 1.0
        and metrics.recovered_answer_accuracy == 1.0
        and metrics.final_safe_abstention_accuracy == 1.0
        and metrics.prompt_injection_safe_answer_accuracy == 1.0
        and metrics.worker_task_count == config.evaluation.expected_worker_tasks
        and metrics.worker_task_accuracy == 1.0
        and metrics.worker_role_selection_accuracy == 1.0
        and metrics.required_finding_recall == 1.0
        and metrics.required_material_objection_recall == 1.0
        and metrics.forbidden_evidence_count == 0
        and metrics.open_material_objection_answer_count == 0
        and metrics.agent_to_agent_citation_count == 0
        and metrics.recursive_delegation_count == 0
        and metrics.baseline_mutation_count == 0
        and metrics.network_violation_count == 0
        and document.m4_contract == {"expected": 12, "matched": 12}
        and document.m4a_regression["matched"] == document.m4a_regression["expected"] == 5
        and regression_matched == regression_expected == 33
        and document.audit_schema_valid
        and not document.network_enabled
    )
    if passed:
        print(
            "M4B PASS: worker paths 5/5; DUAL_CHECK 3/3; "
            "FULL_ORCHESTRA non-counterfactual 2/2; recovered answers 3/3; "
            "safety outcomes 2/2; worker tasks 12/12; M4A regression 5/5; "
            "M0-M3 regression 28/28; baseline mutations 0; "
            "agent-to-agent citations 0; network disabled."
        )
        return 0
    print(
        f"M4B FAIL: worker paths {m4b_matched}/{len(document.scenario_results)}; "
        f"worker tasks {metrics.worker_task_count}/{config.evaluation.expected_worker_tasks}; "
        f"M4A regression {document.m4a_regression['matched']}/"
        f"{document.m4a_regression['expected']}; M0-M3 aggregate "
        f"{regression_matched - document.m4a_regression['matched']}/"
        f"{regression_expected - document.m4a_regression['expected']}; "
        "one or more M4B gates failed."
    )
    return 1


def evaluate_milestone4c(config_path: Path) -> int:
    """Run M4C transition adjudication plus all required regressions."""

    config = load_milestone4c_config(config_path)
    document = M4CEvaluator(config).run()
    write_m4c_reports(document, config.orchestra.m4c.generated_root)
    metrics = document.metrics
    passed = (
        len(document.scenario_results) == config.evaluation.expected_cases
        and metrics.m4c_case_match_rate == 1.0
        and metrics.consistency_pass_rate == 1.0
        and metrics.safe_transition_count
        == metrics.expected_safe_transition_count
        == config.evaluation.expected_safe_transition_passes
        and metrics.scope_leak_count
        == metrics.expected_scope_leak_count
        == config.evaluation.expected_scope_leaks
        and metrics.unsafe_answer_block_count
        == metrics.expected_unsafe_answer_block_count
        == config.evaluation.expected_final_abstentions
        and metrics.counterfactual_variant_count
        == metrics.expected_counterfactual_variant_count
        == config.evaluation.expected_counterfactual_variants
        and metrics.worker_task_count
        == metrics.expected_worker_task_count
        == config.evaluation.expected_worker_tasks
        and metrics.brm_queue_route_count
        == metrics.expected_brm_queue_route_count
        == config.evaluation.expected_brm_queue_routes
        and metrics.recursive_orchestration_count == 0
        and metrics.counterfactual_routing_count == 0
        and metrics.baseline_mutation_count == 0
        and metrics.agent_to_agent_citation_count == 0
        and metrics.network_violation_count == 0
        and document.m4_contract == {"expected": 12, "matched": 12}
        and document.m4a_regression["matched"] == document.m4a_regression["expected"] == 5
        and document.m4b_regression["matched"] == document.m4b_regression["expected"] == 5
        and document.m0_m3_regression == {"expected": 28, "matched": 28}
        and document.audit_schema_valid
        and not document.network_enabled
    )
    if passed:
        print(
            "M4C PASS: counterfactual cases 2/2; consistency pass 1/1; safe transitions 3/3; "
            "scope leak detected 1/1; unsafe answer blocked 1/1; variants 4/4; worker tasks 7/7; "
            "BRM queue route 1/1; M4A regression 5/5; M4B regression 5/5; M0-M3 regression 28/28; "
            "recursive orchestration 0; counterfactual routing 0; baseline mutations 0; "
            "network disabled."
        )
        return 0
    matched = sum(item.matched for item in document.scenario_results)
    print(
        f"M4C FAIL: counterfactual cases {matched}/{len(document.scenario_results)}; "
        f"safe transitions {metrics.safe_transition_count}/"
        f"{metrics.expected_safe_transition_count}; scope leaks {metrics.scope_leak_count}/"
        f"{metrics.expected_scope_leak_count}; worker tasks {metrics.worker_task_count}/"
        f"{metrics.expected_worker_task_count}; one or more M4C gates failed."
    )
    return 1


def evaluate_milestone4d(config_path: Path) -> int:
    """Run M4D automatic activation, failure contracts, and regressions."""

    config = load_milestone4d_config(config_path)
    document = M4DEvaluator(config).run()
    write_m4d_reports(document, config.orchestra.m4d.generated_root)
    metrics = document.metrics
    passed = (
        document.m4d_contract == {"expected": 5, "matched": 5}
        and metrics.m4d_case_match_rate == 1.0
        and metrics.automatic_activation_accuracy == 1.0
        and metrics.fast_path_accuracy == 1.0
        and metrics.short_circuit_clarify_accuracy == 1.0
        and metrics.human_first_accuracy == 1.0
        and metrics.dual_check_accuracy == 1.0
        and metrics.full_orchestra_accuracy == 1.0
        and metrics.local_counterfactual_transition_count
        == metrics.expected_local_counterfactual_transition_count
        == config.evaluation.expected_local_counterfactual_transitions
        and metrics.run_planned_once_accuracy == 1.0
        and metrics.risk_signal_provenance_completeness == 1.0
        and metrics.failure_contract_count == metrics.expected_failure_contract_count == 3
        and metrics.answer_worker_fail_closed_count
        == metrics.expected_answer_worker_fail_closed_count
        == 1
        and metrics.abstain_worker_fallback_count
        == metrics.expected_abstain_worker_fallback_count
        == 1
        and metrics.counterfactual_fail_closed_count
        == metrics.expected_counterfactual_fail_closed_count
        == 1
        and metrics.partial_answer_count == 0
        and metrics.unexpected_route_invention_count == 0
        and metrics.recursive_orchestration_count == 0
        and metrics.counterfactual_routing_count == 0
        and metrics.agent_to_agent_citation_count == 0
        and metrics.baseline_mutation_count == 0
        and metrics.network_violation_count == 0
        and document.m4_frozen_contract == {"expected": 12, "matched": 12}
        and document.m4a_regression["matched"] == document.m4a_regression["expected"] == 5
        and document.m4b_regression["matched"] == document.m4b_regression["expected"] == 5
        and document.m4c_regression["matched"] == document.m4c_regression["expected"] == 2
        and document.m0_m3_regression == {"expected": 28, "matched": 28}
        and document.audit_schema_valid
        and not document.network_enabled
    )
    if passed:
        print(
            "M4D PASS: end-to-end 5/5; auto-activation 5/5; FAST_PATH 1/1; "
            "SHORT_CIRCUIT_CLARIFY 1/1; HUMAN_FIRST 1/1; DUAL_CHECK 1/1; "
            "FULL_ORCHESTRA 1/1; local counterfactual transitions 3/3; "
            "failure contracts 3/3; M4A regression 5/5; M4B regression 5/5; "
            "M4C regression 2/2; M0-M3 regression 28/28; partial answers after failure 0; "
            "baseline mutations 0; network disabled."
        )
        return 0
    matched = sum(item.matched for item in document.scenario_results)
    print(
        f"M4D FAIL: end-to-end {matched}/{len(document.scenario_results)}; "
        f"failure contracts {metrics.failure_contract_count}/"
        f"{metrics.expected_failure_contract_count}; one or more M4D gates failed."
    )
    return 1


def _is_milestone1_config(config_path: Path) -> bool:
    if not config_path.is_file():
        return False
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return "extension" in raw and "verification" in raw


def _is_milestone2_config(config_path: Path) -> bool:
    if not config_path.is_file():
        return False
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return "extension" in raw and "query_planning" in raw and "retrieval" in raw


def _is_milestone3_config(config_path: Path) -> bool:
    if not config_path.is_file():
        return False
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return "extension" in raw and "routing" in raw and "network_edges" in raw["extension"]


def _is_milestone4a_config(config_path: Path) -> bool:
    if not config_path.is_file():
        return False
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    orchestra = raw.get("orchestra")
    return (
        isinstance(orchestra, dict)
        and "m4a" in orchestra
        and "evaluation" in raw
        and "security" in raw
    )


def _is_milestone4b_config(config_path: Path) -> bool:
    if not config_path.is_file():
        return False
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    orchestra = raw.get("orchestra")
    return (
        isinstance(orchestra, dict)
        and "m4b" in orchestra
        and "evaluation" in raw
        and "security" in raw
    )


def _is_milestone4c_config(config_path: Path) -> bool:
    if not config_path.is_file():
        return False
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    orchestra = raw.get("orchestra")
    return (
        isinstance(orchestra, dict)
        and "m4c" in orchestra
        and "evaluation" in raw
        and "security" in raw
    )


def _is_milestone4d_config(config_path: Path) -> bool:
    if not config_path.is_file():
        return False
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    orchestra = raw.get("orchestra")
    return (
        isinstance(orchestra, dict)
        and "m4d" in orchestra
        and "evaluation" in raw
        and "security" in raw
    )


def _is_milestone5b_config(config_path: Path) -> bool:
    if not config_path.is_file():
        return False
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    governance = raw.get("governance")
    return (
        isinstance(governance, dict)
        and "contract_cases" in governance
        and "execution_policy" in governance
        and "policy_ci" in governance
        and "evaluation" in raw
        and "security" in raw
    )


def run_query(config_path: Path, query: str, context_json: str | None) -> int:
    """Run one local query and print its JSON result."""

    context = json.loads(context_json) if context_json else {}
    request = QueryInput(query=query, context=context)
    result: Any
    try:
        if _is_milestone5b_config(config_path):
            result = M5BRiskonPipeline.from_milestone5b_config(
                load_milestone5b_config(config_path)
            ).run_orchestrated(request)
        elif _is_milestone4d_config(config_path):
            result = RiskonPipeline.from_milestone4d_config(
                load_milestone4d_config(config_path)
            ).run_orchestrated(request)
        elif _is_milestone4c_config(config_path):
            raise ValueError(
                "M4C exposes orchestrate_planned for frozen inputs; "
                "run_orchestrated is not available"
            )
        elif _is_milestone4b_config(config_path):
            raise ValueError(
                "M4B exposes orchestrate_planned for frozen inputs; "
                "run_orchestrated is not available"
            )
        elif _is_milestone4a_config(config_path):
            raise ValueError(
                "M4A exposes orchestrate_planned for frozen inputs; "
                "run_orchestrated is not available"
            )
        elif _is_milestone3_config(config_path):
            result = RiskonPipeline.from_milestone3_config(
                load_milestone3_config(config_path)
            ).run_routed(request)
        elif _is_milestone2_config(config_path):
            result = RiskonPipeline.from_milestone2_config(
                load_milestone2_config(config_path)
            ).run_planned(request)
        elif _is_milestone1_config(config_path):
            result = RiskonPipeline.from_milestone1_config(
                load_milestone1_config(config_path)
            ).run_verified(request)
        else:
            result = RiskonPipeline.from_config(load_config(config_path)).run(request)
    except OrchestraFailClosedError as exc:
        print(exc.safe_message, file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(prog="riskon")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = subparsers.add_parser("evaluate", help="evaluate all synthetic M0 scenarios")
    evaluate_parser.add_argument("--config", type=Path, required=True)

    run_parser = subparsers.add_parser("run", help="run one local query")
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("query")
    run_parser.add_argument("--context", dest="context_json")

    inspect_parser = subparsers.add_parser(
        "inspect-corpus",
        help="inspect an external event HTML corpus without mutating or fetching it",
    )
    _add_event_arguments(inspect_parser, include_cases=False)

    smoke_parser = subparsers.add_parser(
        "smoke-corpus",
        help="run the local event corpus compatibility smoke suite",
    )
    _add_event_arguments(smoke_parser, include_cases=True)

    demo_build_parser = subparsers.add_parser(
        "demo-build",
        help="build the self-contained local ER-B demonstration",
    )
    demo_build_parser.add_argument("--config", type=Path, required=True)

    demo_case_parser = subparsers.add_parser(
        "demo-case",
        help="render one frozen ER-B story as standalone HTML",
    )
    demo_case_parser.add_argument("--config", type=Path, required=True)
    demo_case_parser.add_argument("--case", required=True)
    demo_case_parser.add_argument("--output", type=Path, required=True)

    demo_query_parser = subparsers.add_parser(
        "demo-query",
        help="run one synthetic query through the local orchestrated runtime",
    )
    demo_query_parser.add_argument("--config", type=Path, required=True)
    demo_query_parser.add_argument("--question", required=True)
    demo_query_parser.add_argument("--output", type=Path, required=True)
    demo_query_parser.add_argument("--context-file", type=Path)
    demo_query_parser.add_argument("--context-id")

    pitch_build_parser = subparsers.add_parser(
        "pitch-build",
        help="build the ER-C final pitch, demo and event-day package",
    )
    pitch_build_parser.add_argument("--config", type=Path, required=True)

    pitch_validate_parser = subparsers.add_parser(
        "pitch-validate",
        help="validate an existing ER-C generated package",
    )
    pitch_validate_parser.add_argument("--config", type=Path, required=True)

    pitch_script_parser = subparsers.add_parser(
        "pitch-script",
        help="render one ER-C timing script",
    )
    pitch_script_parser.add_argument("--config", type=Path, required=True)
    pitch_script_parser.add_argument(
        "--profile", choices=["3_MIN", "5_MIN", "7_MIN"], required=True
    )
    return parser


def _add_event_arguments(parser: argparse.ArgumentParser, *, include_cases: bool) -> None:
    """Add the shared ER-A CLI arguments."""

    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    if include_cases:
        parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument(
        "--column-mapping",
        help='JSON object such as {"filename":"Document","title":"Page"}',
    )
    parser.add_argument("--filename-column")
    parser.add_argument("--title-column")
    parser.add_argument("--url-column")


def _event_column_mapping(args: argparse.Namespace) -> dict[str, str]:
    """Combine JSON and individual explicit column mappings."""

    mapping: dict[str, str] = {}
    if args.column_mapping:
        try:
            raw = json.loads(args.column_mapping)
        except json.JSONDecodeError as exc:
            raise ValueError("--column-mapping must be valid JSON") from exc
        if not isinstance(raw, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in raw.items()
        ):
            raise ValueError("--column-mapping must be a JSON object of strings")
        mapping.update(raw)
    for logical, attribute in (
        ("filename", "filename_column"),
        ("title", "title_column"),
        ("url", "url_column"),
    ):
        value = getattr(args, attribute)
        if value:
            mapping[logical] = value
    return mapping


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point."""

    args = build_parser().parse_args(argv)
    if args.command == "evaluate":
        return evaluate(args.config)
    if args.command == "inspect-corpus":
        try:
            mapping = _event_column_mapping(args)
        except ValueError as exc:
            print(f"Corpus intake BLOCKED: {exc}", file=sys.stderr)
            return 2
        return inspect_corpus(args.root, args.manifest, args.output, mapping)
    if args.command == "smoke-corpus":
        try:
            mapping = _event_column_mapping(args)
        except ValueError as exc:
            print(f"Corpus compatibility FAIL: {exc}", file=sys.stderr)
            return 2
        return smoke_corpus(args.root, args.manifest, args.cases, args.output, mapping)
    if args.command == "demo-build":
        try:
            result = build_demo(args.config)
        except (DemoContractError, DemoSecurityError, ValueError, FileNotFoundError) as exc:
            print(f"Event demo FAIL: {exc}", file=sys.stderr)
            return 1
        print(
            "Event demo PASS: stories "
            f"{len(result.stories)}/{len(result.stories)}; dashboard metrics sourced; "
            "self-contained HTML 2/2; external assets 0; network disabled."
        )
        return 0
    if args.command == "demo-case":
        try:
            story = build_demo_case(args.config, args.case, args.output)
        except (
            DemoContractError,
            DemoSecurityError,
            ValueError,
            FileNotFoundError,
            KeyError,
        ) as exc:
            print(f"Demo case FAIL: {exc}", file=sys.stderr)
            return 1
        evidence_valid = story.decision == "CLARIFY" or bool(story.evidence)
        print(
            f"Demo case PASS: {story.case_id}; decision {story.decision}; "
            f"evidence {'valid' if evidence_valid else 'not measured'}; external assets 0."
        )
        return 0
    if args.command == "demo-query":
        try:
            if args.context_file is not None and not args.context_id:
                raise ValueError("--context-id is required with --context-file")
            context = (
                load_context_file(args.context_file, args.context_id)
                if args.context_file is not None
                else {}
            )
            story = run_live_query(args.config, args.question, context, args.output)
        except (
            DemoContractError,
            DemoSecurityError,
            ValueError,
            FileNotFoundError,
            KeyError,
        ) as exc:
            print(f"Demo query FAIL: {exc}", file=sys.stderr)
            return 1
        print(f"Demo query PASS: decision {story.decision}; external assets 0; network disabled.")
        return 0
    if args.command == "pitch-build":
        from riskon.pitch.errors import PitchError
        from riskon.pitch.reporting import build_pitch

        try:
            pitch_result = build_pitch(args.config)
        except (PitchError, FileNotFoundError, ValueError, OSError) as exc:
            print(f"Event pitch FAIL: {exc}", file=sys.stderr)
            return 1
        report = pitch_result.report
        print(
            "Event pitch PASS: slides "
            f"{report.slide_count}/12; timing profiles {report.timing_profile_count}/3; "
            f"live demo {report.live_demo_seconds}s; Q&A bank complete; "
            "backup demo self-contained; external assets "
            f"{report.external_asset_count}; network disabled."
        )
        return 0
    if args.command == "pitch-validate":
        from riskon.pitch.reporting import validate_pitch

        try:
            report = validate_pitch(args.config)
        except (ValueError, FileNotFoundError, OSError) as exc:
            print(f"Event pitch VALIDATION FAIL: {exc}", file=sys.stderr)
            return 1
        if report.passed:
            print(
                "Event pitch VALID: slides "
                f"{report.slide_count}/12; timing profiles {report.timing_profile_count}/3; "
                f"canonical script {report.canonical_duration_seconds}s; live demo "
                f"{report.live_demo_seconds}s; Q&A topics {report.qa_topic_count}/18; "
                f"backup scenes {report.backup_scene_count}/6; metrics sourced "
                f"{report.metric_source_count}/{report.metric_source_expected}; "
                f"network violations {report.network_violation_count}."
            )
            return 0
        print("Event pitch VALIDATION FAIL: " + "; ".join(report.errors), file=sys.stderr)
        return 1
    if args.command == "pitch-script":
        from riskon.pitch.errors import PitchError
        from riskon.pitch.reporting import build_pitch_script

        try:
            path = build_pitch_script(args.config, args.profile)
        except (PitchError, FileNotFoundError, ValueError, OSError) as exc:
            print(f"Event pitch script FAIL: {exc}", file=sys.stderr)
            return 1
        print(f"Event pitch script PASS: profile {args.profile}; output {path}.")
        return 0
    return run_query(args.config, args.query, args.context_json)
