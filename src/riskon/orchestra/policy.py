"""Loader and validator for the frozen M4 activation policy."""

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riskon.models import Decision
from riskon.orchestra.models import ActivationProfile, RiskSignal


class ActivationProfileSpec(BaseModel):
    """One closed profile declaration from ``activation_policy.json``."""

    model_config = ConfigDict(extra="forbid")

    profile_id: ActivationProfile
    trigger_signals: tuple[RiskSignal, ...]
    available_worker_roles: tuple[str, ...]
    worker_activation: str = Field(min_length=1)
    baseline_decision: Decision | None = None
    requires_empty_risk_signals: bool = False
    final_decision_behavior: str = Field(min_length=1)


class ActivationPolicyDocument(BaseModel):
    """Schema for the frozen activation-policy document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    precedence: tuple[ActivationProfile, ...]
    profiles: tuple[ActivationProfileSpec, ...]


EXPECTED_PRECEDENCE = (
    ActivationProfile.SHORT_CIRCUIT_CLARIFY,
    ActivationProfile.HUMAN_FIRST,
    ActivationProfile.FULL_ORCHESTRA,
    ActivationProfile.DUAL_CHECK,
    ActivationProfile.FAST_PATH,
)


class ActivationPolicy:
    """Immutable in-memory view of the frozen activation policy."""

    def __init__(
        self,
        document: ActivationPolicyDocument,
        source_path: Path,
    ) -> None:
        self.source_path = source_path
        self.precedence = tuple(document.precedence)
        profile_map = {
            profile.profile_id: profile.model_copy(deep=True) for profile in document.profiles
        }
        self._profiles = MappingProxyType(profile_map)
        self.declared_signals = frozenset(
            str(signal) for profile in document.profiles for signal in profile.trigger_signals
        )

    @classmethod
    def from_file(cls, path: Path) -> "ActivationPolicy":
        """Load and validate a policy without mutating the source document."""

        resolved_path = path.resolve()
        if not resolved_path.is_file():
            raise FileNotFoundError(f"Activation policy not found: {resolved_path}")
        raw_value = json.loads(resolved_path.read_text(encoding="utf-8"))
        if not isinstance(raw_value, dict):
            raise ValueError("Activation policy must be a JSON object")
        expected_keys = {"schema_version", "precedence", "profiles"}
        if set(raw_value) != expected_keys:
            raise ValueError("Activation policy fields do not match the frozen schema")

        raw_precedence = raw_value["precedence"]
        raw_profiles = raw_value["profiles"]
        if not isinstance(raw_precedence, list) or not isinstance(raw_profiles, list):
            raise ValueError("Activation policy precedence and profiles must be arrays")
        raw_profile_ids = [
            profile.get("profile_id") for profile in raw_profiles if isinstance(profile, dict)
        ]
        if len(raw_profile_ids) != len(raw_profiles):
            raise ValueError("Every activation policy profile must be an object")
        if len(set(raw_profile_ids)) != len(raw_profile_ids):
            raise ValueError("Activation policy contains duplicate profiles")

        try:
            document = ActivationPolicyDocument.model_validate(raw_value)
        except Exception as exc:
            raise ValueError(f"Invalid activation policy: {exc}") from exc
        if document.schema_version != "1.0":
            raise ValueError("Unsupported activation policy schema")
        if document.precedence != EXPECTED_PRECEDENCE:
            raise ValueError("Activation policy precedence does not match the frozen order")
        if tuple(
            document.profiles[index].profile_id for index in range(len(document.profiles))
        ) != (EXPECTED_PRECEDENCE):
            raise ValueError("Activation policy profile order does not match precedence")
        return cls(document, resolved_path)

    @property
    def profiles(self) -> tuple[ActivationProfileSpec, ...]:
        """Return detached profile copies so callers cannot mutate policy state."""

        return tuple(profile.model_copy(deep=True) for profile in self._profiles.values())

    def profile(self, value: ActivationProfile | str) -> ActivationProfileSpec:
        """Return a detached declaration for one profile."""

        profile = self.coerce_profile(value)
        declared = self._profiles.get(profile)
        if declared is None:
            raise ValueError(f"Unknown activation profile: {profile.value}")
        return declared.model_copy(deep=True)

    def coerce_profile(self, value: ActivationProfile | str) -> ActivationProfile:
        """Convert a public profile value and reject unknown profiles."""

        try:
            return value if isinstance(value, ActivationProfile) else ActivationProfile(value)
        except ValueError as exc:
            raise ValueError(f"Unknown activation profile: {value!r}") from exc

    def validate_risk_signals(
        self, values: tuple[RiskSignal, ...] | list[RiskSignal]
    ) -> tuple[RiskSignal, ...]:
        """Validate all signals against the policy-declared vocabulary."""

        validated = tuple(RiskSignal(str(value)) for value in values)
        unknown = sorted(
            {str(value) for value in validated if str(value) not in self.declared_signals}
        )
        if unknown:
            raise ValueError(f"Unknown M4 risk signal(s): {unknown}")
        return validated

    def is_declared_signal(self, value: str) -> bool:
        """Return whether a signal is declared by the loaded policy."""

        return value in self.declared_signals

    def as_dict(self) -> dict[str, Any]:
        """Return a detached JSON-shaped policy snapshot for diagnostics/tests."""

        return {
            "schema_version": "1.0",
            "precedence": [profile.value for profile in self.precedence],
            "profiles": [profile.model_dump(mode="json") for profile in self.profiles],
        }


class WorkerSignalMapping(BaseModel):
    """One signal-to-worker mapping in the M4B execution policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_signal: RiskSignal
    required_agent_roles: tuple[str, ...]
    status: str = Field(min_length=1)


