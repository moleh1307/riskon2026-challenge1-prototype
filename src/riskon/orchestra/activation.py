"""Fail-closed activation validation for M4A and M4B profiles."""

from riskon.models import Decision
from riskon.orchestra.models import ActivationProfile, OrchestraContext
from riskon.orchestra.policy import ActivationPolicy

M4A_SUPPORTED_PROFILES = (
    ActivationProfile.FAST_PATH,
    ActivationProfile.SHORT_CIRCUIT_CLARIFY,
    ActivationProfile.HUMAN_FIRST,
)

M4B_SUPPORTED_PROFILES = (
    ActivationProfile.DUAL_CHECK,
    ActivationProfile.FULL_ORCHESTRA,
)

M4C_SUPPORTED_PROFILES = (ActivationProfile.FULL_ORCHESTRA,)


def validate_m4a_activation(
    policy: ActivationPolicy,
    profile_value: ActivationProfile | str,
    baseline_decision: Decision,
    context: OrchestraContext,
) -> ActivationProfile:
    """Validate profile, baseline decision, signals, and routing-context relation."""

    profile = policy.coerce_profile(profile_value)
    signals = policy.validate_risk_signals(context.risk_signals)
    spec = policy.profile(profile)

    if profile is ActivationProfile.FAST_PATH:
        if baseline_decision is not Decision.ANSWER:
            raise ValueError("FAST_PATH requires a baseline ANSWER")
        if signals:
            raise ValueError("FAST_PATH requires empty risk_signals")
        if context.routing_context is not None:
            raise ValueError("FAST_PATH requires routing_context=None")
    elif profile is ActivationProfile.SHORT_CIRCUIT_CLARIFY:
        if baseline_decision is not Decision.CLARIFY:
            raise ValueError("SHORT_CIRCUIT_CLARIFY requires a baseline CLARIFY")
        if context.routing_context is not None:
            raise ValueError("SHORT_CIRCUIT_CLARIFY requires routing_context=None")
        if not set(map(str, signals)) & {str(signal) for signal in spec.trigger_signals}:
            raise ValueError("SHORT_CIRCUIT_CLARIFY requires a declared trigger signal")
    elif profile is ActivationProfile.HUMAN_FIRST:
        if baseline_decision is not Decision.ABSTAIN:
            raise ValueError("HUMAN_FIRST requires a baseline ABSTAIN")
        if context.routing_context is None:
            raise ValueError("HUMAN_FIRST requires routing_context")
        if not set(map(str, signals)) & {str(signal) for signal in spec.trigger_signals}:
            raise ValueError("HUMAN_FIRST requires a declared trigger signal")
    return profile


def validate_m4b_activation(
    policy: ActivationPolicy,
    profile_value: ActivationProfile | str,
    baseline_decision: Decision,
    context: OrchestraContext,
) -> ActivationProfile:
    """Validate a worker-backed profile against the frozen M4 policy."""

    del baseline_decision
    profile = policy.coerce_profile(profile_value)
    if profile not in M4B_SUPPORTED_PROFILES:
        raise ValueError(f"M4B does not implement activation profile {profile.value}")
    signals = policy.validate_risk_signals(context.risk_signals)
    spec = policy.profile(profile)
    if not signals:
        raise ValueError(f"{profile.value} requires at least one declared risk signal")
    trigger_signals = {str(signal) for signal in spec.trigger_signals}
    if not trigger_signals.intersection(map(str, signals)):
        raise ValueError(f"{profile.value} received signals outside its trigger set")
    return profile


def validate_m4c_activation(
    policy: ActivationPolicy,
    profile_value: ActivationProfile | str,
    baseline_decision: Decision,
    context: OrchestraContext,
) -> ActivationProfile:
    """Validate the bounded counterfactual profile and its activation signal."""

    profile = policy.coerce_profile(profile_value)
    if profile not in M4C_SUPPORTED_PROFILES:
        raise ValueError(f"M4C does not implement activation profile {profile.value}")
    if baseline_decision is not Decision.ANSWER:
        raise ValueError("M4C requires a baseline ANSWER")
    signals = policy.validate_risk_signals(context.risk_signals)
    if "COUNTERFACTUAL_REQUIRED" not in {str(signal) for signal in signals}:
        raise ValueError("M4C requires the COUNTERFACTUAL_REQUIRED signal")
    return profile
