"""M1, M2, M3, M4A, M4B, M4D, and M5B report writers."""

import json
from pathlib import Path

from riskon.evaluation import (
    M1EvaluationDocument,
    M2EvaluationDocument,
    M3EvaluationDocument,
    M4AEvaluationDocument,
    M4BEvaluationDocument,
    M4CEvaluationDocument,
    M4DEvaluationDocument,
)
from riskon.m5b_evaluation import M5BEvaluationDocument


def write_reports(document: M1EvaluationDocument, generated_root: Path) -> tuple[Path, Path]:
    """Write the canonical machine-readable and human-readable M1 reports."""

    generated_root.mkdir(parents=True, exist_ok=True)
    json_path = generated_root / "evaluation.json"
    markdown_path = generated_root / "evaluation.md"
    json_path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(document), encoding="utf-8")
    return json_path, markdown_path


def render_markdown(document: M1EvaluationDocument) -> str:
    """Render all required metric names and case-level failures."""

    metrics = document.metrics.model_dump(mode="json")
    lines = [
        "# M1 Evaluation Report",
        "",
        "M1 is a deterministic synthetic evidence-contract regression run.",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{name}` | `{value}` |" for name, value in metrics.items())
    lines.extend(
        [
            "",
            "## M0 regression",
            "",
            f"Matched `{document.m0_regression['matched']}/"
            f"{document.m0_regression['expected']}` M0 cases.",
            "",
            "## Scenario results",
            "",
        ]
    )
    for scenario in document.scenario_results:
        status = "PASS" if scenario.matched else "FAIL"
        lines.append(f"### {scenario.id} — {status}")
        lines.append("")
        lines.append(
            f"Decision: `{scenario.actual_decision}`; reasons: `{scenario.actual_reason_codes}`."
        )
        if scenario.failures:
            lines.append("")
            lines.append("Failures:")
            lines.extend(f"- {failure}" for failure in scenario.failures)
        lines.append("")
    return "\n".join(lines)


def write_m2_reports(document: M2EvaluationDocument, generated_root: Path) -> tuple[Path, Path]:
    """Write the canonical machine-readable and human-readable M2 reports."""

    generated_root.mkdir(parents=True, exist_ok=True)
    json_path = generated_root / "evaluation.json"
    markdown_path = generated_root / "evaluation.md"
    diagnostics_path = generated_root / "retrieval_diagnostics.jsonl"
    json_path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_m2_markdown(document), encoding="utf-8")
    diagnostic_lines: list[str] = []
    for scenario in document.scenario_results:
        payload = scenario.result.get("diagnostics", {})
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        for entry in entries:
            if isinstance(entry, dict):
                diagnostic_lines.append(
                    json.dumps(
                        {"scenario_id": scenario.id, **entry},
                        sort_keys=True,
                    )
                )
    diagnostics_path.write_text(
        "\n".join(diagnostic_lines) + ("\n" if diagnostic_lines else ""),
        encoding="utf-8",
    )
    return json_path, markdown_path


def render_m2_markdown(document: M2EvaluationDocument) -> str:
    """Render all required M2 metrics and case-level diagnostics."""

    metrics = document.metrics.model_dump(mode="json")
    lines = [
        "# M2 Evaluation Report",
        "",
        "M2 is a deterministic synthetic context-aware hybrid retrieval regression run.",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{name}` | `{value}` |" for name, value in metrics.items())
    lines.extend(
        [
            "",
            "## Regressions",
            "",
            f"M0 matched `{document.m0_regression['matched']}/"
            f"{document.m0_regression['expected']}`.",
            f"M1-new matched `{document.m1_regression['matched']}/"
            f"{document.m1_regression['expected']}`.",
            "",
            "## M2 scenario results",
            "",
        ]
    )
    for scenario in document.scenario_results:
        status = "PASS" if scenario.matched else "FAIL"
        lines.append(f"### {scenario.id} — {status}")
        lines.append("")
        lines.append(
            f"Decision: `{scenario.actual_decision}`; reasons: `{scenario.actual_reason_codes}`."
        )
        lines.append(f"Top-1: `{scenario.actual_top1_refs}`.")
        if scenario.failures:
            lines.append("")
            lines.append("Failures:")
            lines.extend(f"- {failure}" for failure in scenario.failures)
        lines.append("")
    return "\n".join(lines)


