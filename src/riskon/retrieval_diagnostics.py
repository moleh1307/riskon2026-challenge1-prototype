"""Deterministic diagnostics for M2 channel ranking and fusion."""

from __future__ import annotations

from dataclasses import dataclass

from riskon.models import RetrievalChannel, RetrievalDiagnostic, RetrievalDiagnostics

ALLOWED_EXCLUSION_REASONS = {
    "CONTEXT_CONFLICT",
    "DUPLICATE_EVIDENCE",
    "BELOW_CHANNEL_THRESHOLD",
    "NOT_SELECTED_TOP_K",
}


@dataclass(frozen=True)
class ChannelObservation:
    """One candidate emitted by a retrieval channel."""

    plan_id: str
    subquery: str
    channel: RetrievalChannel
    candidate_ref: str
    channel_rank: int
    raw_score: float


def build_diagnostics(
    observations: list[ChannelObservation],
    *,
    rrf_contributions: dict[tuple[str, RetrievalChannel, str], float],
    final_ranks: dict[tuple[str, str], int],
    included: set[tuple[str, str]],
    exclusion_reasons: dict[tuple[str, str], str],
) -> RetrievalDiagnostics:
    """Materialise one closed diagnostic record per channel observation."""

    entries: list[RetrievalDiagnostic] = []
    for observation in observations:
        key = (observation.subquery, observation.candidate_ref)
        exclusion_reason = exclusion_reasons.get(key)
        if exclusion_reason is not None and exclusion_reason not in ALLOWED_EXCLUSION_REASONS:
            raise ValueError(f"Unsupported M2 exclusion reason: {exclusion_reason}")
        entries.append(
            RetrievalDiagnostic(
                plan_id=observation.plan_id,
                subquery=observation.subquery,
                channel=observation.channel,
                candidate_ref=observation.candidate_ref,
                channel_rank=observation.channel_rank,
                raw_score=observation.raw_score,
                rrf_contribution=rrf_contributions.get(
                    (observation.subquery, observation.channel, observation.candidate_ref),
                    0.0,
                ),
                final_rank=final_ranks.get(key),
                included=key in included,
                exclusion_reason=exclusion_reason,
            )
        )
    entries.sort(
        key=lambda item: (
            item.subquery,
            item.final_rank or 10**9,
            item.candidate_ref,
            item.channel.value,
        )
    )
    return RetrievalDiagnostics(entries=entries)
