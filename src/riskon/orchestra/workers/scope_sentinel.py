"""Deterministic source-scope discovery worker."""

from riskon.orchestra.models import (
    AgentFinding,
    FindingStance,
    MaterialObjection,
    WorkerContext,
    WorkerResult,
)
from riskon.orchestra.workers.base import (
    claim_texts_for_section,
    corpus_for,
    infer_scope,
    make_finding,
    make_objection,
    query_for,
    safety_for,
    section_ref,
    sections_with_filename,
)


class ScopeSentinel:
    """Detect explicit region/service scope conflicts without deciding."""

    async def run(self, context: WorkerContext) -> WorkerResult:
        corpus = corpus_for(context)
        safety = safety_for(context)
        query = query_for(context).lower()
        findings: list[AgentFinding] = []
        objections: list[MaterialObjection] = []

        if "control meridian" in query:
            for section in sections_with_filename(corpus, "meridian_region_beta.html"):
                ref = section_ref(corpus, section)
                if not safety.policy.evidence_allowed(ref, safety.report):
                    continue
                matches = claim_texts_for_section(corpus, section, "meridian_applies_beta_basic")
                if matches:
                    findings.append(
                        make_finding(
                            context,
                            len(findings) + 1,
                            claim_id="meridian_applies_beta_basic",
                            stance=FindingStance.NEUTRAL,
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
                        stance=FindingStance.CHALLENGE,
                        evidence_refs=[ref],
                        source_scope=infer_scope(section, section.text),
                        criticality="CRITICAL",
                        limitations=["Rule is not portable outside its explicit service scope"],
                    )
                )
                break

        elif "region alpha rule" in query and "region beta" in query:
            for section in sections_with_filename(corpus, "regional_scope_alpha.html"):
                ref = section_ref(corpus, section)
                if not safety.policy.evidence_allowed(ref, safety.report):
                    continue
                if "must not be used to support a region beta case" not in section.text.lower():
                    continue
                findings.append(
                    make_finding(
                        context,
                        len(findings) + 1,
                        claim_id="region_alpha_distractor",
                        stance=FindingStance.CHALLENGE,
                        evidence_refs=[ref],
                        source_scope="REGION_ALPHA",
                        criticality="CRITICAL",
                        limitations=["Not valid for REGION_BETA"],
                    )
                )
                objections.append(
                    make_objection(
                        context,
                        len(objections) + 1,
                        target_claim_id="region_alpha_distractor",
                        reason_code="SCOPE_CONFLICT",
                        materiality="MATERIAL",
                        evidence_refs=[ref],
                        status="RESOLVED",
                        resolvable_by="SCOPE_SENTINEL",
                    )
                )
                break

        elif "control atlas" in query and "service basic" in query and "region beta" in query:
            sections = sections_with_filename(corpus, "conflict_policy_b.html")
            for section in sections:
                ref = section_ref(corpus, section)
                if not safety.policy.evidence_allowed(ref, safety.report):
                    continue
                if not claim_texts_for_section(corpus, section, "control_atlas_applicability"):
                    continue
                findings.append(
                    make_finding(
                        context,
                        len(findings) + 1,
                        claim_id="control_atlas_applicability",
                        stance=FindingStance.SUPPORT,
                        evidence_refs=[ref],
                        source_scope=infer_scope(section, section.text),
                        criticality="CRITICAL",
                    )
                )
                break

        return WorkerResult(
            task_id=context.task.task_id,
            agent_id=context.task.agent_id,
            agent_role=context.task.agent_role,
            findings=findings,
            material_objections=objections,
        )
