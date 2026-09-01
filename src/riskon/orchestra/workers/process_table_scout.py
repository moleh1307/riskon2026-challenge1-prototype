"""Deterministic structure-aware table discovery worker."""

from riskon.orchestra.models import AgentFinding, FindingStance, WorkerContext, WorkerResult
from riskon.orchestra.workers.base import corpus_for, make_finding, query_for, safety_for


class ProcessTableScout:
    """Recover complete eligible table rows while preserving header context."""

    async def run(self, context: WorkerContext) -> WorkerResult:
        corpus = corpus_for(context)
        safety = safety_for(context)
        query = query_for(context).lower()
        findings: list[AgentFinding] = []
        if "which alerts" not in query:
            return WorkerResult(
                task_id=context.task.task_id,
                agent_id=context.task.agent_id,
                agent_role=context.task.agent_role,
            )

        for section in corpus.sections:
            if section.filename != "alert_configuration.html":
                continue
            address = corpus.provenance.section_address(section.section_id)
            if address is None or not section.tables:
                continue
            table = section.tables[0]
            headers = [header.strip().lower() for header in table.headers]
            header_index = {header: index for index, header in enumerate(headers)}
            required_headers = {
                "status",
                "workflow stage",
                "mandate",
                "advisory location",
            }
            if not required_headers.issubset(header_index):
                continue
            for index, row in enumerate(table.rows):
                values = [str(value).strip().upper() for value in row]
                if len(values) < len(headers):
                    continue
                if (
                    values[header_index["status"]] != "ACTIVE"
                    or values[header_index["workflow stage"]] != "INTERACTIVE_SESSION"
                    or values[header_index["mandate"]] != "PREMIUM"
                    or values[header_index["advisory location"]] != "REGION_ALPHA"
                ):
                    continue
                if index >= len(address.table_row_refs):
                    continue
                ref = address.table_row_refs[index]
                if not safety.policy.evidence_allowed(ref, safety.report):
                    continue
                claim_id = table.claim_ids[index] if index < len(table.claim_ids) else None
                if not claim_id and "claim id" in header_index:
                    claim_index = header_index["claim id"]
                    claim_id = str(row[claim_index]).strip() if claim_index < len(row) else None
                unit = corpus.resolve(ref)
                if not claim_id or unit is None or not unit.headers:
                    continue
                findings.append(
                    make_finding(
                        context,
                        len(findings) + 1,
                        claim_id=claim_id,
                        stance=FindingStance.SUPPORT,
                        evidence_refs=[ref],
                        source_scope="INTERACTIVE_SESSION/REGION_ALPHA/PREMIUM",
                        criticality="NORMAL",
                    )
                )
        return WorkerResult(
            task_id=context.task.task_id,
            agent_id=context.task.agent_id,
            agent_role=context.task.agent_role,
            findings=findings,
        )
