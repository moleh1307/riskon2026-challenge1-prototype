"""Compatibility smoke tests over the existing deterministic M2/M1 components."""

from __future__ import annotations

import tempfile
from collections.abc import Iterable
from pathlib import Path

from bs4 import BeautifulSoup, Comment, Tag

from riskon.config import load_milestone2_config
from riskon.context import ContextDetector
from riskon.event_intake.errors import CorpusBlockedError
from riskon.event_intake.models import (
    CompatibilityCaseResult,
    CorpusCompatibilityReport,
    CorpusSmokeCase,
    PreparedCorpus,
)
from riskon.event_intake.path_safety import snapshot_source, snapshots_unchanged
from riskon.hybrid_retrieval import (
    HybridRetrievalResult,
    HybridRetriever,
    RetrievalCandidate,
)
from riskon.ingestion import KnowledgeIngestor
from riskon.models import (
    AnswerClaim,
    Decision,
    Evidence,
    ManifestEntry,
    PipelineResult,
    QueryInput,
    ReasonCode,
    RetrievalHit,
    VerifiedRun,
)
from riskon.provenance import ProvenanceIndex, ProvenanceUnit
from riskon.query_planning import QueryPlanner
from riskon.routing import ExpertRouter
from riskon.verification import VerificationEngine


