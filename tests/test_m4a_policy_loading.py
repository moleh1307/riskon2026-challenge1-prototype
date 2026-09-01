"""Tests for the frozen M4 activation-policy loader."""

import copy
import json
from pathlib import Path

import pytest

from riskon.orchestra.models import ActivationProfile, RiskSignal
from riskon.orchestra.policy import EXPECTED_PRECEDENCE, ActivationPolicy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = PROJECT_ROOT / "data" / "synthetic" / "m4" / "activation_policy.json"


def policy_raw() -> dict[str, object]:
    """Load a detached copy of the frozen policy for negative tests."""

    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def write_policy(tmp_path: Path, raw: dict[str, object]) -> Path:
    """Write a temporary policy fixture."""

    path = tmp_path / "activation_policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_frozen_policy_loads_with_exact_precedence_and_declared_signals() -> None:
    original = POLICY_PATH.read_text(encoding="utf-8")
    policy = ActivationPolicy.from_file(POLICY_PATH)
    assert policy.precedence == EXPECTED_PRECEDENCE
    assert [profile.profile_id for profile in policy.profiles] == list(EXPECTED_PRECEDENCE)
    assert policy.is_declared_signal("APPROVAL_REQUIRED")
    assert not policy.is_declared_signal("UNKNOWN_SIGNAL")
    assert policy.profile("FAST_PATH").requires_empty_risk_signals is True
    assert policy.as_dict()["precedence"] == [profile.value for profile in EXPECTED_PRECEDENCE]
    assert POLICY_PATH.read_text(encoding="utf-8") == original


def test_policy_returns_detached_profiles_and_rejects_unknown_signals() -> None:
    policy = ActivationPolicy.from_file(POLICY_PATH)
    detached = policy.profile(ActivationProfile.FAST_PATH)
    detached.final_decision_behavior = "MUTATED_ONLY_IN_TEST"
    detached_again = policy.profile(ActivationProfile.FAST_PATH)
    assert detached_again.final_decision_behavior == "PRESERVE_BASELINE"
    assert policy.validate_risk_signals((RiskSignal("APPROVAL_REQUIRED"),)) == (
        "APPROVAL_REQUIRED",
    )
    with pytest.raises(ValueError, match="Unknown M4 risk signal"):
        policy.validate_risk_signals((RiskSignal("UNKNOWN_SIGNAL"),))


def test_policy_rejects_duplicate_profiles_wrong_precedence_and_unknown_profile(
    tmp_path: Path,
) -> None:
    original = policy_raw()

    duplicate = copy.deepcopy(original)
    profiles = duplicate["profiles"]
    assert isinstance(profiles, list)
    profiles.append(copy.deepcopy(profiles[0]))
    with pytest.raises(ValueError, match="duplicate profiles"):
        ActivationPolicy.from_file(write_policy(tmp_path, duplicate))

    wrong_order = copy.deepcopy(original)
    precedence = wrong_order["precedence"]
    assert isinstance(precedence, list)
    precedence.reverse()
    with pytest.raises(ValueError, match="precedence"):
        ActivationPolicy.from_file(write_policy(tmp_path, wrong_order))

    unknown = copy.deepcopy(original)
    unknown_profiles = unknown["profiles"]
    assert isinstance(unknown_profiles, list)
    assert isinstance(unknown_profiles[0], dict)
    unknown_profiles[0]["profile_id"] = "NOT_A_PROFILE"
    with pytest.raises(ValueError, match="Invalid activation policy|Unknown"):
        ActivationPolicy.from_file(write_policy(tmp_path, unknown))


def test_policy_rejects_schema_and_file_errors(tmp_path: Path) -> None:
    malformed = {"schema_version": "1.0", "precedence": [], "profiles": []}
    with pytest.raises(ValueError, match="precedence"):
        ActivationPolicy.from_file(write_policy(tmp_path, malformed))
    wrong_keys = policy_raw()
    wrong_keys["extra"] = True
    with pytest.raises(ValueError, match="fields"):
        ActivationPolicy.from_file(write_policy(tmp_path, wrong_keys))
    with pytest.raises(FileNotFoundError):
        ActivationPolicy.from_file(tmp_path / "missing.json")


def test_policy_rejects_non_object_arrays_invalid_schema_and_profile_order(tmp_path: Path) -> None:
    non_object = tmp_path / "non-object.json"
    non_object.write_text(json.dumps([]), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        ActivationPolicy.from_file(non_object)

    arrays = policy_raw()
    arrays["precedence"] = {}
    with pytest.raises(ValueError, match="arrays"):
        ActivationPolicy.from_file(write_policy(tmp_path, arrays))
    arrays = policy_raw()
    arrays["profiles"] = {}
    with pytest.raises(ValueError, match="arrays"):
        ActivationPolicy.from_file(write_policy(tmp_path, arrays))

    non_object_profile = policy_raw()
    non_object_profiles = non_object_profile["profiles"]
    assert isinstance(non_object_profiles, list)
    non_object_profiles[0] = "not-an-object"
    with pytest.raises(ValueError, match="Every activation policy profile"):
        ActivationPolicy.from_file(write_policy(tmp_path, non_object_profile))

    wrong_schema = policy_raw()
    wrong_schema["schema_version"] = "9.9"
    with pytest.raises(ValueError, match="Unsupported activation policy schema"):
        ActivationPolicy.from_file(write_policy(tmp_path, wrong_schema))

    wrong_profile_order = policy_raw()
    profile_list = wrong_profile_order["profiles"]
    assert isinstance(profile_list, list)
    profile_list[0], profile_list[1] = profile_list[1], profile_list[0]
    with pytest.raises(ValueError, match="profile order"):
        ActivationPolicy.from_file(write_policy(tmp_path, wrong_profile_order))

    policy = ActivationPolicy.from_file(POLICY_PATH)
    with pytest.raises(ValueError, match="Unknown activation profile"):
        policy.profile("NOT_A_PROFILE")