class WorkerSelectionPolicyDocument(BaseModel):
    """Schema for the bounded M4B worker-selection policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    backend: str
    maximum_worker_depth: int
    maximum_parallel_discovery_workers: int
    maximum_challenge_rounds: int
    canonical_role_order: tuple[str, ...]
    signal_mappings: tuple[WorkerSignalMapping, ...]


class WorkerSelectionPolicy:
    """Immutable signal-driven worker selection without case-ID branching."""

    def __init__(
        self,
        document: WorkerSelectionPolicyDocument,
        source_path: Path,
    ) -> None:
        self.source_path = source_path
        self.schema_version = document.schema_version
        self.backend = document.backend
        self.maximum_worker_depth = document.maximum_worker_depth
        self.maximum_parallel_discovery_workers = document.maximum_parallel_discovery_workers
        self.maximum_challenge_rounds = document.maximum_challenge_rounds
        self.canonical_role_order = tuple(document.canonical_role_order)
        mapping = {
            str(item.risk_signal): item.model_copy(deep=True) for item in document.signal_mappings
        }
        self._signal_mappings = MappingProxyType(mapping)

    @classmethod
    def from_file(cls, path: Path) -> "WorkerSelectionPolicy":
        """Load the closed M4B policy and fail closed on schema drift."""

        resolved_path = path.resolve()
        if not resolved_path.is_file():
            raise FileNotFoundError(f"M4B worker selection policy not found: {resolved_path}")
        try:
            raw_value = json.loads(resolved_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid M4B worker selection policy: {exc}") from exc
        if not isinstance(raw_value, dict):
            raise ValueError("M4B worker selection policy must be a JSON object")
        expected_keys = {
            "schema_version",
            "backend",
            "maximum_worker_depth",
            "maximum_parallel_discovery_workers",
            "maximum_challenge_rounds",
            "canonical_role_order",
            "signal_mappings",
        }
        if set(raw_value) != expected_keys:
            raise ValueError("M4B worker selection policy fields do not match the frozen schema")
        try:
            document = WorkerSelectionPolicyDocument.model_validate(raw_value)
        except Exception as exc:
            raise ValueError(f"Invalid M4B worker selection policy: {exc}") from exc
        if document.schema_version != "1.0":
            raise ValueError("Unsupported M4B worker selection policy schema")
        if document.backend != "DETERMINISTIC_WORKER_V1":
            raise ValueError("M4B worker selection backend is not deterministic")
        if (
            document.maximum_worker_depth != 1
            or document.maximum_parallel_discovery_workers != 3
            or document.maximum_challenge_rounds != 1
        ):
            raise ValueError("M4B worker bounds do not match the frozen contract")
        if not document.canonical_role_order or len(set(document.canonical_role_order)) != len(
            document.canonical_role_order
        ):
            raise ValueError("M4B canonical role order must be unique and non-empty")
        signal_ids = [str(item.risk_signal) for item in document.signal_mappings]
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("M4B worker selection policy contains duplicate signals")
        if any(not item.required_agent_roles for item in document.signal_mappings):
            raise ValueError("Every M4B signal mapping must declare a worker role")
        if any(
            role not in document.canonical_role_order
            for item in document.signal_mappings
            for role in item.required_agent_roles
        ):
            raise ValueError("M4B signal mapping contains a role outside canonical_role_order")
        if any(
            item.status not in {"IMPLEMENTED", "NOT_IMPLEMENTED"}
            for item in document.signal_mappings
        ):
            raise ValueError("M4B signal mapping status is invalid")
        return cls(document, resolved_path)

    @property
    def signal_mappings(self) -> tuple[WorkerSignalMapping, ...]:
        """Return detached mapping copies."""

        return tuple(item.model_copy(deep=True) for item in self._signal_mappings.values())

    def mapping(self, signal: RiskSignal | str) -> WorkerSignalMapping:
        """Return the policy mapping for one declared signal."""

        key = str(signal)
        mapping = self._signal_mappings.get(key)
        if mapping is None:
            raise ValueError(f"Unknown M4B worker-selection signal: {key}")
        return mapping.model_copy(deep=True)

    def required_agent_roles(
        self,
        signals: tuple[RiskSignal, ...] | list[RiskSignal],
    ) -> list[str]:
        """Union mapped roles and return them in canonical policy order."""

        selected: set[str] = set()
        for signal in signals:
            selected.update(self.mapping(signal).required_agent_roles)
        return [role for role in self.canonical_role_order if role in selected]

    def status_for(self, signal: RiskSignal | str) -> str:
        """Return the implementation status declared for one signal."""

        return self.mapping(signal).status

    def as_dict(self) -> dict[str, Any]:
        """Return a detached JSON-shaped policy snapshot."""

        return {
            "schema_version": self.schema_version,
            "backend": self.backend,
            "maximum_worker_depth": self.maximum_worker_depth,
            "maximum_parallel_discovery_workers": self.maximum_parallel_discovery_workers,
            "maximum_challenge_rounds": self.maximum_challenge_rounds,
            "canonical_role_order": list(self.canonical_role_order),
            "signal_mappings": [item.model_dump(mode="json") for item in self.signal_mappings],
        }
