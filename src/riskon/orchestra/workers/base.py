"""Shared interfaces and pure helpers for isolated M4B workers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol

from riskon.models import Section
from riskon.orchestra.models import (
    AgentFinding,
    FindingStance,
    MaterialObjection,
    WorkerContext,
    WorkerDiagnostic,
    WorkerResult,
)
from riskon.orchestra.source_safety import LocalCorpus, SourceSafetyContext


class Worker(Protocol):
    """Async worker boundary consumed by the bounded executor."""

    async def run(self, context: WorkerContext) -> WorkerResult:
        """Return an isolated result without mutating shared state."""


def corpus_for(context: WorkerContext) -> LocalCorpus:
    """Read the local corpus from the worker context."""

    corpus = context.local_corpus_config
    if not isinstance(corpus, LocalCorpus):
        raise TypeError("M4B worker context does not contain a LocalCorpus")
    return corpus


def safety_for(context: WorkerContext) -> SourceSafetyContext:
    """Read source-safety state from the worker context."""

    safety = context.source_safety_policy
    if not isinstance(safety, SourceSafetyContext):
        raise TypeError("M4B worker context does not contain SourceSafetyContext")
    return safety


def query_for(context: WorkerContext) -> str:
    """Return the frozen normalised query visible to a worker."""

    return context.baseline_run.query_plan.normalised_query


def sections_with_filename(corpus: LocalCorpus, filename: str) -> list[Section]:
    """Return sections for one manifest filename in stable order."""

    return sorted(
        (section for section in corpus.sections if section.filename == filename),
        key=lambda section: (section.source_ref, section.section_id),
    )


def section_ref(corpus: LocalCorpus, section: Section) -> str:
    """Return the M4 section-level provenance address."""

    return corpus.provenance.section_ref(section)


def infer_scope(section: Section, text: str, fallback: str = "LOCAL_SYNTHETIC") -> str:
    """Infer a compact source scope from explicit source data."""

    lowered = f"{section.text} {text}".lower()
    if "active control" in lowered or "client acceptance" in lowered:
        return "ACTIVE_CONTROL"
    if "region_beta" in lowered and "service_basic" in lowered:
        return "REGION_BETA/SERVICE_BASIC"
    if "region_beta" in lowered:
        return "REGION_BETA"
    if "region_alpha" in lowered:
        return "REGION_ALPHA"
    if "interactive_session" in lowered and "premium" in lowered:
        return "INTERACTIVE_SESSION/REGION_ALPHA/PREMIUM"
    if "overnight_monitoring" in lowered and "premium" in lowered:
        return "OVERNIGHT_MONITORING/REGION_ALPHA/PREMIUM"
    if "untrusted instruction" in lowered or "prompt" in lowered:
        return "UNTRUSTED_SOURCE_CONTENT"
    return fallback


def claim_id_for_text(text: str, explicit: str | None = None) -> str:
    """Return a stable semantic claim identifier from source content."""

    if explicit:
        return explicit
    lowered = text.lower()
    if "must not continue" in lowered or "do not proceed" in lowered:
        return "do_not_proceed"
    if "client acceptance does not override" in lowered:
        return "client_acceptance_does_not_override"
    if "region_beta" in lowered and "synthetic advisory review rule applies" in lowered:
        return "region_beta_scope_rule"
    if "control atlas" in lowered and "service_basic" in lowered:
        return "control_atlas_applicability"
    if "requires a local evidence reference" in lowered:
        return "prompt_safe_control_rule"
    words = re.findall(r"[a-z0-9]+", lowered)
    return "claim-" + "-".join(words[:6]) if words else "claim-unknown"


def claim_texts_for_section(
    corpus: LocalCorpus,
    section: Section,
    claim_id: str,
) -> list[tuple[str, str]]:
    """Return source texts and refs that semantically match one claim."""

    results: list[tuple[str, str]] = []
    section_address = section_ref(corpus, section)
    declared_text = section.claims.get(claim_id)
    if declared_text:
        for unit in corpus.provenance.units_for_section(section.section_id):
            if unit.claim_id == claim_id:
                results.append((unit.ref, declared_text))
        if not results:
            results.append((section_address, declared_text))
    for block in section.lists:
        for item in block.items:
            explicit_claim = item.split(":", 1)[0].strip() if ":" in item else None
            item_text = item.split(":", 1)[1].strip() if explicit_claim else item
            item_claim = claim_id_for_text(item_text, explicit_claim)
            if item_claim == claim_id:
                results.append((section_address, item_text))
    for paragraph in section.paragraphs:
        if claim_id_for_text(paragraph) == claim_id or section.claims.get(claim_id) == paragraph:
            for unit in corpus.provenance.units_for_section(section.section_id):
                if unit.kind == "sentence" and unit.text == paragraph:
                    results.append((unit.ref, unit.text))
            if not any(ref == section_address and text == paragraph for ref, text in results):
                results.append((section_address, paragraph))
    address = corpus.provenance.section_address(section.section_id)
    if address is not None:
        for ref in address.table_row_refs:
            resolved_unit = corpus.provenance.resolve(ref)
            if (
                resolved_unit is not None
                and claim_id_for_text(resolved_unit.text, resolved_unit.claim_id) == claim_id
            ):
                results.append((ref, resolved_unit.text))
    return list(dict.fromkeys(results))


def unit_text(corpus: LocalCorpus, reference: str, claim_id: str) -> str:
    """Resolve a claim's source text without copying unrelated source content."""

    unit = corpus.resolve(reference)
    if unit is None:
        raise ValueError(f"Unknown M4 source reference: {reference}")
    section = corpus.section_for_reference(reference)
    if section is not None:
        matches = claim_texts_for_section(corpus, section, claim_id)
        for ref, text in matches:
            if ref == reference:
                return text
        if matches:
            return matches[0][1]
    return unit.text


