"""Deterministic bounded challenge worker."""

from collections import defaultdict

from riskon.orchestra.models import (
    AgentFinding,
    FindingStance,
    MaterialObjection,
    WorkerContext,
    WorkerDiagnostic,
    WorkerResult,
)
from riskon.orchestra.workers.base import (
    claim_texts_for_section,
    corpus_for,
    make_diagnostic,
    make_finding,
    make_objection,
    query_for,
    safety_for,
    section_ref,
    sections_with_filename,
)


class Skeptic:
    """Try to break candidate claims using only the bounded discovery envelope."""

    async def run(self, context: WorkerContext) -> WorkerResult:
        corpus = corpus_for(context)
        safety = safety_for(context)
        query = query_for(context).lower()
        findings: list[AgentFinding] = []
        objections: list[MaterialObjection] = []
        diagnostics: list[WorkerDiagnostic] = []

        if "synthetic atlas control" in query and "client accepts" in query:
            for section in sections_with_filename(corpus, "atlas_critical_control.html"):
                ref = section_ref(corpus, section)
                if not safety.policy.evidence_allowed(ref, safety.report):
                    continue
                matches = claim_texts_for_section(
                    corpus, section, "atlas_client_acceptance_no_override"
                )
                if matches:
                    findings.append(
                        make_finding(
                            context,
                            len(findings) + 1,
                            claim_id="atlas_client_acceptance_no_override",
                            stance=FindingStance.SUPPORT,
                            evidence_refs=[matches[0][0]],
                            source_scope="ACTIVE_CONTROL",
                            criticality="CRITICAL",
                        )
                    )
                    break

        elif "bypass" in query and "acceptance" in query:
            for section in sections_with_filename(corpus, "active_control.html"):
                ref = section_ref(corpus, section)
                if not safety.policy.evidence_allowed(ref, safety.report):
                    continue
                matches = claim_texts_for_section(
                    corpus, section, "client_acceptance_does_not_override"
                )
                if matches:
                    findings.append(
                        make_finding(
                            context,
                            len(findings) + 1,
                            claim_id="client_acceptance_does_not_override",
                            stance=FindingStance.SUPPORT,
                            evidence_refs=[ref],
                            source_scope="ACTIVE_CONTROL",
                            criticality="CRITICAL",
                        )
                    )
                    objections.append(
                        make_objection(
                            context,
                            len(objections) + 1,
                            target_claim_id="active_control_set",
                            reason_code="CRITICAL_CONTROL_OMITTED",
                            materiality="MATERIAL",
                            evidence_refs=[ref],
                            status="RESOLVED",
                            resolvable_by="EVIDENCE_SCOUT",
                        )
                    )
                    break

        if "region alpha rule" in query and "region beta" in query:
            beta_findings = [
                finding
                for finding in context.prior_findings
                if finding.claim_id == "region_beta_scope_rule"
            ]
            if beta_findings:
                finding = beta_findings[0]
                findings.append(
                    make_finding(
                        context,
                        len(findings) + 1,
                        claim_id=finding.claim_id,
                        stance=FindingStance.NEUTRAL,
                        evidence_refs=finding.evidence_refs,
                        source_scope=finding.source_scope,
                        criticality="NORMAL",
                    )
                )

        if "scoped rule" in query:
            supports = [
                finding
                for finding in context.prior_findings
                if finding.claim_id == "service_model_scope_rule"
                and finding.stance is FindingStance.SUPPORT
            ]
            if supports:
                finding = supports[0]
                findings.append(
                    make_finding(
                        context,
                        len(findings) + 1,
                        claim_id=finding.claim_id,
                        stance=FindingStance.CHALLENGE,
                        evidence_refs=finding.evidence_refs,
                        source_scope=finding.source_scope,
                        criticality="CRITICAL",
                        limitations=[
                            "A baseline answer is not enough without transition validation"
                        ],
                    )
                )

        if "which alerts" in query:
            for section in corpus.sections:
                if section.filename != "alert_configuration.html" or not section.tables:
                    continue
                address = corpus.provenance.section_address(section.section_id)
                if address is None:
                    continue
                table = section.tables[0]
                headers = [header.lower() for header in table.headers]
                stage_index = headers.index("workflow stage") if "workflow stage" in headers else -1
                if stage_index < 0:
                    continue
                for index, row in enumerate(table.rows):
                    if index >= len(address.table_row_refs) or len(row) <= stage_index:
                        continue
                    if str(row[stage_index]).upper() != "OVERNIGHT_MONITORING":
                        continue
                    ref = address.table_row_refs[index]
                    findings.append(
                        make_finding(
                            context,
                            len(findings) + 1,
                            claim_id="filtered_alert_set",
                            stance=FindingStance.CHALLENGE,
                            evidence_refs=[ref],
                            source_scope="OVERNIGHT_MONITORING/REGION_ALPHA/PREMIUM",
                            criticality="NORMAL",
                            limitations=["Excluded from the interactive-session answer"],
                        )
                    )
                    break

        support_by_claim: dict[str, list[AgentFinding]] = defaultdict(list)
        for finding in context.prior_findings:
            if finding.stance is FindingStance.SUPPORT:
                support_by_claim[finding.claim_id].append(finding)
        for claim_id, supports in sorted(support_by_claim.items()):
            evidence_refs = sorted(
                {reference for finding in supports for reference in finding.evidence_refs}
            )
            if len(evidence_refs) < 2:
                continue
            findings.append(
                make_finding(
                    context,
                    len(findings) + 1,
                    claim_id=claim_id,
                    stance=FindingStance.CHALLENGE,
                    evidence_refs=evidence_refs,
                    source_scope=supports[0].source_scope,
                    criticality="CRITICAL",
                    limitations=["Both sources declare synthetic-equivalent authority"],
                )
            )
            objections.append(
                make_objection(
                    context,
                    len(objections) + 1,
                    target_claim_id=claim_id,
                    reason_code="CONTRADICTORY_EVIDENCE",
                    materiality="MATERIAL",
                    evidence_refs=evidence_refs,
                    status="OPEN",
                    resolvable_by="M1_VERIFICATION_AUTHORITY",
                )
            )

        signals = {str(signal) for signal in context.orchestra_context.risk_signals}
        if "PROMPT_INJECTION_SIGNAL" in signals:
            for source_diagnostic in safety.report.diagnostics:
                references = list(source_diagnostic.evidence_refs)
                findings.append(
                    make_finding(
                        context,
                        len(findings) + 1,
                        claim_id="source_instruction",
                        stance=FindingStance.CHALLENGE,
                        evidence_refs=references,
                        source_scope="UNTRUSTED_SOURCE_CONTENT",
                        criticality="CRITICAL",
                        limitations=["Instruction text is not evidence"],
                    )
                )
                diagnostics.append(
                    make_diagnostic(
                        context,
                        len(diagnostics) + 1,
                        code=source_diagnostic.diagnostic_code,
                        message="Suspicious source instruction was ignored as non-evidence.",
                        evidence_refs=references,
                    )
                )

        return WorkerResult(
            task_id=context.task.task_id,
            agent_id=context.task.agent_id,
            agent_role=context.task.agent_role,
            findings=findings,
            material_objections=objections,
            diagnostics=diagnostics,
        )