def write_m3_reports(document: M3EvaluationDocument, generated_root: Path) -> tuple[Path, Path]:
    """Write canonical M3 evaluation and routing-diagnostics reports."""

    generated_root.mkdir(parents=True, exist_ok=True)
    json_path = generated_root / "evaluation.json"
    markdown_path = generated_root / "evaluation.md"
    diagnostics_path = generated_root / "routing_diagnostics.jsonl"
    json_path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_m3_markdown(document), encoding="utf-8")
    diagnostic_lines: list[str] = []
    for scenario in document.scenario_results:
        routed = scenario.result.get("routed_run", {})
        diagnostics = routed.get("routing_diagnostics", {}) if isinstance(routed, dict) else {}
        if isinstance(diagnostics, dict):
            diagnostic_lines.append(
                json.dumps({"scenario_id": scenario.id, **diagnostics}, sort_keys=True)
            )
    diagnostics_path.write_text(
        "\n".join(diagnostic_lines) + ("\n" if diagnostic_lines else ""),
        encoding="utf-8",
    )
    return json_path, markdown_path


def render_m3_markdown(document: M3EvaluationDocument) -> str:
    """Render M3 metrics without exposing raw upstream query text."""

    metrics = document.metrics.model_dump(mode="json")
    lines = [
        "# M3 Evaluation Report",
        "",
        "M3 is a deterministic synthetic configurable expert-routing regression run.",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{name}` | `{value}` |" for name, value in metrics.items())
    lines.extend(
        [
            "",
            "## Regressions",
            "",
            f"M0 matched `{document.m0_regression['matched']}/"
            f"{document.m0_regression['expected']}`.",
            f"M1-new matched `{document.m1_regression['matched']}/"
            f"{document.m1_regression['expected']}`.",
            f"M2-new matched `{document.m2_regression['matched']}/"
            f"{document.m2_regression['expected']}`.",
            "",
            "## M3 routing cases",
            "",
        ]
    )
    for scenario in document.scenario_results:
        status = "PASS" if scenario.matched else "FAIL"
        lines.append(f"### {scenario.id} — {status}")
        lines.append("")
        lines.append(
            f"Decision: `{scenario.actual_decision}`; route status: `{scenario.routing_status}`."
        )
        lines.append(f"Candidates: `{scenario.candidate_expert_ids}`.")
        if scenario.failures:
            lines.append("")
            lines.append("Failures:")
            lines.extend(f"- {failure}" for failure in scenario.failures)
        lines.append("")
    return "\n".join(lines)


def write_m4a_reports(document: M4AEvaluationDocument, generated_root: Path) -> tuple[Path, Path]:
    """Write canonical M4A evaluation JSON and Markdown reports."""

    generated_root.mkdir(parents=True, exist_ok=True)
    json_path = generated_root / "evaluation.json"
    markdown_path = generated_root / "evaluation.md"
    json_path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_m4a_markdown(document), encoding="utf-8")
    return json_path, markdown_path


def render_m4a_markdown(document: M4AEvaluationDocument) -> str:
    """Render M4A metrics and explicitly state the M4B boundary."""

    metrics = document.metrics.model_dump(mode="json")
    lines = [
        "# M4A Evaluation Report",
        "",
        (
            "M4A is an orchestration shell with zero worker execution. It applies only "
            "FAST_PATH, SHORT_CIRCUIT_CLARIFY, and HUMAN_FIRST over frozen M0-M3 state."
        ),
        "",
        (
            "This is not an agent swarm: active agents and worker executions are both "
            "required to remain zero. DUAL_CHECK and FULL_ORCHESTRA are reserved for M4B."
        ),
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{name}` | `{value}` |" for name, value in metrics.items())
    lines.extend(
        [
            "",
            "## Regressions",
            "",
            f"M0 matched `{document.m0_regression['matched']}/"
            f"{document.m0_regression['expected']}`.",
            f"M1-new matched `{document.m1_regression['matched']}/"
            f"{document.m1_regression['expected']}`.",
            f"M2-new matched `{document.m2_regression['matched']}/"
            f"{document.m2_regression['expected']}`.",
            f"M3-new matched `{document.m3_regression['matched']}/"
            f"{document.m3_regression['expected']}`.",
            "",
            "## M4A scenarios",
            "",
        ]
    )
    for scenario in document.scenario_results:
        status = "PASS" if scenario.matched else "FAIL"
        lines.append(f"### {scenario.id} — {status}")
        lines.append("")
        lines.append(
            f"Profile: `{scenario.actual_profile}`; decision: `{scenario.actual_decision}`; "
            f"route: `{scenario.actual_route}`."
        )
        if scenario.failures:
            lines.append("")
            lines.append("Failures:")
            lines.extend(f"- {failure}" for failure in scenario.failures)
        lines.append("")
    return "\n".join(lines)