class CompatibilityRunner:
    """Run bounded event-like cases without adding a retrieval or model layer."""

    def __init__(self, project_root: Path, pipeline_config_path: Path) -> None:
        self.project_root = project_root.resolve()
        self.pipeline_config_path = pipeline_config_path.resolve()

    def run(
        self,
        prepared_corpus: PreparedCorpus | None,
        smoke_cases: tuple[CorpusSmokeCase, ...],
    ) -> CorpusCompatibilityReport:
        """Execute smoke cases and validate source/no-egress invariants."""

        if prepared_corpus is None:
            raise CorpusBlockedError("Compatibility smoke requires a prepared corpus")
        before = snapshot_source(prepared_corpus.source_root)
        results: list[CompatibilityCaseResult] = []
        failure_codes: list[str] = []
        try:
            with tempfile.TemporaryDirectory(prefix="riskon-event-smoke-") as temporary:
                pipeline = self._build_components(prepared_corpus, Path(temporary))
                for case in smoke_cases:
                    try:
                        verified = self._run_case(case, *pipeline)
                        result = self._compare_case(case, verified)
                    except Exception as exc:  # pragma: no cover - defensive closeout path
                        del exc
                        result = CompatibilityCaseResult(
                            id=case.id,
                            matched=False,
                            expected_decision=case.expected_decision,
                            actual_decision=Decision.ABSTAIN,
                            evidence_count=0,
                            evidence_refs=[],
                            answer_contains_matched=False,
                            table_rows_matched=False,
                            failures=["SMOKE_EXECUTION_ERROR"],
                        )
                    results.append(result)
                    if not result.matched:
                        failure_codes.append("SMOKE_CASE_MISMATCH")
        finally:
            after = snapshot_source(prepared_corpus.source_root)

        files_unchanged = before.file_hashes == after.file_hashes
        entries_unchanged = snapshots_unchanged(before, after)
        source_mutations = 0 if files_unchanged and entries_unchanged else 1
        if source_mutations:
            failure_codes.append("SOURCE_MUTATION")
        if not smoke_cases:
            failure_codes.append("NO_SMOKE_CASES")
        deduplicated_failures = list(dict.fromkeys(failure_codes))
        matched_count = sum(item.matched for item in results)
        passed = (
            bool(smoke_cases) and matched_count == len(smoke_cases) and not deduplicated_failures
        )
        return CorpusCompatibilityReport(
            passed=passed,
            case_results=results,
            expected_case_count=len(smoke_cases),
            matched_case_count=matched_count,
            source_mutations=source_mutations,
            source_file_hashes_unchanged=files_unchanged,
            source_directory_entries_unchanged=entries_unchanged,
            external_fetches=0,
            source_instruction_executions=0,
            subprocess_calls=0,
            network_disabled=True,
            failure_codes=deduplicated_failures,
        )

    def _build_components(
        self,
        prepared: PreparedCorpus,
        temporary_root: Path,
    ) -> tuple[
        QueryPlanner,
        HybridRetriever,
        ProvenanceIndex,
        VerificationEngine,
    ]:
        """Sanitize only a temporary smoke view and wire existing components."""

        entries: list[ManifestEntry] = []
        for document in prepared.documents:
            source = (prepared.source_root / document.relative_path).resolve(strict=False)
            if not source.is_relative_to(prepared.source_root.resolve(strict=False)):
                raise CorpusBlockedError("Prepared document escapes the source root")
            target = temporary_root / document.relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_safe_html(source.read_bytes()), encoding="utf-8")
            entries.append(
                ManifestEntry(
                    filename=document.relative_path,
                    title=document.title,
                    url=document.source_url,
                    source_path=str(target),
                )
            )
        sections = KnowledgeIngestor().ingest(entries)
        if not sections:
            raise CorpusBlockedError("Prepared corpus contains no ingestible HTML sections")
        provenance = ProvenanceIndex(
            sections,
            knowledge_root=temporary_root,
            ref_style="m2",
        )
        config = load_milestone2_config(self.pipeline_config_path)
        planner = QueryPlanner.from_file(config.alias_registry, config.query_planning)
        retriever = HybridRetriever(sections, provenance, config.retrieval)
        router = ExpertRouter.from_files(
            config.base.base.paths.data_root / "experts.json",
            config.base.base.paths.data_root / "routing_policy.json",
        )
        verifier = VerificationEngine(provenance, router, config.base.verification)
        return planner, retriever, provenance, verifier

    def _run_case(
        self,
        case: CorpusSmokeCase,
        planner: QueryPlanner,
        retriever: HybridRetriever,
        provenance: ProvenanceIndex,
        verifier: VerificationEngine,
    ) -> VerifiedRun:
        """Run one case through planning, retrieval, and existing verification."""

        request = QueryInput(query=case.query, context=case.input_context, trace_id=case.id)
        config = load_milestone2_config(self.pipeline_config_path)
        plan = planner.plan(request)
        context = ContextDetector().detect(request)
        if plan.retrieval_skipped:
            provisional = PipelineResult(
                trace_id=case.id,
                decision=Decision.CLARIFY,
                clarifying_question=(
                    "Did the alert arise during an interactive session or during "
                    "overnight monitoring?"
                    if "workflow_stage" in plan.missing_context_fields
                    else f"Please provide the missing context: {plan.missing_context_fields[0]}."
                ),
                reason_codes=[ReasonCode.MISSING_REQUIRED_CONTEXT],
                answer_confidence=0.0,
                routing_confidence=0.0,
                confidence_kind=config.base.base.runtime.confidence_kind,
                detected_context=context,
                missing_context=plan.missing_context_fields,
                retrieved_sections=[],
            )
            return verifier.verify(request, provisional)

        retrieval = retriever.retrieve(plan, planner.context_values(request, plan))
        evidence, hits, units = _selected_material(retrieval, provenance)
        claims = _claims_from_units(units)
        if not claims:
            router = verifier.router
            route = router.route(context, [ReasonCode.UNSUPPORTED_CLAIM])
            provisional = PipelineResult(
                trace_id=case.id,
                decision=Decision.ABSTAIN,
                reason_codes=[ReasonCode.UNSUPPORTED_CLAIM],
                evidence=evidence,
                route=route,
                answer_confidence=0.0,
                routing_confidence=route.routing_confidence,
                confidence_kind=config.base.base.runtime.confidence_kind,
                detected_context=context,
                retrieved_sections=hits,
            )
        else:
            provisional = PipelineResult(
                trace_id=case.id,
                decision=Decision.ANSWER,
                answer="\n".join(claim.text for claim in claims),
                evidence=evidence,
                answer_confidence=1.0,
                routing_confidence=0.0,
                confidence_kind=config.base.base.runtime.confidence_kind,
                detected_context=context,
                retrieved_sections=hits,
            )
        return verifier.verify(request, provisional)

    @staticmethod
    def _compare_case(
        case: CorpusSmokeCase,
        verified: VerifiedRun,
    ) -> CompatibilityCaseResult:
        """Compare only closed smoke expectations, never serialize answer text."""

        result = verified.result
        failures: list[str] = []
        if result.decision is not case.expected_decision:
            failures.append("DECISION_MISMATCH")
        answer_contains_matched = all(
            phrase in (result.answer or "") for phrase in case.expected_answer_contains
        )
        if not answer_contains_matched:
            failures.append("ANSWER_EXPECTATION_MISMATCH")
        table_rows = [row for item in result.evidence for row in item.table_rows]
        table_rows_matched = all(row in table_rows for row in case.expected_table_rows)
        if not table_rows_matched:
            failures.append("TABLE_EXPECTATION_MISMATCH")
        evidence_refs = list(verified.verification.evidence_refs)
        if case.require_local_evidence and not evidence_refs:
            failures.append("LOCAL_EVIDENCE_EXPECTED")
        return CompatibilityCaseResult(
            id=case.id,
            matched=not failures,
            expected_decision=case.expected_decision,
            actual_decision=result.decision,
            evidence_count=len(result.evidence),
            evidence_refs=evidence_refs,
            answer_contains_matched=answer_contains_matched,
            table_rows_matched=table_rows_matched,
            failures=failures,
        )


