"""Shared fixtures for the M0 acceptance suite."""

from pathlib import Path

import pytest
import pytest_socket

from riskon.config import (
    AuditConfig,
    EventPitchConfig,
    Milestone1Config,
    Milestone2Config,
    Milestone3Config,
    PathsConfig,
    PipelineConfig,
    load_config,
    load_event_demo_config,
    load_event_pitch_config,
    load_milestone1_config,
    load_milestone2_config,
    load_milestone3_config,
)
from riskon.demo.catalog import DemoCatalog
from riskon.demo.dashboard import DashboardBuilder
from riskon.demo.models import DashboardView
from riskon.demo.runner import DemoRun, DemoRunner
from riskon.pipeline import RiskonPipeline
from riskon.pitch.catalog import PitchCatalog
from riskon.pitch.reporting import PitchBuildResult, build_pitch

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def allow_session_asyncio_unix_socket() -> None:
    """Allow asyncio's local socketpair while session fixtures are built."""

    pytest_socket.enable_socket()
    pytest_socket.disable_socket(allow_unix_socket=True)


@pytest.fixture(scope="module", autouse=True)
def allow_module_asyncio_unix_socket() -> None:
    """Allow asyncio's local socketpair for module-scoped evaluation fixtures."""

    pytest_socket.enable_socket()
    pytest_socket.disable_socket(allow_unix_socket=True)


@pytest.fixture(autouse=True)
def allow_m4b_asyncio_unix_socket(request: pytest.FixtureRequest) -> None:
    """Allow asyncio's local socketpair while retaining network blocking."""

    del request
    pytest_socket.enable_socket()
    pytest_socket.disable_socket(allow_unix_socket=True)


@pytest.fixture
def config(tmp_path: Path) -> PipelineConfig:
    base = load_config(PROJECT_ROOT / "config" / "milestone0.toml")
    return base.model_copy(
        update={
            "paths": PathsConfig(
                data_root=base.paths.data_root,
                generated_root=tmp_path / "generated",
            ),
            "audit": AuditConfig(path=tmp_path / "audit.jsonl"),
        }
    )


@pytest.fixture
def pipeline(config: PipelineConfig) -> RiskonPipeline:
    return RiskonPipeline.from_config(config)


@pytest.fixture
def m1_config(tmp_path: Path) -> Milestone1Config:
    base = load_milestone1_config(PROJECT_ROOT / "config" / "milestone1.toml")
    return base.model_copy(update={"generated_root": tmp_path / "m1-generated"})


@pytest.fixture
def m1_pipeline(m1_config: Milestone1Config) -> RiskonPipeline:
    return RiskonPipeline.from_milestone1_config(m1_config)


@pytest.fixture
def m2_config(tmp_path: Path) -> Milestone2Config:
    base = load_milestone2_config(PROJECT_ROOT / "config" / "milestone2.toml")
    return base.model_copy(update={"generated_root": tmp_path / "m2-generated"})


@pytest.fixture
def m2_pipeline(m2_config: Milestone2Config) -> RiskonPipeline:
    return RiskonPipeline.from_milestone2_config(m2_config)


@pytest.fixture
def m3_config(tmp_path: Path) -> Milestone3Config:
    base = load_milestone3_config(PROJECT_ROOT / "config" / "milestone3.toml")
    return base.model_copy(update={"generated_root": tmp_path / "m3-generated"})


@pytest.fixture
def m3_pipeline(m3_config: Milestone3Config) -> RiskonPipeline:
    return RiskonPipeline.from_milestone3_config(m3_config)


@pytest.fixture(scope="session")
def event_demo_config() -> object:
    """Load the frozen ER-B configuration once for demo contract tests."""

    return load_event_demo_config(PROJECT_ROOT / "config" / "event_demo.toml")


@pytest.fixture(scope="session")
def event_demo_catalog(event_demo_config: object) -> DemoCatalog:
    """Load the ER-B catalog once for view and renderer tests."""

    return DemoCatalog.from_config(event_demo_config)  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def event_demo_run(
    event_demo_config: object,
    event_demo_catalog: DemoCatalog,
    allow_session_asyncio_unix_socket: None,
) -> DemoRun:
    """Run the five stories and frozen M5B evaluator once per test session."""

    pytest_socket.enable_socket()
    pytest_socket.disable_socket(allow_unix_socket=True)
    return DemoRunner(event_demo_config, event_demo_catalog).run_all()  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def event_demo_dashboard(event_demo_catalog: DemoCatalog, event_demo_run: DemoRun) -> DashboardView:
    """Build the dashboard from the session's actual runtime outputs."""

    return DashboardBuilder(event_demo_catalog).build(
        m4d_runs=event_demo_run.m4d_runs,
        m5b_document=event_demo_run.m5b_document,
    )


@pytest.fixture(scope="session")
def event_pitch_config() -> EventPitchConfig:
    """Load the frozen ER-C configuration once per test session."""

    return load_event_pitch_config(PROJECT_ROOT / "config" / "event_pitch.toml")


@pytest.fixture(scope="session")
def event_pitch_catalog(event_pitch_config: EventPitchConfig) -> PitchCatalog:
    """Load the complete ER-C source catalog once per test session."""

    return PitchCatalog.from_config(event_pitch_config)


@pytest.fixture(scope="session")
def event_pitch_build(
    event_pitch_config: EventPitchConfig,
    allow_session_asyncio_unix_socket: None,
) -> PitchBuildResult:
    """Build ER-B and ER-C outputs once so runtime tests inspect real artifacts."""

    from riskon.demo.reporting import build_demo

    pytest_socket.enable_socket()
    pytest_socket.disable_socket(allow_unix_socket=True)
    build_demo(PROJECT_ROOT / "config" / "event_demo.toml")
    return build_pitch(PROJECT_ROOT / "config" / "event_pitch.toml")
