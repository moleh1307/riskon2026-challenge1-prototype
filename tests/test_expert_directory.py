"""M3 synthetic expert-directory and network-edge tests."""

from riskon.expert_directory import ExpertDirectory, NetworkDirectory


def test_default_directory_has_synthetic_profiles(m3_config) -> None:
    path = m3_config.routing.profiles["default"].expert_directory
    directory = ExpertDirectory.from_file(path)
    assert directory.expert_directory_version == "m3-v1"
    assert len(directory.profiles) == 9
    assert all(profile.expert_id.startswith("SYN3-") for profile in directory.profiles)


def test_selected_expert_queue_is_directory_data(m3_config) -> None:
    path = m3_config.routing.profiles["default"].expert_directory
    directory = ExpertDirectory.from_file(path)
    assert directory.queue_for_expert_id("SYN3-BRM-BETA-001") == "QUEUE-BRM-BETA"


def test_network_edges_are_loaded_without_external_access(m3_config) -> None:
    network = NetworkDirectory.from_file(m3_config.network_edges)
    assert network.weight("TEAM-LEGAL-ALPHA", "NODE-LEGAL-GLOBAL-PRIMARY") == 1.0
    assert network.weight("TEAM-LEGAL-ALPHA", "NODE-UNKNOWN") == 0.0
