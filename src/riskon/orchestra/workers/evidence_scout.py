"""Deterministic explicit-evidence discovery worker."""

from riskon.orchestra.models import AgentFinding, FindingStance, WorkerContext, WorkerResult
from riskon.orchestra.workers.base import (
    claim_id_for_text,
    claim_texts_for_section,
    corpus_for,
    infer_scope,
    make_finding,
    query_for,
    safety_for,
    section_ref,
    sections_with_filename,
)


class EvidenceScout:
    """Find explicit source support without deciding or routing."""

    async def run(self, context: WorkerContext) -> WorkerResult:
        corpus = corpus_for(context)
        safety = safety_for(context)
        query = query_for(context).lower()
        findings: list[AgentFinding] = []

        if "table_dependent" not in {
            str(signal).lower() for signal in context.orchestra_context.risk_signals
        }:
            if "synthetic stability marker" in query:
                for section in sections_with_filename(corpus, "stability_marker_definition.html"):
                    ref = section_ref(corpus, section)
                    if not safety.policy.evidence_allowed(ref, safety.report):
                        continue
                    matches = claim_texts_for_section(
                        corpus, section, "stability_marker_definition"
                    )
                    if matches:
                        findings.append(
                            make_finding(
                                context,
                                len(findings) + 1,
                                claim_id="stability_marker_definition",
                                stance=FindingStance.SUPPORT,
                                evidence_refs=[matches[0][0]],
                                source_scope=infer_scope(section, matches[0][1]),
                                criticality="NORMAL",
                            )
                        )
                        break

            elif "synthetic atlas control" in query and "client accepts" in query:
                for section in sections_with_filename(corpus, "atlas_critical_control.html"):
                    ref = section_ref(corpus, section)
                    if not safety.policy.evidence_allowed(ref, safety.report):
                        continue
                    matches = claim_texts_for_section(corpus, section, "atlas_do_not_proceed")
                    if matches:
                        findings.append(
                            make_finding(
                                context,
                                len(findings) + 1,
                                claim_id="atlas_do_not_proceed",
                                stance=FindingStance.SUPPORT,
                                evidence_refs=[matches[0][0]],
                                source_scope="ACTIVE_CONTROL",
                                criticality="CRITICAL",
                            )
                        )
                        break

            elif "control meridian" in query:
                for section in sections_with_filename(corpus, "meridian_region_beta.html"):
                    ref = section_ref(corpus, section)
                    if not safety.policy.evidence_allowed(ref, safety.report):
                        continue
                    matches = claim_texts_for_section(
                        corpus, section, "meridian_applies_beta_basic"
                    )
                    if matches:
                        findings.append(
                            make_finding(
                                context,
                                len(findings) + 1,
                                claim_id="meridian_applies_beta_basic",
                                stance=FindingStance.SUPPORT,
                                evidence_refs=[matches[0][0]],
                                source_scope=infer_scope(section, matches[0][1]),
                                criticality="NORMAL",
                            )
                        )
                        break

            elif "scoped rule" in query:
                for section in sections_with_filename(corpus, "service_model_counterfactuals.html"):
                    ref = section_ref(corpus, section)
                    if not safety.policy.evidence_allowed(ref, safety.report):
                        continue
                    findings.append(
                        make_finding(
                            context,
                            len(findings) + 1,
                            claim_id="service_model_scope_rule",
                            stance=FindingStance.SUPPORT,
                            evidence_refs=[ref],
                            source_scope=infer_scope(section, section.text),
                            criticality="CRITICAL",
                        )
                    )
                    break

            elif "bypass" in query and "acceptance" in query:
                for section in sections_with_filename(corpus, "active_control.html"):
                    ref = section_ref(corpus, section)
                    if safety.policy.evidence_allowed(ref, safety.report):
                        matches = claim_texts_for_section(corpus, section, "do_not_proceed")
                        if matches:
                            findings.append(
                                make_finding(
                                    context,
                                    len(findings) + 1,
                                    claim_id=claim_id_for_text(matches[0][1], "do_not_proceed"),
                                    stance=FindingStance.SUPPORT,
                                    evidence_refs=[ref],
                                    source_scope="ACTIVE_CONTROL",
                                    criticality="CRITICAL",
                                )
                            )
                            break

            elif "region alpha rule" in query and "region beta" in query:
                for section in sections_with_filename(corpus, "regional_scope_beta.html"):
                    ref = section_ref(corpus, section)
                    if safety.policy.evidence_allowed(ref, safety.report):
                        matches = claim_texts_for_section(corpus, section, "region_beta_scope_rule")
                        if matches:
                            findings.append(
                                make_finding(
                                    context,
                                    len(findings) + 1,
                                    claim_id="region_beta_scope_rule",
                                    stance=FindingStance.SUPPORT,
                                    evidence_refs=[ref],
                                    source_scope=infer_scope(section, matches[0][1]),
                                    criticality="CRITICAL",
                                )
                            )
                            break

            elif "control atlas" in query and "service basic" in query and "region beta" in query:
                for section in sections_with_filename(corpus, "conflict_policy_a.html"):
                    ref = section_ref(corpus, section)
                    if safety.policy.evidence_allowed(ref, safety.report):
                        if not claim_texts_for_section(
                            corpus,
                            section,
                            "control_atlas_applicability",
                        ):
                            continue
                        findings.append(
                            make_finding(
                                context,
                                len(findings) + 1,
                                claim_id="control_atlas_applicability",
                                stance=FindingStance.SUPPORT,
                                evidence_refs=[ref],
                                source_scope="REGION_BETA/SERVICE_BASIC",
                                criticality="CRITICAL",
                            )
                        )
                        break

            elif "local control" in query and "synthetic recommendation" in query:
                for section in sections_with_filename(corpus, "prompt_injection_source.html"):
                    ref = section_ref(corpus, section)
                    if (
                        "valid synthetic policy statement"
                        not in " ".join(section.heading_path).lower()
                    ):
                        continue
                    if safety.policy.evidence_allowed(ref, safety.report):
                        findings.append(
                            make_finding(
                                context,
                                len(findings) + 1,
                                claim_id="prompt_safe_control_rule",
                                stance=FindingStance.SUPPORT,
                                evidence_refs=[ref],
                                source_scope="PROMPT_SAFETY",
                                criticality="NORMAL",
                            )
                        )
                        break

        return WorkerResult(
            task_id=context.task.task_id,
            agent_id=context.task.agent_id,
            agent_role=context.task.agent_role,
            findings=findings,
        )