def write_m4b_reports(document: M4BEvaluationDocument, generated_root: Path) -> tuple[Path, Path]:
    """Write canonical M4B evaluation JSON and Markdown reports."""

    generated_root.mkdir(parents=True, exist_ok=True)
    json_path = generated_root / "evaluation.json"
    markdown_path = generated_root / "evaluation.md"
    json_path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_m4b_markdown(document), encoding="utf-8")
    return json_path, markdown_path


def render_m4b_markdown(document: M4BEvaluationDocument) -> str:
    """Render M4B metrics and the deterministic worker boundary."""

    metrics = document.metrics.model_dump(mode="json")
    lines = [
        "# M4B Evaluation Report",
        "",
        "M4B uses deterministic bounded workers.",
        "It does not yet use an LLM or claim to be a model-driven swarm.",
        "",
        "Workers investigate local synthetic evidence; existing M1 verification and the "
        "material-objection gate retain final decision authority.",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{name}` | `{value}` |" for name, value in metrics.items())
    lines.extend(
        [
            "",
            "## Contract and regressions",
            "",
            f"M4 contract matched `{document.m4_contract['matched']}/"
            f"{document.m4_contract['expected']}` frozen fixtures.",
            f"M4A matched `{document.m4a_regression['matched']}/"
            f"{document.m4a_regression['expected']}`.",
            f"M0 matched `{document.m0_regression['matched']}/"
            f"{document.m0_regression['expected']}`.",
            f"M1-new matched `{document.m1_regression['matched']}/"
            f"{document.m1_regression['expected']}`.",
            f"M2-new matched `{document.m2_regression['matched']}/"
            f"{document.m2_regression['expected']}`.",
            f"M3-new matched `{document.m3_regression['matched']}/"
            f"{document.m3_regression['expected']}`.",
            "",
            "## M4B scenarios",
            "",
        ]
    )
    for scenario in document.scenario_results:
        status = "PASS" if scenario.matched else "FAIL"
        lines.append(f"### {scenario.id} — {status}")
        lines.append("")
        lines.append(
            f"Profile: `{scenario.actual_profile}`; decision: `{scenario.actual_decision}`; "
            f"tasks: `{scenario.actual_task_count}`; route: `{scenario.actual_route}`."
        )
        if scenario.failures:
            lines.append("")
            lines.append("Failures:")
            lines.extend(f"- {failure}" for failure in scenario.failures)
        lines.append("")
    return "\n".join(lines)


def write_m4c_reports(document: M4CEvaluationDocument, generated_root: Path) -> tuple[Path, Path]:
    """Write canonical M4C evaluation JSON and Markdown reports."""

    generated_root.mkdir(parents=True, exist_ok=True)
    json_path = generated_root / "evaluation.json"
    markdown_path = generated_root / "evaluation.md"
    json_path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_m4c_markdown(document), encoding="utf-8")
    return json_path, markdown_path


def render_m4c_markdown(document: M4CEvaluationDocument) -> str:
    """Render M4C transition metrics and the frozen-fixture boundary."""

    metrics = document.metrics.model_dump(mode="json")
    lines = [
        "# M4C Evaluation Report",
        "",
        (
            "Canonical M4C evaluation uses frozen synthetic counterfactual "
            "PlannedVerifiedRun fixtures to isolate transition adjudication from upstream "
            "retrieval drift."
        ),
        "",
        "A separate local run_planned adapter is implemented and tested for normal runtime use.",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{name}` | `{value}` |" for name, value in metrics.items())
    lines.extend(
        [
            "",
            "## Contract and regressions",
            "",
            f"M4 contract matched `{document.m4_contract['matched']}/"
            f"{document.m4_contract['expected']}`.",
            f"M4A matched `{document.m4a_regression['matched']}/"
            f"{document.m4a_regression['expected']}`.",
            f"M4B matched `{document.m4b_regression['matched']}/"
            f"{document.m4b_regression['expected']}`.",
            f"M0-M3 matched `{document.m0_m3_regression['matched']}/"
            f"{document.m0_m3_regression['expected']}`.",
            "",
            "## M4C scenarios",
            "",
        ]
    )
    for scenario in document.scenario_results:
        status = "PASS" if scenario.matched else "FAIL"
        lines.append(f"### {scenario.id} — {status}")
        lines.append("")
        lines.append(
            f"Decision: `{scenario.actual_decision}`; variants: "
            f"`{scenario.actual_variant_count}`; scope leaks: `{scenario.actual_scope_leak_count}`."
        )
        if scenario.failures:
            lines.append("")
            lines.append("Failures:")
            lines.extend(f"- {failure}" for failure in scenario.failures)
        lines.append("")
    return "\n".join(lines)


