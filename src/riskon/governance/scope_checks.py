"""Explicit, non-wildcard scope containment checks."""

from riskon.governance.models import ExpertResolution, KnowledgePatch, Scope


def scope_contains(container: Scope, candidate: Scope) -> tuple[bool, str]:
    """Return whether each candidate dimension is a subset of the container."""

    for dimension, values in candidate.dimensions().items():
        allowed = set(container.dimensions()[dimension])
        missing = sorted(set(values) - allowed)
        if missing:
            return False, f"{dimension} outside declared resolution scope: {', '.join(missing)}"
    return True, "patch scope is contained by resolution scope"


def scope_containment(
    resolution: ExpertResolution,
    patch: KnowledgePatch,
) -> tuple[bool, str]:
    """Apply scope containment without treating an empty dimension as global."""

    return scope_contains(resolution.scope, patch.scope)


def context_matches_scope(context: dict[str, str], scope: Scope) -> bool:
    """Check a normalized query context against explicit overlay dimensions."""

    mapping = {
        "region": scope.regions,
        "jurisdiction": scope.jurisdictions,
        "service_model": scope.service_models,
        "solicitation_type": scope.solicitation_types,
        "workflow_stage": scope.workflow_stages,
        "client_classification": scope.client_classifications,
        "system": scope.systems,
    }
    for field, values in mapping.items():
        actual = context.get(field)
        if (
            actual is not None
            and values
            and actual.upper() not in {item.upper() for item in values}
        ):
            return False
    return True