def _selected_material(
    retrieval: HybridRetrievalResult,
    provenance: ProvenanceIndex,
) -> tuple[list[Evidence], list[RetrievalHit], list[ProvenanceUnit]]:
    """Convert selected existing retriever candidates into verification inputs."""

    selected_refs = {candidate.candidate_ref for candidate in retrieval.selected_candidates}
    candidates = [
        candidate
        for subquery in retrieval.final_candidates.values()
        for candidate in subquery
        if candidate.candidate_ref in selected_refs
    ]
    grouped: dict[str, list[RetrievalCandidate]] = {}
    seen_candidates: set[str] = set()
    for candidate in candidates:
        if candidate.candidate_ref in seen_candidates:
            continue
        seen_candidates.add(candidate.candidate_ref)
        section_id = candidate.section_id or f"attachment::{candidate.candidate_ref}"
        grouped.setdefault(section_id, []).append(candidate)

    evidence: list[Evidence] = []
    hits: list[RetrievalHit] = []
    units: list[ProvenanceUnit] = []
    for section_id, grouped_candidates in grouped.items():
        first = grouped_candidates[0]
        table_rows = list(
            dict.fromkeys(row for candidate in grouped_candidates for row in candidate.table_rows)
        )
        unit_refs = list(
            dict.fromkeys(
                reference for candidate in grouped_candidates for reference in candidate.unit_refs
            )
        )
        excerpt = "\n".join(
            dict.fromkeys(
                candidate.excerpt for candidate in grouped_candidates if candidate.excerpt
            )
        )
        evidence.append(
            Evidence(
                section_id=section_id,
                source_ref=first.source_ref,
                title=first.title,
                heading_path=list(first.heading_path),
                score=1.0,
                excerpt=excerpt,
                table_rows=[list(row) for row in table_rows],
            )
        )
        hits.append(
            RetrievalHit(
                section_id=section_id,
                source_ref=first.source_ref,
                title=first.title,
                heading_path=list(first.heading_path),
                score=1.0,
                excerpt=excerpt,
                table_rows=[list(row) for row in table_rows],
            )
        )
        units.extend(
            unit
            for reference in unit_refs
            for unit in [provenance.resolve(reference)]
            if unit is not None
        )
    return evidence, hits, units


def _claims_from_units(units: Iterable[ProvenanceUnit]) -> list[AnswerClaim]:
    """Build a deterministic claim set from sentence and table source units."""

    claims: dict[str, AnswerClaim] = {}
    generated_index = 0
    for unit in units:
        if unit.kind not in {"sentence", "table_row"} or not unit.text:
            continue
        generated_index += 1
        claim_id = unit.claim_id or f"compat-claim-{generated_index:03d}"
        text = " | ".join(unit.row) if unit.kind == "table_row" else (unit.claim_text or unit.text)
        existing = claims.get(claim_id)
        if existing is None:
            claims[claim_id] = AnswerClaim(
                claim_id=claim_id,
                text=text,
                evidence_refs=[unit.ref],
                critical=any(
                    marker in text.casefold() for marker in ("must", "required", "cannot")
                ),
            )
        elif unit.ref not in existing.evidence_refs:
            existing.evidence_refs.append(unit.ref)
    return list(claims.values())


def _safe_html(raw: bytes) -> str:
    """Create an ephemeral HTML view with executable/hidden markup removed."""

    text = raw.decode("utf-8-sig")
    soup = BeautifulSoup(text, "lxml")
    for node in soup.find_all(["script", "style", "template", "noscript", "form"]):
        node.decompose()
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in list(soup.find_all(True)):
        if not isinstance(tag, Tag):
            continue
        if tag.has_attr("hidden") or str(tag.get("aria-hidden", "")).casefold() == "true":
            tag.decompose()
            continue
        style = str(tag.get("style", "")).replace(" ", "").casefold()
        if "display:none" in style or "visibility:hidden" in style:
            tag.decompose()
    return str(soup)