def write_m4d_reports(document: M4DEvaluationDocument, generated_root: Path) -> tuple[Path, Path]:
    """Write canonical M4D evaluation JSON and Markdown reports."""

    generated_root.mkdir(parents=True, exist_ok=True)
    json_path = generated_root / "evaluation.json"
    markdown_path = generated_root / "evaluation.md"
    json_path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_m4d_markdown(document), encoding="utf-8")
    return json_path, markdown_path


def render_m4d_markdown(document: M4DEvaluationDocument) -> str:
    """Render M4D metrics, safety contracts, and upstream regressions."""

    metrics = document.metrics.model_dump(mode="json")
    lines = [
        "# M4D Evaluation Report",
        "",
        "M4D is a unified deterministic orchestra runtime.",
        "",
        "It runs bounded specialist workers and local counterfactual checks,",
        "but it does not yet use an LLM or claim model-driven agent autonomy.",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{name}` | `{value}` |" for name, value in metrics.items())
    lines.extend(
        [
            "",
            "## Regressions",
            "",
            f"M4D cases matched `{document.m4d_contract['matched']}/"
            f"{document.m4d_contract['expected']}`.",
            f"M4 frozen contract matched `{document.m4_frozen_contract['matched']}/"
            f"{document.m4_frozen_contract['expected']}`.",
            f"M4A matched `{document.m4a_regression['matched']}/"
            f"{document.m4a_regression['expected']}`.",
            f"M4B matched `{document.m4b_regression['matched']}/"
            f"{document.m4b_regression['expected']}`.",
            f"M4C matched `{document.m4c_regression['matched']}/"
            f"{document.m4c_regression['expected']}`.",
            f"M0-M3 matched `{document.m0_m3_regression['matched']}/"
            f"{document.m0_m3_regression['expected']}`.",
            "",
            "## M4D scenarios",
            "",
        ]
    )
    for scenario in document.scenario_results:
        status = "PASS" if scenario.matched else "FAIL"
        lines.append(f"### {scenario.id} — {status}")
        lines.append("")
        lines.append(
            f"Profile: `{scenario.actual_profile}`; baseline: "
            f"`{scenario.actual_baseline_decision}`; final: `{scenario.actual_final_decision}`."
        )
        lines.append(f"Signals: `{scenario.actual_risk_signals}`.")
        if scenario.failures:
            lines.append("")
            lines.append("Failures:")
            lines.extend(f"- {failure}" for failure in scenario.failures)
        lines.append("")
    return "\n".join(lines)


def write_m5b_reports(document: M5BEvaluationDocument, generated_root: Path) -> tuple[Path, Path]:
    """Write the canonical M5B machine-readable and human-readable reports."""

    generated_root.mkdir(parents=True, exist_ok=True)
    json_path = generated_root / "evaluation.json"
    markdown_path = generated_root / "evaluation.md"
    json_path.write_text(
        json.dumps(document.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_m5b_markdown(document), encoding="utf-8")
    return json_path, markdown_path


def render_m5b_markdown(document: M5BEvaluationDocument) -> str:
    """Render M5B governance decisions and its architecture boundary."""

    metrics = document.metrics.model_dump(mode="json")
    lines = [
        "# M5B Evaluation Report",
        "",
        "M5B is a deterministic governed knowledge-overlay evaluation over frozen M5A cases.",
        "",
        "M5B does not train or fine-tune a model from expert conversations.",
        "",
        "It converts structured expert resolutions into proposed knowledge",
        "patches and activates them only after mandatory Policy CI checks,",
        "separate human approval, and explicit release activation.",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{name}` | `{value}` |" for name, value in metrics.items())
    lines.extend(["", "## Cases", ""])
    for case in document.case_results:
        status = "PASS" if case.matched else "FAIL"
        lines.extend(
            [
                f"### {case.case_id} — {status}",
                "",
                "Patch status: "
                f"`{case.actual_patch_status}`; release: `{case.actual_active_release}`.",
                f"Policy CI: `{case.policy_ci_phase.value}`; post-patch: `{case.post_patch}`.",
            ]
        )
        if case.failures:
            lines.extend(["", "Failures:", *[f"- {failure}" for failure in case.failures]])
        lines.append("")
    lines.extend(
        [
            "## Governance boundary",
            "",
            "Expert resolution proposes. Policy CI tests. A human approves. A release activates.",
            "Official corpus mutation, automatic approval, automatic activation, and "
            "network access remain disabled.",
        ]
    )
    return "\n".join(lines) + "\n"
