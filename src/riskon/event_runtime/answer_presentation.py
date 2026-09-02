"""Deterministic presentation of validated structural evidence.

The structural worker admits source-derived records; it does not write prose or
make the final decision.  This module only projects those already-admitted
records into a compact answer shape so raw evidence serialisations do not leak
into the user-facing response.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from riskon.event_runtime.structural_matrix import StructuralEvidenceClaim

_MEANING_ORDER = {
    "session and overnight": 0,
    "only session": 1,
    "only overnight": 2,
    "not activated": 3,
    "non-critical": 4,
}


def format_structural_answer(
    claims: Sequence[StructuralEvidenceClaim],
    *,
    approved_claim_ids: Collection[str] | None = None,
) -> str:
    """Format source-declared matrix records without adding new facts.

    Only claims whose IDs are explicitly approved are included.  Scope,
    columns, states, and meanings are copied from the validated structural
    records.  A missing page-declared meaning remains visibly unresolved.
    """

    approved = set(approved_claim_ids) if approved_claim_ids is not None else None
    selected = [claim for claim in claims if approved is None or claim.claim_id in approved]
    if not selected:
        return ""

    lines: list[str] = []
    scope = _scope_line(selected[0].applicable_scope, selected[0].table_heading)
    if scope:
        lines.append(f"Scope: {scope}")
        lines.append("")
    grouped: dict[tuple[str, str], list[StructuralEvidenceClaim]] = {}
    first_seen: dict[tuple[str, str], int] = {}
    unresolved: list[StructuralEvidenceClaim] = []
    for index, claim in enumerate(selected):
        meaning = _normalise(claim.state_meaning)
        if not meaning:
            unresolved.append(claim)
            continue
        key = (meaning, _normalise(claim.state))
        grouped.setdefault(key, []).append(claim)
        first_seen.setdefault(key, index)

    ordered_groups = sorted(
        grouped.items(),
        key=lambda item: (
            _MEANING_ORDER.get(item[0][0], len(_MEANING_ORDER)),
            first_seen[item[0]],
        ),
    )
    if grouped:
        lines.append("Source-declared alert configuration")
    for index, ((meaning, state), group) in enumerate(ordered_groups):
        if index or lines[-1] != "Source-declared alert configuration":
            lines.append("")
        lines.append(f"{_display_meaning(meaning)} ({state})")
        lines.extend(f"- {_display_column(claim.column)}" for claim in group)

    if unresolved:
        if grouped:
            lines.append("")
            lines.append("Unresolved source state")
        elif lines and lines[-1] != "":
            lines.append("")
        lines.extend(
            f"- {_display_column(claim.column)} is marked `{claim.state}`. "
            "The page does not declare what "
            "this icon means, so its meaning cannot be determined from this page."
            for claim in unresolved
        )

    return "\n".join(lines)


def _normalise(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _display_meaning(value: str) -> str:
    return value[:1].upper() + value[1:]


def _display_column(value: str) -> str:
    prefix = "suitability / monitoring alerts "
    lowered = value.casefold()
    return value[len(prefix) :] if lowered.startswith(prefix) else value


def _scope_line(scope: dict[str, str], table_heading: str) -> str:
    parts = [table_heading.strip()] if table_heading.strip() else []
    parts.extend(f"{field}: {value}" for field, value in scope.items())
    return " · ".join(parts)


__all__ = ["format_structural_answer"]