def make_finding(
    context: WorkerContext,
    ordinal: int,
    *,
    claim_id: str,
    stance: FindingStance,
    evidence_refs: Iterable[str],
    source_scope: str,
    criticality: str,
    limitations: Iterable[str] = (),
) -> AgentFinding:
    """Construct one isolated deterministic finding."""

    task = context.task
    return AgentFinding(
        finding_id=f"finding:{task.task_id}:{ordinal:03d}",
        task_id=task.task_id,
        agent_id=task.agent_id,
        agent_role=task.agent_role,
        claim_id=claim_id,
        stance=stance,
        evidence_refs=list(dict.fromkeys(evidence_refs)),
        source_scope=source_scope,
        criticality=criticality,
        limitations=list(dict.fromkeys(limitations)),
    )


def make_objection(
    context: WorkerContext,
    ordinal: int,
    *,
    target_claim_id: str,
    reason_code: str,
    materiality: str,
    evidence_refs: Iterable[str],
    status: str,
    resolvable_by: str,
) -> MaterialObjection:
    """Construct one retained material-objection record."""

    return MaterialObjection(
        objection_id=f"objection:{context.task.task_id}:{ordinal:03d}",
        agent_id=context.task.agent_id,
        target_claim_id=target_claim_id,
        reason_code=reason_code,
        materiality=materiality,
        evidence_refs=list(dict.fromkeys(evidence_refs)),
        status=status,
        resolvable_by=resolvable_by,
    )


def make_diagnostic(
    context: WorkerContext,
    ordinal: int,
    *,
    code: str,
    message: str,
    evidence_refs: Iterable[str] = (),
) -> WorkerDiagnostic:
    """Construct a safe diagnostic without raw source text."""

    return WorkerDiagnostic(
        diagnostic_id=f"diagnostic:{context.task.task_id}:{ordinal:03d}",
        task_id=context.task.task_id,
        agent_id=context.task.agent_id,
        agent_role=context.task.agent_role,
        code=code,
        message=message,
        evidence_refs=list(dict.fromkeys(evidence_refs)),
    )
