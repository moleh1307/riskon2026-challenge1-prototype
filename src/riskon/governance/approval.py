"""Human-decision validation for M5B patches."""

from riskon.governance.errors import MissingHumanApprovalError, SelfApprovalError
from riskon.governance.models import ActorType, ApprovalDecision, ExpertResolution, HumanApproval


def validate_human_approval(
    resolution: ExpertResolution,
    approval: HumanApproval | None,
    *,
    require_approve: bool = False,
) -> tuple[bool, str]:
    """Validate actor type, patch identity, and separation of duties."""

    if approval is None:
        return False, "no human approval record is present"
    if approval.actor_type is not ActorType.HUMAN_ROLE:
        return False, "approval actor is not a HUMAN_ROLE"
    if approval.patch_id == "":
        return False, "approval has no patch identifier"
    if approval.actor_role_id == resolution.resolution_author_role_id:
        return False, "resolution author and approval actor are identical"
    if require_approve and approval.decision is not ApprovalDecision.APPROVE:
        return False, "approval decision is not APPROVE"
    return True, "independent human decision is valid"


def require_approvable(
    resolution: ExpertResolution,
    approval: HumanApproval | None,
) -> HumanApproval:
    """Return an approval suitable for activation or raise a typed error."""

    if approval is None:
        raise MissingHumanApprovalError("A human approval is required before activation")
    if approval.actor_role_id == resolution.resolution_author_role_id:
        raise SelfApprovalError("The resolution author cannot approve the same patch")
    if approval.actor_type is not ActorType.HUMAN_ROLE:
        raise MissingHumanApprovalError("Only HUMAN_ROLE actors may approve a patch")
    if approval.decision is not ApprovalDecision.APPROVE:
        raise MissingHumanApprovalError("The supplied human decision is not an approval")
    return approval
