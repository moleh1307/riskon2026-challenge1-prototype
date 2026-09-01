"""TOML configuration with explicit local-only path resolution."""

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riskon.orchestra.models import ActivationProfile


class PathsConfig(BaseModel):
    """Resolved repository paths."""

    model_config = ConfigDict(extra="forbid")

    data_root: Path
    generated_root: Path


class RetrievalConfig(BaseModel):
    """Deterministic TF-IDF settings."""

    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(ge=1)
    minimum_score: float = Field(ge=0.0, le=1.0)
    ngram_min: int = Field(ge=1)
    ngram_max: int = Field(ge=1)


class AuditConfig(BaseModel):
    """Local JSONL audit path."""

    model_config = ConfigDict(extra="forbid")

    path: Path


class SecurityConfig(BaseModel):
    """Network policy; M0 only permits false."""

    model_config = ConfigDict(extra="forbid")

    network_enabled: bool = False


class RuntimeConfig(BaseModel):
    """Runtime labels that prevent placeholder confidence overclaiming."""

    model_config = ConfigDict(extra="forbid")

    confidence_kind: str


class PipelineConfig(BaseModel):
    """Fully resolved M0 configuration."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    paths: PathsConfig
    retrieval: RetrievalConfig
    audit: AuditConfig
    security: SecurityConfig
    runtime: RuntimeConfig


class M1VerificationConfig(BaseModel):
    """Closed M1 evidence-gate switches."""

    model_config = ConfigDict(extra="forbid")

    require_explicit_support: bool
    require_scope_match: bool
    require_local_evidence: bool
    require_required_references: bool
    fail_on_unsupported_modality: bool
    include_critical_controls: bool
    exclude_unrequested_sections: bool


class M1EvaluationConfig(BaseModel):
    """M1 regression-suite cardinality contract."""

    model_config = ConfigDict(extra="forbid")

    expected_m0_cases: int = Field(ge=1)
    expected_m1_cases: int = Field(ge=1)
    expected_total_cases: int = Field(ge=1)


class Milestone1Config(BaseModel):
    """Resolved M1 configuration layered over immutable M0 config."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    base: PipelineConfig
    manifest: Path
    knowledge_root: Path
    evaluation_cases: Path
    generated_root: Path
    verification: M1VerificationConfig
    evaluation: M1EvaluationConfig
    security: SecurityConfig
    runtime: RuntimeConfig


class M2QueryPlanningConfig(BaseModel):
    """Closed M2 planner switches."""

    model_config = ConfigDict(extra="forbid")

    max_subqueries: int = Field(ge=1, le=3)
    require_explicit_context: bool
    split_markers: list[str]


class M2VectorizerConfig(BaseModel):
    """One fixed M2 TF-IDF channel configuration."""

    model_config = ConfigDict(extra="forbid")

    lowercase: bool
    stop_words: str | None = None
    analyzer: str | None = None
    ngram_min: int = Field(ge=1)
    ngram_max: int = Field(ge=1)


class M2ChannelWeights(BaseModel):
    """Weighted reciprocal-rank fusion channel weights."""

    model_config = ConfigDict(extra="forbid")

    exact: float = Field(gt=0.0)
    table_row: float = Field(gt=0.0)
    word_tfidf: float = Field(gt=0.0)
    char_tfidf: float = Field(gt=0.0)


class M2RetrievalConfig(BaseModel):
    """Structure-aware M2 retrieval settings."""

    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(ge=1)
    rrf_k: int = Field(ge=1)
    scope_filter_mode: str
    tie_breaker: str
    word_tfidf: M2VectorizerConfig
    char_tfidf: M2VectorizerConfig
    channel_weights: M2ChannelWeights


class M2EvaluationConfig(BaseModel):
    """Aggregate M2 evaluation cardinalities."""

    model_config = ConfigDict(extra="forbid")

    expected_m0_cases: int = Field(ge=1)
    expected_m1_new_cases: int = Field(ge=1)
    expected_m2_new_cases: int = Field(ge=1)
    expected_aggregate_cases: int = Field(ge=1)


class Milestone2Config(BaseModel):
    """Resolved M2 configuration layered over the M0/M1 contracts."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    base: Milestone1Config
    manifest: Path
    knowledge_root: Path
    alias_registry: Path
    evaluation_cases: Path
    generated_root: Path
    query_planning: M2QueryPlanningConfig
    retrieval: M2RetrievalConfig
    evaluation: M2EvaluationConfig
    security: SecurityConfig
    runtime: RuntimeConfig


class M3RoutingWeights(BaseModel):
    """Frozen M3 soft-scoring weights."""

    model_config = ConfigDict(extra="forbid")

    expertise_match: float = Field(gt=0.0)
    context_specificity: float = Field(gt=0.0)
    system_match: float = Field(gt=0.0)
    network_proximity: float = Field(gt=0.0)
    capacity_score: float = Field(gt=0.0)


class M3RoutingProfileConfig(BaseModel):
    """Paths for one versioned M3 support/directory profile."""

    model_config = ConfigDict(extra="forbid")

    support_model: Path
    expert_directory: Path


class M3RoutingConfig(BaseModel):
    """Closed M3 routing algorithm settings."""

    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(ge=1, le=3)
    person_min_score: float = Field(ge=0.0, le=1.0)
    person_min_margin: float = Field(ge=0.0, le=1.0)
    functional_queue_confidence: float = Field(ge=0.0, le=1.0)
    renormalize_applicable_weights: bool
    tie_breaker: str
    reference_time_utc: str
    confidence_kind: str
    weights: M3RoutingWeights
    profiles: dict[str, M3RoutingProfileConfig]


class M3EvaluationConfig(BaseModel):
    """M3 and aggregate evaluation cardinalities."""

    model_config = ConfigDict(extra="forbid")

    expected_m0_cases: int = Field(ge=1)
    expected_m1_new_cases: int = Field(ge=1)
    expected_m2_new_cases: int = Field(ge=1)
    expected_m3_new_cases: int = Field(ge=1)
    expected_aggregate_cases: int = Field(ge=1)


class Milestone3Config(BaseModel):
    """Resolved M3 configuration layered over the immutable M2 contract."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    base: Milestone2Config
    evaluation_cases: Path
    network_edges: Path
    generated_root: Path
    routing: M3RoutingConfig
    evaluation: M3EvaluationConfig
    security: SecurityConfig


class M4AOrchestraPaths(BaseModel):
    """Resolved paths for the frozen M4 inputs and ignored M4A outputs."""

    model_config = ConfigDict(extra="forbid")

    evaluation_cases: Path
    activation_policy: Path
    agent_catalog: Path
    source_safety_policy: Path
    counterfactual_policy: Path
    upstream_runs_root: Path
    generated_root: Path


class M4AProfileConfig(BaseModel):
    """Closed M4A runtime switches."""

    model_config = ConfigDict(extra="forbid")

    supported_profiles: list[ActivationProfile]
    worker_execution_enabled: bool


class M4AOrchestraConfig(BaseModel):
    """M4 input paths plus the explicit zero-worker profile boundary."""

    model_config = ConfigDict(extra="forbid")

    evaluation_cases: Path
    activation_policy: Path
    agent_catalog: Path
    source_safety_policy: Path
    counterfactual_policy: Path
    upstream_runs_root: Path
    generated_root: Path
    m4a: M4AProfileConfig


class M4AEvaluationConfig(BaseModel):
    """M4A case selection and acceptance cardinalities."""

    model_config = ConfigDict(extra="forbid")

    included_cases: list[str]
    expected_cases: int = Field(ge=1)
    expected_fast_path: int = Field(ge=0)
    expected_short_circuit_clarify: int = Field(ge=0)
    expected_human_first: int = Field(ge=0)
    expected_active_agents: int = Field(ge=0)


class Milestone4AConfig(BaseModel):
    """Resolved M4A configuration layered over the unchanged M3 contract."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    base: Milestone3Config
    orchestra: M4AOrchestraConfig
    evaluation: M4AEvaluationConfig
    security: SecurityConfig


class M4BProfileConfig(BaseModel):
    """Closed deterministic worker-orchestra settings."""

    model_config = ConfigDict(extra="forbid")

    worker_selection_policy: Path
    worker_backend: str
    implemented_roles: list[str]
    unsupported_roles: list[str]
    maximum_worker_depth: int = Field(ge=1)
    maximum_parallel_discovery_workers: int = Field(ge=1)
    maximum_challenge_rounds: int = Field(ge=1)
    generated_root: Path


class M4BOrchestraConfig(BaseModel):
    """Resolved M4 corpus paths plus the M4B worker boundary."""

    model_config = ConfigDict(extra="forbid")

    evaluation_cases: Path
    activation_policy: Path
    agent_catalog: Path
    source_safety_policy: Path
    counterfactual_policy: Path
    upstream_runs_root: Path
    generated_root: Path
    m4b: M4BProfileConfig


class M4BEvaluationConfig(BaseModel):
    """M4B case selection and aggregate acceptance cardinalities."""

    model_config = ConfigDict(extra="forbid")

    included_cases: list[str]
    expected_cases: int = Field(ge=1)
    expected_dual_check: int = Field(ge=0)
    expected_full_orchestra_non_counterfactual: int = Field(ge=0)
    expected_worker_tasks: int = Field(ge=0)
    expected_recovered_answers: int = Field(ge=0)
    expected_final_abstentions: int = Field(ge=0)
    expected_injection_safe_answers: int = Field(ge=0)


class M4BSecurityConfig(BaseModel):
    """M4B no-egress and no-delegation controls."""

    model_config = ConfigDict(extra="forbid")

    network_enabled: bool = False
    agent_to_agent_citation_enabled: bool = False
    recursive_delegation_enabled: bool = False


class Milestone4BConfig(BaseModel):
    """Resolved M4B configuration layered over the accepted M4A baseline."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    base: Milestone4AConfig
    orchestra: M4BOrchestraConfig
    evaluation: M4BEvaluationConfig
    security: M4BSecurityConfig


class M4CProfileConfig(BaseModel):
    """Closed M4C counterfactual execution settings and input paths."""

    model_config = ConfigDict(extra="forbid")

    evaluation_cases: Path
    execution_policy: Path
    context_value_registry: Path
    fixture_catalog: Path
    worker_selection_extension: Path
    fixture_root: Path
    fixture_backend: str
    runtime_backend: str
    maximum_parallel_variants: int = Field(ge=1)
    maximum_counterfactual_depth: int = Field(ge=1)
    implemented_dimensions: list[str]
    generated_root: Path


class M4COrchestraConfig(BaseModel):
    """Resolved M4C paths exposed through the nested profile boundary."""

    model_config = ConfigDict(extra="forbid")

    m4c: M4CProfileConfig

    @property
    def evaluation_cases(self) -> Path:
        """Return the M4C evaluation-case path."""

        return self.m4c.evaluation_cases

    @property
    def fixture_root(self) -> Path:
        """Return the M4C frozen-fixture directory."""

        return self.m4c.fixture_root

    @property
    def generated_root(self) -> Path:
        """Return the ignored M4C output directory."""

        return self.m4c.generated_root


class M4CEvaluationConfig(BaseModel):
    """M4C case selection and transition acceptance cardinalities."""

    model_config = ConfigDict(extra="forbid")

    included_cases: list[str]
    expected_cases: int = Field(ge=1)
    expected_counterfactual_variants: int = Field(ge=0)
    expected_safe_transition_passes: int = Field(ge=0)
    expected_scope_leaks: int = Field(ge=0)
    expected_final_answers: int = Field(ge=0)
    expected_final_abstentions: int = Field(ge=0)
    expected_brm_queue_routes: int = Field(ge=0)
    expected_worker_tasks: int = Field(ge=0)


class M4CSecurityConfig(BaseModel):
    """M4C fail-closed network, recursion, routing, and citation switches."""

    model_config = ConfigDict(extra="forbid")

    network_enabled: bool = False
    counterfactual_routing_enabled: bool = False
    recursive_orchestration_enabled: bool = False
    agent_to_agent_citation_enabled: bool = False


class Milestone4CConfig(BaseModel):
    """Resolved M4C configuration layered over the accepted M4B contract."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    base: Milestone4BConfig
    orchestra: M4COrchestraConfig
    evaluation: M4CEvaluationConfig
    security: M4CSecurityConfig


class M4DOrchestraConfig(BaseModel):
    """Resolved paths and bounded switches for the unified M4D runtime."""

    model_config = ConfigDict(extra="forbid")

    evaluation_cases: Path
    manifest: Path
    knowledge_root: Path
    runtime_policy: Path
    failure_policy: Path
    baseline_runs_root: Path
    counterfactual_runs_root: Path
    generated_root: Path
    auto_activation_enabled: bool
    counterfactual_backend: str
    retry_count: int = Field(ge=0)
    partial_answer_enabled: bool
    maximum_total_worker_tasks: int = Field(ge=1)
    maximum_worker_depth: int = Field(ge=1)
    maximum_parallel_discovery_workers: int = Field(ge=1)
    maximum_challenge_rounds: int = Field(ge=1)
    maximum_counterfactual_variants: int = Field(ge=1)
    maximum_counterfactual_depth: int = Field(ge=1)
    low_retrieval_margin_threshold: float = Field(ge=0.0, le=1.0)
    default_routing_profile: str = Field(min_length=1)


class M4DOrchestraContainer(BaseModel):
    """Nested TOML container preserving the M4D profile boundary."""

    model_config = ConfigDict(extra="forbid")

    m4d: M4DOrchestraConfig


class M4DEvaluationConfig(BaseModel):
    """M4D end-to-end case and regression cardinalities."""

    model_config = ConfigDict(extra="forbid")

    included_cases: list[str]
    expected_cases: int = Field(ge=1)
    expected_fast_path: int = Field(ge=0)
    expected_short_circuit_clarify: int = Field(ge=0)
    expected_human_first: int = Field(ge=0)
    expected_dual_check: int = Field(ge=0)
    expected_full_orchestra: int = Field(ge=0)
    expected_local_counterfactual_transitions: int = Field(ge=0)


class M4DSecurityConfig(BaseModel):
    """M4D no-egress, no-recursion, and no-external-service controls."""

    model_config = ConfigDict(extra="forbid")

    network_enabled: bool = False
    external_api_enabled: bool = False
    recursive_orchestration_enabled: bool = False
    counterfactual_routing_enabled: bool = False
    agent_to_agent_citation_enabled: bool = False


class Milestone4DConfig(BaseModel):
    """Resolved M4D configuration layered over the accepted M4C contract."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    base: Milestone4CConfig
    orchestra: M4DOrchestraContainer
    evaluation: M4DEvaluationConfig
    security: M4DSecurityConfig


class M5BOverlayConfig(BaseModel):
    """Closed retrieval policy for the active knowledge overlay."""

    model_config = ConfigDict(extra="forbid")

    provenance_prefix: str
    special_ranking_boost: bool
    include_expired_patches: bool
    include_rejected_patches: bool
    include_awaiting_approval_patches: bool


class M5BPolicyCIConfig(BaseModel):
    """Bounded Policy CI execution switches."""

    model_config = ConfigDict(extra="forbid")

    required_regression_passes: int = Field(ge=0)
    counterfactual_routing_enabled: bool
    recursive_policy_ci_enabled: bool


class M5BGovernanceConfig(BaseModel):
    """Resolved M5B contract paths and explicit governance switches."""

    model_config = ConfigDict(extra="forbid")

    contract_cases: Path
    execution_policy: Path
    claim_relations: Path
    regression_suites: Path
    overlay_evaluation_cases: Path
    release_activation_requests: Path
    generated_root: Path
    official_corpus_mutation_enabled: bool
    automatic_approval_enabled: bool
    automatic_activation_enabled: bool
    agent_approval_enabled: bool
    self_approval_enabled: bool
    overlay: M5BOverlayConfig
    policy_ci: M5BPolicyCIConfig


class M5BEvaluationConfig(BaseModel):
    """M5B case selection and acceptance cardinalities."""

    model_config = ConfigDict(extra="forbid")

    included_cases: list[str]
    expected_cases: int = Field(ge=1)
    expected_active_patches: int = Field(ge=0)
    expected_awaiting_approval: int = Field(ge=0)
    expected_rejected_patches: int = Field(ge=0)
    expected_expired_patches: int = Field(ge=0)
    expected_post_patch_transitions: int = Field(ge=0)


class M5BSecurityConfig(BaseModel):
    """M5B local-only and no-telemetry controls."""

    model_config = ConfigDict(extra="forbid")

    network_enabled: bool = False
    external_api_enabled: bool = False
    telemetry_enabled: bool = False


class Milestone5BConfig(BaseModel):
    """Resolved M5B configuration layered over the frozen M4D contract."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    base: Milestone4DConfig
    governance: M5BGovernanceConfig
    evaluation: M5BEvaluationConfig
    security: M5BSecurityConfig


class EventReadinessConfig(BaseModel):
    """Local-only ER-A adapter configuration."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    column_aliases: Path
    generated_root: Path
    pipeline_config: Path
    url_prefix: str
    network_enabled: bool = False
    external_fetch_enabled: bool = False
    source_mutation_enabled: bool = False
    source_instruction_execution_enabled: bool = False


class EventDemoRuntimeConfig(BaseModel):
    """Repository-local paths used by the ER-B demonstration surface."""

    model_config = ConfigDict(extra="forbid")

    pipeline_config: Path
    event_intake_config: Path
    demo_cases: Path
    dashboard_contract: Path
    presentation_copy: Path
    context_presets: Path
    expected_views_root: Path
    generated_root: Path


class EventDemoRenderingConfig(BaseModel):
    """Closed rendering and redaction switches for static demo output."""

    model_config = ConfigDict(extra="forbid")

    language: str
    self_contained_html: bool
    external_assets_enabled: bool
    maximum_evidence_excerpt_characters: int = Field(ge=1, le=280)
    include_private_reasoning: bool
    include_raw_source_html: bool
    include_absolute_paths: bool


class EventDemoSelectionConfig(BaseModel):
    """The five event-day stories frozen by the ER-B presentation contract."""

    model_config = ConfigDict(extra="forbid")

    included_cases: list[str]


class EventDemoDashboardConfig(BaseModel):
    """Dashboard evaluator inputs and honest-unmeasured policy."""

    model_config = ConfigDict(extra="forbid")

    evaluation_configs: list[Path]
    show_unmeasured_as_not_measured: bool


class EventDemoSecurityConfig(BaseModel):
    """No-egress and no-server controls for ER-B output."""

    model_config = ConfigDict(extra="forbid")

    network_enabled: bool = False
    external_api_enabled: bool = False
    telemetry_enabled: bool = False
    local_server_enabled: bool = False


class EventDemoConfig(BaseModel):
    """Resolved, self-contained ER-B configuration."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    runtime: EventDemoRuntimeConfig
    rendering: EventDemoRenderingConfig
    demo: EventDemoSelectionConfig
    dashboard: EventDemoDashboardConfig
    security: EventDemoSecurityConfig


class EventPitchRuntimeConfig(BaseModel):
    """Repository-local inputs used by the ER-C pitch package."""

    model_config = ConfigDict(extra="forbid")

    pipeline_config: Path
    demo_config: Path
    pitch_contract: Path
    slide_content: Path
    timing_profiles: Path
    live_demo_script: Path
    qa_bank: Path
    backup_demo_contract: Path
    presentation_copy: Path
    speaker_assignments: Path
    demo_bundle: Path
    dashboard_metrics: Path
    generated_root: Path


class EventPitchDeckConfig(BaseModel):
    """Closed PowerPoint format and leakage switches for ER-C."""

    model_config = ConfigDict(extra="forbid")

    aspect_ratio: str
    main_slide_count: int = Field(ge=1)
    appendix_slide_count: int = Field(ge=1)
    total_slide_count: int = Field(ge=1)
    external_assets_enabled: bool
    external_links_enabled: bool
    include_real_names: bool
    include_confidential_source_text: bool


class EventPitchTimingConfig(BaseModel):
    """Timing-profile selection for a duration-agnostic event pitch."""

    model_config = ConfigDict(extra="forbid")

    default_profile: str
    profiles: list[str]
    live_demo_seconds: int = Field(ge=1)


class EventPitchSecurityConfig(BaseModel):
    """No-egress and no-service controls for ER-C artifacts."""

    model_config = ConfigDict(extra="forbid")

    network_enabled: bool = False
    external_api_enabled: bool = False
    telemetry_enabled: bool = False
    server_enabled: bool = False


class EventPitchConfig(BaseModel):
    """Resolved, local-only ER-C pitch configuration."""

    model_config = ConfigDict(extra="forbid")

    project_root: Path
    runtime: EventPitchRuntimeConfig
    deck: EventPitchDeckConfig
    timing: EventPitchTimingConfig
    security: EventPitchSecurityConfig


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def load_config(config_path: Path) -> PipelineConfig:
    """Load and validate a TOML config relative to its repository root."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw = tomllib.load(handle)

    project_root = resolved_config.parent.parent
    paths_raw = raw["paths"]
    audit_raw = raw["audit"]
    config = PipelineConfig(
        project_root=project_root,
        paths=PathsConfig(
            data_root=_resolve(project_root, paths_raw["data_root"]),
            generated_root=_resolve(project_root, paths_raw["generated_root"]),
        ),
        retrieval=RetrievalConfig(**raw["retrieval"]),
        audit=AuditConfig(path=_resolve(project_root, audit_raw["path"])),
        security=SecurityConfig(**raw["security"]),
        runtime=RuntimeConfig(**raw["runtime"]),
    )
    if config.security.network_enabled:
        raise ValueError("M0 requires security.network_enabled = false")
    if config.retrieval.ngram_min > config.retrieval.ngram_max:
        raise ValueError("ngram_min cannot exceed ngram_max")
    return config


def load_milestone1_config(config_path: Path) -> Milestone1Config:
    """Load M1 extension settings without changing the M0 config file."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw = tomllib.load(handle)

    project_root = resolved_config.parent.parent
    base_config_path = _resolve(project_root, raw["base"]["config"])
    base_config = load_config(base_config_path)
    extension = raw["extension"]
    config = Milestone1Config(
        project_root=project_root,
        base=base_config,
        manifest=_resolve(project_root, extension["manifest"]),
        knowledge_root=_resolve(project_root, extension["knowledge_root"]),
        evaluation_cases=_resolve(project_root, extension["evaluation_cases"]),
        generated_root=_resolve(project_root, extension["generated_root"]),
        verification=M1VerificationConfig(**raw["verification"]),
        evaluation=M1EvaluationConfig(**raw["evaluation"]),
        security=SecurityConfig(**raw["security"]),
        runtime=RuntimeConfig(**raw["runtime"]),
    )
    if config.security.network_enabled:
        raise ValueError("M1 requires security.network_enabled = false")
    if config.runtime.confidence_kind != "DETERMINISTIC_GATE_PLACEHOLDER":
        raise ValueError("M1 confidence must remain a deterministic placeholder")
    return config


def load_milestone2_config(config_path: Path) -> Milestone2Config:
    """Load M2 extensions without changing the M0 or M1 configuration files."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw = tomllib.load(handle)

    project_root = resolved_config.parent.parent
    base_config_path = _resolve(project_root, raw["base"]["config"])
    base_config = load_milestone1_config(base_config_path)
    extension = raw["extension"]
    config = Milestone2Config(
        project_root=project_root,
        base=base_config,
        manifest=_resolve(project_root, extension["manifest"]),
        knowledge_root=_resolve(project_root, extension["knowledge_root"]),
        alias_registry=_resolve(project_root, extension["alias_registry"]),
        evaluation_cases=_resolve(project_root, extension["evaluation_cases"]),
        generated_root=_resolve(project_root, extension["generated_root"]),
        query_planning=M2QueryPlanningConfig(**raw["query_planning"]),
        retrieval=M2RetrievalConfig(
            top_k=raw["retrieval"]["top_k"],
            rrf_k=raw["retrieval"]["rrf_k"],
            scope_filter_mode=raw["retrieval"]["scope_filter_mode"],
            tie_breaker=raw["retrieval"]["tie_breaker"],
            word_tfidf=M2VectorizerConfig(**raw["retrieval"]["word_tfidf"]),
            char_tfidf=M2VectorizerConfig(**raw["retrieval"]["char_tfidf"]),
            channel_weights=M2ChannelWeights(**raw["retrieval"]["channel_weights"]),
        ),
        evaluation=M2EvaluationConfig(**raw["evaluation"]),
        security=SecurityConfig(**raw["security"]),
        runtime=RuntimeConfig(**raw["runtime"]),
    )
    if config.security.network_enabled:
        raise ValueError("M2 requires security.network_enabled = false")
    if config.runtime.confidence_kind != "DETERMINISTIC_GATE_PLACEHOLDER":
        raise ValueError("M2 confidence must remain a deterministic placeholder")
    if config.retrieval.scope_filter_mode != "EXCLUDE_EXPLICIT_CONFLICTS":
        raise ValueError("M2 requires explicit-conflict scope filtering")
    if config.retrieval.tie_breaker != "PROVENANCE_REF_ASCENDING":
        raise ValueError("M2 requires provenance-ref tie breaking")
    return config


def load_milestone3_config(config_path: Path) -> Milestone3Config:
    """Load M3 routing extensions without changing M0-M2 configuration."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw = tomllib.load(handle)

    project_root = resolved_config.parent.parent
    base_config_path = _resolve(project_root, raw["base"]["config"])
    base_config = load_milestone2_config(base_config_path)
    extension = raw["extension"]
    routing_raw = raw["routing"]
    profile_raw = routing_raw["profiles"]
    profiles = {
        name: M3RoutingProfileConfig(
            support_model=_resolve(project_root, values["support_model"]),
            expert_directory=_resolve(project_root, values["expert_directory"]),
        )
        for name, values in profile_raw.items()
    }
    config = Milestone3Config(
        project_root=project_root,
        base=base_config,
        evaluation_cases=_resolve(project_root, extension["evaluation_cases"]),
        network_edges=_resolve(project_root, extension["network_edges"]),
        generated_root=_resolve(project_root, extension["generated_root"]),
        routing=M3RoutingConfig(
            top_k=routing_raw["top_k"],
            person_min_score=routing_raw["person_min_score"],
            person_min_margin=routing_raw["person_min_margin"],
            functional_queue_confidence=routing_raw["functional_queue_confidence"],
            renormalize_applicable_weights=routing_raw["renormalize_applicable_weights"],
            tie_breaker=routing_raw["tie_breaker"],
            reference_time_utc=routing_raw["reference_time_utc"],
            confidence_kind=routing_raw["confidence_kind"],
            weights=M3RoutingWeights(**routing_raw["weights"]),
            profiles=profiles,
        ),
        evaluation=M3EvaluationConfig(**raw["evaluation"]),
        security=SecurityConfig(**raw["security"]),
    )
    if config.security.network_enabled:
        raise ValueError("M3 requires security.network_enabled = false")
    if config.base.security.network_enabled:
        raise ValueError("M3 base M2 security must remain disabled")
    required_profiles = {"default", "capacity_stress", "support_v2"}
    if set(config.routing.profiles) != required_profiles:
        raise ValueError("M3 requires default, capacity_stress, and support_v2 profiles")
    if config.routing.tie_breaker != "SCORE_DESC_MANDATE_SPECIFICITY_DESC_EXPERT_ID_ASC":
        raise ValueError("M3 requires deterministic score/mandate/id tie breaking")
    if config.routing.confidence_kind != "DETERMINISTIC_ROUTING_HEURISTIC_V1":
        raise ValueError("M3 confidence kind must remain the frozen heuristic label")
    return config


def _resolve_m4a_path(project_root: Path, value: object, field_name: str) -> Path:
    """Resolve a required M4A path while keeping configuration repository-local."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"M4A path {field_name} must be a non-empty relative string")
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"M4A path {field_name} must be relative")
    resolved = (project_root / path).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise ValueError(f"M4A path {field_name} must remain inside the repository")
    return resolved


def _resolve_m4b_path(project_root: Path, value: object, field_name: str) -> Path:
    """Resolve a required M4B path while keeping configuration repository-local."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"M4B path {field_name} must be a non-empty relative string")
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"M4B path {field_name} must be relative")
    resolved = (project_root / path).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise ValueError(f"M4B path {field_name} must remain inside the repository")
    return resolved


def _resolve_m4c_path(project_root: Path, value: object, field_name: str) -> Path:
    """Resolve a required M4C path while keeping configuration repository-local."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"M4C path {field_name} must be a non-empty relative string")
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"M4C path {field_name} must be relative")
    resolved = (project_root / path).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise ValueError(f"M4C path {field_name} must remain inside the repository")
    return resolved


def _require_table(raw: dict[str, Any], key: str) -> dict[str, Any]:
    """Read one TOML table with a useful validation error."""

    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"M4A configuration table {key!r} is required")
    return value


def _require_exact_keys(raw: dict[str, Any], expected: set[str], label: str) -> None:
    """Reject omitted or unrecognised M4A configuration keys."""

    if set(raw) != expected:
        raise ValueError(f"M4A configuration fields mismatch for {label}")


def load_milestone4a_config(config_path: Path) -> Milestone4AConfig:
    """Load the M4A zero-worker extension without changing M0-M3 configs."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw_value = tomllib.load(handle)
    if not isinstance(raw_value, dict):
        raise ValueError("M4A configuration must be a TOML table")
    _require_exact_keys(raw_value, {"base", "orchestra", "evaluation", "security"}, "root")

    project_root = resolved_config.parent.parent
    base_raw = _require_table(raw_value, "base")
    _require_exact_keys(base_raw, {"config"}, "base")
    base_config = load_milestone3_config(
        _resolve_m4a_path(project_root, base_raw.get("config"), "base.config")
    )

    orchestra_raw = _require_table(raw_value, "orchestra")
    orchestra_keys = {
        "evaluation_cases",
        "activation_policy",
        "agent_catalog",
        "source_safety_policy",
        "counterfactual_policy",
        "upstream_runs_root",
        "generated_root",
        "m4a",
    }
    _require_exact_keys(orchestra_raw, orchestra_keys, "orchestra")
    m4a_raw = _require_table(orchestra_raw, "m4a")
    _require_exact_keys(
        m4a_raw, {"supported_profiles", "worker_execution_enabled"}, "orchestra.m4a"
    )

    evaluation_raw = _require_table(raw_value, "evaluation")
    _require_exact_keys(
        evaluation_raw,
        {
            "included_cases",
            "expected_cases",
            "expected_fast_path",
            "expected_short_circuit_clarify",
            "expected_human_first",
            "expected_active_agents",
        },
        "evaluation",
    )
    security_raw = _require_table(raw_value, "security")
    _require_exact_keys(security_raw, {"network_enabled"}, "security")

    config = Milestone4AConfig(
        project_root=project_root,
        base=base_config,
        orchestra=M4AOrchestraConfig(
            evaluation_cases=_resolve_m4a_path(
                project_root, orchestra_raw.get("evaluation_cases"), "orchestra.evaluation_cases"
            ),
            activation_policy=_resolve_m4a_path(
                project_root, orchestra_raw.get("activation_policy"), "orchestra.activation_policy"
            ),
            agent_catalog=_resolve_m4a_path(
                project_root, orchestra_raw.get("agent_catalog"), "orchestra.agent_catalog"
            ),
            source_safety_policy=_resolve_m4a_path(
                project_root,
                orchestra_raw.get("source_safety_policy"),
                "orchestra.source_safety_policy",
            ),
            counterfactual_policy=_resolve_m4a_path(
                project_root,
                orchestra_raw.get("counterfactual_policy"),
                "orchestra.counterfactual_policy",
            ),
            upstream_runs_root=_resolve_m4a_path(
                project_root,
                orchestra_raw.get("upstream_runs_root"),
                "orchestra.upstream_runs_root",
            ),
            generated_root=_resolve_m4a_path(
                project_root, orchestra_raw.get("generated_root"), "orchestra.generated_root"
            ),
            m4a=M4AProfileConfig(**m4a_raw),
        ),
        evaluation=M4AEvaluationConfig(**evaluation_raw),
        security=SecurityConfig(**security_raw),
    )
    if config.security.network_enabled:
        raise ValueError("M4A requires security.network_enabled = false")
    if config.base.security.network_enabled:
        raise ValueError("M4A base M3 security must remain disabled")
    if config.orchestra.m4a.supported_profiles != [
        ActivationProfile.FAST_PATH,
        ActivationProfile.SHORT_CIRCUIT_CLARIFY,
        ActivationProfile.HUMAN_FIRST,
    ]:
        raise ValueError(
            "M4A supported_profiles must be FAST_PATH, SHORT_CIRCUIT_CLARIFY, HUMAN_FIRST"
        )
    if config.orchestra.m4a.worker_execution_enabled:
        raise ValueError("M4A worker_execution_enabled must remain false")
    if config.evaluation.included_cases != [
        "M4-029",
        "M4-033",
        "M4-034",
        "M4-039",
        "M4-040",
    ]:
        raise ValueError("M4A included_cases do not match the frozen zero-worker set")
    if (
        config.evaluation.expected_cases != 5
        or config.evaluation.expected_fast_path != 1
        or config.evaluation.expected_short_circuit_clarify != 1
        or config.evaluation.expected_human_first != 3
        or config.evaluation.expected_active_agents != 0
    ):
        raise ValueError("M4A evaluation cardinalities do not match the frozen acceptance contract")
    return config


def load_milestone4b_config(config_path: Path) -> Milestone4BConfig:
    """Load the M4B deterministic worker extension over M4A."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw_value = tomllib.load(handle)
    if not isinstance(raw_value, dict):
        raise ValueError("M4B configuration must be a TOML table")
    _require_exact_keys(raw_value, {"base", "orchestra", "evaluation", "security"}, "root")

    project_root = resolved_config.parent.parent
    base_raw = _require_table(raw_value, "base")
    _require_exact_keys(base_raw, {"config"}, "base")
    base_config = load_milestone4a_config(
        _resolve_m4b_path(project_root, base_raw.get("config"), "base.config")
    )

    orchestra_raw = _require_table(raw_value, "orchestra")
    _require_exact_keys(orchestra_raw, {"m4b"}, "orchestra")
    m4b_raw = _require_table(orchestra_raw, "m4b")
    _require_exact_keys(
        m4b_raw,
        {
            "worker_selection_policy",
            "worker_backend",
            "implemented_roles",
            "unsupported_roles",
            "maximum_worker_depth",
            "maximum_parallel_discovery_workers",
            "maximum_challenge_rounds",
            "generated_root",
        },
        "orchestra.m4b",
    )
    evaluation_raw = _require_table(raw_value, "evaluation")
    _require_exact_keys(
        evaluation_raw,
        {
            "included_cases",
            "expected_cases",
            "expected_dual_check",
            "expected_full_orchestra_non_counterfactual",
            "expected_worker_tasks",
            "expected_recovered_answers",
            "expected_final_abstentions",
            "expected_injection_safe_answers",
        },
        "evaluation",
    )
    security_raw = _require_table(raw_value, "security")
    _require_exact_keys(
        security_raw,
        {
            "network_enabled",
            "agent_to_agent_citation_enabled",
            "recursive_delegation_enabled",
        },
        "security",
    )

    worker_selection_policy = _resolve_m4b_path(
        project_root,
        m4b_raw.get("worker_selection_policy"),
        "orchestra.m4b.worker_selection_policy",
    )
    generated_root = _resolve_m4b_path(
        project_root,
        m4b_raw.get("generated_root"),
        "orchestra.m4b.generated_root",
    )
    config = Milestone4BConfig(
        project_root=project_root,
        base=base_config,
        orchestra=M4BOrchestraConfig(
            evaluation_cases=base_config.orchestra.evaluation_cases,
            activation_policy=base_config.orchestra.activation_policy,
            agent_catalog=base_config.orchestra.agent_catalog,
            source_safety_policy=base_config.orchestra.source_safety_policy,
            counterfactual_policy=base_config.orchestra.counterfactual_policy,
            upstream_runs_root=base_config.orchestra.upstream_runs_root,
            generated_root=generated_root,
            m4b=M4BProfileConfig(
                worker_selection_policy=worker_selection_policy,
                worker_backend=m4b_raw["worker_backend"],
                implemented_roles=m4b_raw["implemented_roles"],
                unsupported_roles=m4b_raw["unsupported_roles"],
                maximum_worker_depth=m4b_raw["maximum_worker_depth"],
                maximum_parallel_discovery_workers=m4b_raw["maximum_parallel_discovery_workers"],
                maximum_challenge_rounds=m4b_raw["maximum_challenge_rounds"],
                generated_root=generated_root,
            ),
        ),
        evaluation=M4BEvaluationConfig(**evaluation_raw),
        security=M4BSecurityConfig(**security_raw),
    )
    if config.security.network_enabled:
        raise ValueError("M4B requires network_enabled = false")
    if config.security.agent_to_agent_citation_enabled:
        raise ValueError("M4B requires agent_to_agent_citation_enabled = false")
    if config.security.recursive_delegation_enabled:
        raise ValueError("M4B requires recursive_delegation_enabled = false")
    if config.base.security.network_enabled:
        raise ValueError("M4B base M4A security must remain disabled")
    if config.orchestra.m4b.worker_backend != "DETERMINISTIC_WORKER_V1":
        raise ValueError("M4B worker backend must remain deterministic")
    if config.orchestra.m4b.implemented_roles != [
        "EVIDENCE_SCOUT",
        "SCOPE_SENTINEL",
        "PROCESS_TABLE_SCOUT",
        "SKEPTIC",
    ]:
        raise ValueError("M4B implemented_roles do not match the frozen worker set")
    if config.orchestra.m4b.unsupported_roles != ["COUNTERFACTUAL_SENTINEL"]:
        raise ValueError("M4B unsupported_roles must contain COUNTERFACTUAL_SENTINEL")
    if (
        config.orchestra.m4b.maximum_worker_depth != 1
        or config.orchestra.m4b.maximum_parallel_discovery_workers != 3
        or config.orchestra.m4b.maximum_challenge_rounds != 1
    ):
        raise ValueError("M4B worker bounds do not match the frozen contract")
    if config.evaluation.included_cases != [
        "M4-030",
        "M4-031",
        "M4-032",
        "M4-037",
        "M4-038",
    ]:
        raise ValueError("M4B included_cases do not match the frozen worker set")
    if (
        config.evaluation.expected_cases != 5
        or config.evaluation.expected_dual_check != 3
        or config.evaluation.expected_full_orchestra_non_counterfactual != 2
        or config.evaluation.expected_worker_tasks != 12
        or config.evaluation.expected_recovered_answers != 3
        or config.evaluation.expected_final_abstentions != 1
        or config.evaluation.expected_injection_safe_answers != 1
    ):
        raise ValueError("M4B evaluation cardinalities do not match the frozen contract")
    if not worker_selection_policy.is_file():
        raise FileNotFoundError(f"M4B worker selection policy not found: {worker_selection_policy}")
    return config


def load_milestone4c_config(config_path: Path) -> Milestone4CConfig:
    """Load the M4C extension without changing the frozen M4B contract."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw_value = tomllib.load(handle)
    if not isinstance(raw_value, dict):
        raise ValueError("M4C configuration must be a TOML table")
    _require_exact_keys(raw_value, {"base", "orchestra", "evaluation", "security"}, "root")

    project_root = resolved_config.parent.parent
    base_raw = _require_table(raw_value, "base")
    _require_exact_keys(base_raw, {"config"}, "base")
    base_config = load_milestone4b_config(
        _resolve_m4c_path(project_root, base_raw.get("config"), "base.config")
    )

    orchestra_raw = _require_table(raw_value, "orchestra")
    _require_exact_keys(orchestra_raw, {"m4c"}, "orchestra")
    m4c_raw = _require_table(orchestra_raw, "m4c")
    m4c_keys = {
        "evaluation_cases",
        "execution_policy",
        "context_value_registry",
        "fixture_catalog",
        "worker_selection_extension",
        "fixture_root",
        "fixture_backend",
        "runtime_backend",
        "maximum_parallel_variants",
        "maximum_counterfactual_depth",
        "implemented_dimensions",
        "generated_root",
    }
    _require_exact_keys(m4c_raw, m4c_keys, "orchestra.m4c")

    evaluation_raw = _require_table(raw_value, "evaluation")
    _require_exact_keys(
        evaluation_raw,
        {
            "included_cases",
            "expected_cases",
            "expected_counterfactual_variants",
            "expected_safe_transition_passes",
            "expected_scope_leaks",
            "expected_final_answers",
            "expected_final_abstentions",
            "expected_brm_queue_routes",
            "expected_worker_tasks",
        },
        "evaluation",
    )
    security_raw = _require_table(raw_value, "security")
    _require_exact_keys(
        security_raw,
        {
            "network_enabled",
            "counterfactual_routing_enabled",
            "recursive_orchestration_enabled",
            "agent_to_agent_citation_enabled",
        },
        "security",
    )

    m4c_profile = M4CProfileConfig(
        evaluation_cases=_resolve_m4c_path(
            project_root, m4c_raw.get("evaluation_cases"), "orchestra.m4c.evaluation_cases"
        ),
        execution_policy=_resolve_m4c_path(
            project_root, m4c_raw.get("execution_policy"), "orchestra.m4c.execution_policy"
        ),
        context_value_registry=_resolve_m4c_path(
            project_root,
            m4c_raw.get("context_value_registry"),
            "orchestra.m4c.context_value_registry",
        ),
        fixture_catalog=_resolve_m4c_path(
            project_root, m4c_raw.get("fixture_catalog"), "orchestra.m4c.fixture_catalog"
        ),
        worker_selection_extension=_resolve_m4c_path(
            project_root,
            m4c_raw.get("worker_selection_extension"),
            "orchestra.m4c.worker_selection_extension",
        ),
        fixture_root=_resolve_m4c_path(
            project_root, m4c_raw.get("fixture_root"), "orchestra.m4c.fixture_root"
        ),
        fixture_backend=m4c_raw["fixture_backend"],
        runtime_backend=m4c_raw["runtime_backend"],
        maximum_parallel_variants=m4c_raw["maximum_parallel_variants"],
        maximum_counterfactual_depth=m4c_raw["maximum_counterfactual_depth"],
        implemented_dimensions=m4c_raw["implemented_dimensions"],
        generated_root=_resolve_m4c_path(
            project_root, m4c_raw.get("generated_root"), "orchestra.m4c.generated_root"
        ),
    )
    config = Milestone4CConfig(
        project_root=project_root,
        base=base_config,
        orchestra=M4COrchestraConfig(m4c=m4c_profile),
        evaluation=M4CEvaluationConfig(**evaluation_raw),
        security=M4CSecurityConfig(**security_raw),
    )
    if config.security.network_enabled:
        raise ValueError("M4C requires network_enabled = false")
    if config.security.counterfactual_routing_enabled:
        raise ValueError("M4C requires counterfactual_routing_enabled = false")
    if config.security.recursive_orchestration_enabled:
        raise ValueError("M4C requires recursive_orchestration_enabled = false")
    if config.security.agent_to_agent_citation_enabled:
        raise ValueError("M4C requires agent_to_agent_citation_enabled = false")
    if config.base.security.network_enabled:
        raise ValueError("M4C base M4B security must remain disabled")
    if config.base.security.agent_to_agent_citation_enabled:
        raise ValueError("M4C base M4B agent-to-agent citations must remain disabled")
    if config.base.security.recursive_delegation_enabled:
        raise ValueError("M4C base M4B recursive delegation must remain disabled")
    profile = config.orchestra.m4c
    if profile.fixture_backend != "FROZEN_COUNTERFACTUAL_FIXTURE_V1":
        raise ValueError("M4C fixture backend must remain frozen")
    if profile.runtime_backend != "LOCAL_PLANNED_PIPELINE_V1":
        raise ValueError("M4C runtime backend must use the planned pipeline")
    if profile.maximum_parallel_variants != 3 or profile.maximum_counterfactual_depth != 1:
        raise ValueError("M4C worker bounds do not match the frozen contract")
    if profile.implemented_dimensions != ["region", "service_model"]:
        raise ValueError("M4C implemented dimensions do not match the frozen contract")
    if config.evaluation.included_cases != ["M4-035", "M4-036"]:
        raise ValueError("M4C included cases do not match the frozen counterfactual set")
    if (
        config.evaluation.expected_cases != 2
        or config.evaluation.expected_counterfactual_variants != 4
        or config.evaluation.expected_safe_transition_passes != 3
        or config.evaluation.expected_scope_leaks != 1
        or config.evaluation.expected_final_answers != 1
        or config.evaluation.expected_final_abstentions != 1
        or config.evaluation.expected_brm_queue_routes != 1
        or config.evaluation.expected_worker_tasks != 7
    ):
        raise ValueError("M4C evaluation cardinalities do not match the frozen contract")
    for path in (
        profile.evaluation_cases,
        profile.execution_policy,
        profile.context_value_registry,
        profile.fixture_catalog,
        profile.worker_selection_extension,
    ):
        if not path.is_file():
            raise FileNotFoundError(f"M4C contract input not found: {path}")
    if not profile.fixture_root.is_dir():
        raise FileNotFoundError(f"M4C fixture root not found: {profile.fixture_root}")
    return config


def _resolve_m4d_path(project_root: Path, value: object, field_name: str) -> Path:
    """Resolve one M4D path while preventing repository escape."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"M4D path {field_name} must be a non-empty relative string")
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"M4D path {field_name} must be relative")
    resolved = (project_root / path).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise ValueError(f"M4D path {field_name} must remain inside the repository")
    return resolved


def _require_exact_keys_m4d(raw: dict[str, Any], expected: set[str], label: str) -> None:
    """Reject omitted or unrecognised M4D configuration keys."""

    if set(raw) != expected:
        raise ValueError(f"M4D configuration fields mismatch for {label}")


def load_milestone4d_config(config_path: Path) -> Milestone4DConfig:
    """Load the unified M4D runtime extension over the frozen M4C contract."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw_value = tomllib.load(handle)
    if not isinstance(raw_value, dict):
        raise ValueError("M4D configuration must be a TOML table")
    _require_exact_keys_m4d(raw_value, {"base", "orchestra", "evaluation", "security"}, "root")

    project_root = resolved_config.parent.parent
    base_raw = _require_table(raw_value, "base")
    _require_exact_keys_m4d(base_raw, {"config"}, "base")
    base_config = load_milestone4c_config(
        _resolve_m4d_path(project_root, base_raw.get("config"), "base.config")
    )

    orchestra_raw = _require_table(raw_value, "orchestra")
    _require_exact_keys_m4d(orchestra_raw, {"m4d"}, "orchestra")
    m4d_raw = _require_table(orchestra_raw, "m4d")
    m4d_keys = {
        "evaluation_cases",
        "manifest",
        "knowledge_root",
        "runtime_policy",
        "failure_policy",
        "baseline_runs_root",
        "counterfactual_runs_root",
        "generated_root",
        "auto_activation_enabled",
        "counterfactual_backend",
        "retry_count",
        "partial_answer_enabled",
        "maximum_total_worker_tasks",
        "maximum_worker_depth",
        "maximum_parallel_discovery_workers",
        "maximum_challenge_rounds",
        "maximum_counterfactual_variants",
        "maximum_counterfactual_depth",
        "low_retrieval_margin_threshold",
        "default_routing_profile",
    }
    _require_exact_keys_m4d(m4d_raw, m4d_keys, "orchestra.m4d")

    evaluation_raw = _require_table(raw_value, "evaluation")
    _require_exact_keys_m4d(
        evaluation_raw,
        {
            "included_cases",
            "expected_cases",
            "expected_fast_path",
            "expected_short_circuit_clarify",
            "expected_human_first",
            "expected_dual_check",
            "expected_full_orchestra",
            "expected_local_counterfactual_transitions",
        },
        "evaluation",
    )
    security_raw = _require_table(raw_value, "security")
    _require_exact_keys_m4d(
        security_raw,
        {
            "network_enabled",
            "external_api_enabled",
            "recursive_orchestration_enabled",
            "counterfactual_routing_enabled",
            "agent_to_agent_citation_enabled",
        },
        "security",
    )

    path_fields = {
        key: _resolve_m4d_path(project_root, m4d_raw.get(key), f"orchestra.m4d.{key}")
        for key in (
            "evaluation_cases",
            "manifest",
            "knowledge_root",
            "runtime_policy",
            "failure_policy",
            "baseline_runs_root",
            "counterfactual_runs_root",
            "generated_root",
        )
    }
    config = Milestone4DConfig(
        project_root=project_root,
        base=base_config,
        orchestra=M4DOrchestraContainer(
            m4d=M4DOrchestraConfig(
                evaluation_cases=path_fields["evaluation_cases"],
                manifest=path_fields["manifest"],
                knowledge_root=path_fields["knowledge_root"],
                runtime_policy=path_fields["runtime_policy"],
                failure_policy=path_fields["failure_policy"],
                baseline_runs_root=path_fields["baseline_runs_root"],
                counterfactual_runs_root=path_fields["counterfactual_runs_root"],
                generated_root=path_fields["generated_root"],
                auto_activation_enabled=m4d_raw["auto_activation_enabled"],
                counterfactual_backend=m4d_raw["counterfactual_backend"],
                retry_count=m4d_raw["retry_count"],
                partial_answer_enabled=m4d_raw["partial_answer_enabled"],
                maximum_total_worker_tasks=m4d_raw["maximum_total_worker_tasks"],
                maximum_worker_depth=m4d_raw["maximum_worker_depth"],
                maximum_parallel_discovery_workers=m4d_raw["maximum_parallel_discovery_workers"],
                maximum_challenge_rounds=m4d_raw["maximum_challenge_rounds"],
                maximum_counterfactual_variants=m4d_raw["maximum_counterfactual_variants"],
                maximum_counterfactual_depth=m4d_raw["maximum_counterfactual_depth"],
                low_retrieval_margin_threshold=m4d_raw["low_retrieval_margin_threshold"],
                default_routing_profile=m4d_raw["default_routing_profile"],
            )
        ),
        evaluation=M4DEvaluationConfig(**evaluation_raw),
        security=M4DSecurityConfig(**security_raw),
    )
    if config.security.network_enabled or config.security.external_api_enabled:
        raise ValueError("M4D requires network and external_api to remain disabled")
    if config.security.recursive_orchestration_enabled:
        raise ValueError("M4D requires recursive_orchestration_enabled = false")
    if config.security.counterfactual_routing_enabled:
        raise ValueError("M4D requires counterfactual_routing_enabled = false")
    if config.security.agent_to_agent_citation_enabled:
        raise ValueError("M4D requires agent_to_agent_citation_enabled = false")
    if config.base.security.network_enabled:
        raise ValueError("M4D base M4C security must remain disabled")
    profile = config.orchestra.m4d
    if not profile.auto_activation_enabled:
        raise ValueError("M4D auto_activation_enabled must remain true")
    if profile.counterfactual_backend != "LOCAL_PLANNED_PIPELINE_V1":
        raise ValueError("M4D counterfactual backend must use the local planned pipeline")
    if profile.retry_count != 0 or profile.partial_answer_enabled:
        raise ValueError("M4D retries and partial answers must remain disabled")
    if (
        profile.maximum_total_worker_tasks != 7
        or profile.maximum_worker_depth != 1
        or profile.maximum_parallel_discovery_workers != 3
        or profile.maximum_challenge_rounds != 1
        or profile.maximum_counterfactual_variants != 3
        or profile.maximum_counterfactual_depth != 1
    ):
        raise ValueError("M4D execution bounds do not match the frozen contract")
    if profile.low_retrieval_margin_threshold != 0.015:
        raise ValueError("M4D retrieval margin threshold does not match the frozen contract")
    if config.evaluation.included_cases != [
        "M4D-041",
        "M4D-042",
        "M4D-043",
        "M4D-044",
        "M4D-045",
    ]:
        raise ValueError("M4D included cases do not match the frozen end-to-end set")
    if (
        config.evaluation.expected_cases != 5
        or config.evaluation.expected_fast_path != 1
        or config.evaluation.expected_short_circuit_clarify != 1
        or config.evaluation.expected_human_first != 1
        or config.evaluation.expected_dual_check != 1
        or config.evaluation.expected_full_orchestra != 1
        or config.evaluation.expected_local_counterfactual_transitions != 3
    ):
        raise ValueError("M4D evaluation cardinalities do not match the frozen contract")
    for path in (
        profile.evaluation_cases,
        profile.manifest,
        profile.runtime_policy,
        profile.failure_policy,
    ):
        if not path.is_file():
            raise FileNotFoundError(f"M4D contract input not found: {path}")
    for path in (
        profile.knowledge_root,
        profile.baseline_runs_root,
        profile.counterfactual_runs_root,
    ):
        if not path.is_dir():
            raise FileNotFoundError(f"M4D contract directory not found: {path}")
    return config


def _resolve_m5b_path(project_root: Path, value: object, field_name: str) -> Path:
    """Resolve one M5B path while keeping the contract repository-local."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"M5B path {field_name} must be a non-empty relative string")
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"M5B path {field_name} must be relative")
    resolved = (project_root / path).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise ValueError(f"M5B path {field_name} must remain inside the repository")
    return resolved


def _require_exact_keys_m5b(raw: dict[str, Any], expected: set[str], label: str) -> None:
    """Reject omitted or unrecognised M5B configuration keys."""

    if set(raw) != expected:
        raise ValueError(f"M5B configuration fields mismatch for {label}")


def load_milestone5b_config(config_path: Path) -> Milestone5BConfig:
    """Load and validate the final governed-overlay configuration."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw_value = tomllib.load(handle)
    if not isinstance(raw_value, dict):
        raise ValueError("M5B configuration must be a TOML table")
    _require_exact_keys_m5b(raw_value, {"base", "governance", "evaluation", "security"}, "root")

    project_root = resolved_config.parent.parent
    base_raw = _require_table(raw_value, "base")
    _require_exact_keys_m5b(base_raw, {"config"}, "base")
    base_config = load_milestone4d_config(
        _resolve_m5b_path(project_root, base_raw.get("config"), "base.config")
    )

    governance_raw = _require_table(raw_value, "governance")
    _require_exact_keys_m5b(
        governance_raw,
        {
            "contract_cases",
            "execution_policy",
            "claim_relations",
            "regression_suites",
            "overlay_evaluation_cases",
            "release_activation_requests",
            "generated_root",
            "official_corpus_mutation_enabled",
            "automatic_approval_enabled",
            "automatic_activation_enabled",
            "agent_approval_enabled",
            "self_approval_enabled",
            "overlay",
            "policy_ci",
        },
        "governance",
    )
    overlay_raw = governance_raw.get("overlay")
    if not isinstance(overlay_raw, dict):
        raise ValueError("M5B governance.overlay table is required")
    _require_exact_keys_m5b(
        overlay_raw,
        {
            "provenance_prefix",
            "special_ranking_boost",
            "include_expired_patches",
            "include_rejected_patches",
            "include_awaiting_approval_patches",
        },
        "governance.overlay",
    )
    policy_ci_raw = governance_raw.get("policy_ci")
    if not isinstance(policy_ci_raw, dict):
        raise ValueError("M5B governance.policy_ci table is required")
    _require_exact_keys_m5b(
        policy_ci_raw,
        {
            "required_regression_passes",
            "counterfactual_routing_enabled",
            "recursive_policy_ci_enabled",
        },
        "governance.policy_ci",
    )
    evaluation_raw = _require_table(raw_value, "evaluation")
    _require_exact_keys_m5b(
        evaluation_raw,
        {
            "included_cases",
            "expected_cases",
            "expected_active_patches",
            "expected_awaiting_approval",
            "expected_rejected_patches",
            "expected_expired_patches",
            "expected_post_patch_transitions",
        },
        "evaluation",
    )
    security_raw = _require_table(raw_value, "security")
    _require_exact_keys_m5b(
        security_raw,
        {"network_enabled", "external_api_enabled", "telemetry_enabled"},
        "security",
    )

    path_values = {
        key: _resolve_m5b_path(project_root, governance_raw.get(key), f"governance.{key}")
        for key in (
            "contract_cases",
            "execution_policy",
            "claim_relations",
            "regression_suites",
            "overlay_evaluation_cases",
            "release_activation_requests",
            "generated_root",
        )
    }
    config = Milestone5BConfig(
        project_root=project_root,
        base=base_config,
        governance=M5BGovernanceConfig(
            **path_values,
            official_corpus_mutation_enabled=bool(
                governance_raw["official_corpus_mutation_enabled"]
            ),
            automatic_approval_enabled=bool(governance_raw["automatic_approval_enabled"]),
            automatic_activation_enabled=bool(governance_raw["automatic_activation_enabled"]),
            agent_approval_enabled=bool(governance_raw["agent_approval_enabled"]),
            self_approval_enabled=bool(governance_raw["self_approval_enabled"]),
            overlay=M5BOverlayConfig(**overlay_raw),
            policy_ci=M5BPolicyCIConfig(**policy_ci_raw),
        ),
        evaluation=M5BEvaluationConfig(**evaluation_raw),
        security=M5BSecurityConfig(**security_raw),
    )
    if config.security.network_enabled or config.security.external_api_enabled:
        raise ValueError("M5B requires network and external_api to remain disabled")
    if config.security.telemetry_enabled:
        raise ValueError("M5B requires telemetry_enabled = false")
    if config.governance.official_corpus_mutation_enabled:
        raise ValueError("M5B official corpus mutation must remain disabled")
    if any(
        (
            config.governance.automatic_approval_enabled,
            config.governance.automatic_activation_enabled,
            config.governance.agent_approval_enabled,
            config.governance.self_approval_enabled,
        )
    ):
        raise ValueError("M5B automatic, agent, and self approval must remain disabled")
    if config.governance.overlay != M5BOverlayConfig(
        provenance_prefix="local://knowledge-overlay/",
        special_ranking_boost=False,
        include_expired_patches=False,
        include_rejected_patches=False,
        include_awaiting_approval_patches=False,
    ):
        raise ValueError("M5B overlay policy does not match the frozen contract")
    if config.governance.policy_ci.required_regression_passes != 45:
        raise ValueError("M5B regression gate must require 45 passes")
    if config.governance.policy_ci.counterfactual_routing_enabled:
        raise ValueError("M5B counterfactual routing must remain disabled")
    if config.governance.policy_ci.recursive_policy_ci_enabled:
        raise ValueError("M5B recursive Policy CI must remain disabled")
    if config.evaluation.included_cases != [
        "M5A-046",
        "M5A-047",
        "M5A-048",
        "M5A-049",
        "M5A-050",
    ]:
        raise ValueError("M5B included cases do not match the frozen M5A set")
    if (
        config.evaluation.expected_cases != 5
        or config.evaluation.expected_active_patches != 1
        or config.evaluation.expected_awaiting_approval != 1
        or config.evaluation.expected_rejected_patches != 2
        or config.evaluation.expected_expired_patches != 1
        or config.evaluation.expected_post_patch_transitions != 4
    ):
        raise ValueError("M5B evaluation cardinalities do not match the frozen contract")
    for path in path_values.values():
        if path != config.governance.generated_root and not path.is_file():
            raise FileNotFoundError(f"M5B contract input not found: {path}")
    return config


def load_event_readiness_config(config_path: Path) -> EventReadinessConfig:
    """Load and validate the additive, no-egress ER-A configuration."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw_value = tomllib.load(handle)
    if not isinstance(raw_value, dict) or set(raw_value) != {"event_readiness"}:
        raise ValueError("Event readiness configuration must contain one event_readiness table")
    raw = raw_value["event_readiness"]
    if not isinstance(raw, dict):
        raise ValueError("Event readiness configuration must be a TOML table")
    expected = {
        "column_aliases",
        "generated_root",
        "pipeline_config",
        "url_prefix",
        "network_enabled",
        "external_fetch_enabled",
        "source_mutation_enabled",
        "source_instruction_execution_enabled",
    }
    if set(raw) != expected:
        raise ValueError("Event readiness configuration fields do not match the frozen contract")
    project_root = resolved_config.parent.parent.resolve()
    path_values: dict[str, Path] = {}
    for field_name in ("column_aliases", "generated_root", "pipeline_config"):
        value = raw.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Event readiness path {field_name} must be a non-empty string")
        path = Path(value)
        if path.is_absolute():
            raise ValueError(f"Event readiness path {field_name} must be relative")
        resolved = (project_root / path).resolve()
        if not resolved.is_relative_to(project_root):
            raise ValueError(f"Event readiness path {field_name} must remain in the repository")
        path_values[field_name] = resolved
    config = EventReadinessConfig(
        project_root=project_root,
        column_aliases=path_values["column_aliases"],
        generated_root=path_values["generated_root"],
        pipeline_config=path_values["pipeline_config"],
        url_prefix=str(raw["url_prefix"]),
        network_enabled=bool(raw["network_enabled"]),
        external_fetch_enabled=bool(raw["external_fetch_enabled"]),
        source_mutation_enabled=bool(raw["source_mutation_enabled"]),
        source_instruction_execution_enabled=bool(raw["source_instruction_execution_enabled"]),
    )
    if not config.url_prefix.startswith("local://"):
        raise ValueError("Event readiness URL prefix must remain local")
    if any(
        (
            config.network_enabled,
            config.external_fetch_enabled,
            config.source_mutation_enabled,
            config.source_instruction_execution_enabled,
        )
    ):
        raise ValueError(
            "ER-A requires network, fetch, mutation, and instruction execution disabled"
        )
    for path in (config.column_aliases, config.pipeline_config):
        if not path.is_file():
            raise FileNotFoundError(f"Event readiness contract input not found: {path}")
    return config


def _resolve_event_demo_path(project_root: Path, value: object, field_name: str) -> Path:
    """Resolve an ER-B path while preventing repository escape."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"Event demo path {field_name} must be a non-empty relative string")
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"Event demo path {field_name} must be relative")
    resolved = (project_root / path).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise ValueError(f"Event demo path {field_name} must remain in the repository")
    return resolved


def _require_exact_keys_event_demo(raw: dict[str, Any], expected: set[str], label: str) -> None:
    """Reject omitted or unrecognised ER-B configuration keys."""

    if set(raw) != expected:
        raise ValueError(f"Event demo configuration fields mismatch for {label}")


def load_event_demo_config(config_path: Path) -> EventDemoConfig:
    """Load and validate the local-only ER-B demo configuration."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw_value = tomllib.load(handle)
    if not isinstance(raw_value, dict):
        raise ValueError("Event demo configuration must be a TOML table")
    _require_exact_keys_event_demo(
        raw_value,
        {"runtime", "rendering", "demo", "dashboard", "security"},
        "root",
    )
    project_root = resolved_config.parent.parent.resolve()

    runtime_raw = raw_value.get("runtime")
    if not isinstance(runtime_raw, dict):
        raise ValueError("Event demo runtime table is required")
    _require_exact_keys_event_demo(
        runtime_raw,
        {
            "pipeline_config",
            "event_intake_config",
            "demo_cases",
            "dashboard_contract",
            "presentation_copy",
            "context_presets",
            "expected_views_root",
            "generated_root",
        },
        "runtime",
    )
    runtime_paths = {
        key: _resolve_event_demo_path(project_root, runtime_raw.get(key), f"runtime.{key}")
        for key in (
            "pipeline_config",
            "event_intake_config",
            "demo_cases",
            "dashboard_contract",
            "presentation_copy",
            "context_presets",
            "expected_views_root",
            "generated_root",
        )
    }

    rendering_raw = raw_value.get("rendering")
    if not isinstance(rendering_raw, dict):
        raise ValueError("Event demo rendering table is required")
    _require_exact_keys_event_demo(
        rendering_raw,
        {
            "language",
            "self_contained_html",
            "external_assets_enabled",
            "maximum_evidence_excerpt_characters",
            "include_private_reasoning",
            "include_raw_source_html",
            "include_absolute_paths",
        },
        "rendering",
    )

    demo_raw = raw_value.get("demo")
    if not isinstance(demo_raw, dict):
        raise ValueError("Event demo selection table is required")
    _require_exact_keys_event_demo(demo_raw, {"included_cases"}, "demo")

    dashboard_raw = raw_value.get("dashboard")
    if not isinstance(dashboard_raw, dict):
        raise ValueError("Event demo dashboard table is required")
    _require_exact_keys_event_demo(
        dashboard_raw,
        {"evaluation_configs", "show_unmeasured_as_not_measured"},
        "dashboard",
    )
    evaluation_configs_raw = dashboard_raw.get("evaluation_configs")
    if not isinstance(evaluation_configs_raw, list):
        raise ValueError("Event demo dashboard evaluation_configs must be a list")
    evaluation_configs = [
        _resolve_event_demo_path(project_root, value, "dashboard.evaluation_configs")
        for value in evaluation_configs_raw
    ]

    security_raw = raw_value.get("security")
    if not isinstance(security_raw, dict):
        raise ValueError("Event demo security table is required")
    _require_exact_keys_event_demo(
        security_raw,
        {"network_enabled", "external_api_enabled", "telemetry_enabled", "local_server_enabled"},
        "security",
    )

    config = EventDemoConfig(
        project_root=project_root,
        runtime=EventDemoRuntimeConfig(**runtime_paths),
        rendering=EventDemoRenderingConfig(**rendering_raw),
        demo=EventDemoSelectionConfig(**demo_raw),
        dashboard=EventDemoDashboardConfig(
            evaluation_configs=evaluation_configs,
            show_unmeasured_as_not_measured=bool(dashboard_raw["show_unmeasured_as_not_measured"]),
        ),
        security=EventDemoSecurityConfig(**security_raw),
    )
    if config.rendering.language != "en":
        raise ValueError("Event demo language must remain en")
    if (
        not config.rendering.self_contained_html
        or config.rendering.external_assets_enabled
        or config.rendering.include_private_reasoning
        or config.rendering.include_raw_source_html
        or config.rendering.include_absolute_paths
    ):
        raise ValueError("Event demo rendering must remain self-contained and redacted")
    if config.demo.included_cases != [
        "ERB-001",
        "ERB-002",
        "ERB-003",
        "ERB-004",
        "ERB-005",
    ]:
        raise ValueError("Event demo cases do not match the frozen ER-B story set")
    expected_evaluation_configs = [
        "config/milestone0.toml",
        "config/milestone1.toml",
        "config/milestone2.toml",
        "config/milestone3.toml",
        "config/milestone4a.toml",
        "config/milestone4b.toml",
        "config/milestone4c.toml",
        "config/milestone4d.toml",
        "config/milestone5b.toml",
    ]
    if [
        str(path.relative_to(project_root)) for path in evaluation_configs
    ] != expected_evaluation_configs:
        raise ValueError("Event demo dashboard configs do not match the frozen evaluator set")
    if any(
        (
            config.security.network_enabled,
            config.security.external_api_enabled,
            config.security.telemetry_enabled,
            config.security.local_server_enabled,
        )
    ):
        raise ValueError("Event demo requires network, API, telemetry, and server disabled")
    for path in (
        config.runtime.pipeline_config,
        config.runtime.event_intake_config,
        config.runtime.demo_cases,
        config.runtime.dashboard_contract,
        config.runtime.presentation_copy,
        config.runtime.context_presets,
        *config.dashboard.evaluation_configs,
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Event demo contract input not found: {path}")
    if not config.runtime.expected_views_root.is_dir():
        raise FileNotFoundError(
            f"Event demo expected views directory not found: {config.runtime.expected_views_root}"
        )
    return config


def _require_exact_keys_event_pitch(raw: dict[str, Any], expected: set[str], label: str) -> None:
    """Reject omitted or unrecognised ER-C configuration keys."""

    if set(raw) != expected:
        raise ValueError(f"Event pitch configuration fields mismatch for {label}")


def load_event_pitch_config(config_path: Path) -> EventPitchConfig:
    """Load and validate the local-only ER-C pitch configuration."""

    resolved_config = config_path.resolve()
    if not resolved_config.is_file():
        raise FileNotFoundError(f"Configuration file not found: {resolved_config}")
    with resolved_config.open("rb") as handle:
        raw_value = tomllib.load(handle)
    if not isinstance(raw_value, dict):
        raise ValueError("Event pitch configuration must be a TOML table")
    _require_exact_keys_event_pitch(raw_value, {"runtime", "deck", "timing", "security"}, "root")
    project_root = resolved_config.parent.parent.resolve()

    runtime_raw = raw_value.get("runtime")
    if not isinstance(runtime_raw, dict):
        raise ValueError("Event pitch runtime table is required")
    runtime_keys = {
        "pipeline_config",
        "demo_config",
        "pitch_contract",
        "slide_content",
        "timing_profiles",
        "live_demo_script",
        "qa_bank",
        "backup_demo_contract",
        "presentation_copy",
        "speaker_assignments",
        "demo_bundle",
        "dashboard_metrics",
        "generated_root",
    }
    _require_exact_keys_event_pitch(runtime_raw, runtime_keys, "runtime")
    runtime_paths = {
        key: _resolve_event_demo_path(project_root, runtime_raw.get(key), f"runtime.{key}")
        for key in runtime_keys
    }

    deck_raw = raw_value.get("deck")
    timing_raw = raw_value.get("timing")
    security_raw = raw_value.get("security")
    if not isinstance(deck_raw, dict):
        raise ValueError("Event pitch deck table is required")
    if not isinstance(timing_raw, dict):
        raise ValueError("Event pitch timing table is required")
    if not isinstance(security_raw, dict):
        raise ValueError("Event pitch security table is required")
    _require_exact_keys_event_pitch(
        deck_raw,
        {
            "aspect_ratio",
            "main_slide_count",
            "appendix_slide_count",
            "total_slide_count",
            "external_assets_enabled",
            "external_links_enabled",
            "include_real_names",
            "include_confidential_source_text",
        },
        "deck",
    )
    _require_exact_keys_event_pitch(
        timing_raw,
        {"default_profile", "profiles", "live_demo_seconds"},
        "timing",
    )
    _require_exact_keys_event_pitch(
        security_raw,
        {"network_enabled", "external_api_enabled", "telemetry_enabled", "server_enabled"},
        "security",
    )

    config = EventPitchConfig(
        project_root=project_root,
        runtime=EventPitchRuntimeConfig(**runtime_paths),
        deck=EventPitchDeckConfig(**deck_raw),
        timing=EventPitchTimingConfig(**timing_raw),
        security=EventPitchSecurityConfig(**security_raw),
    )
    if config.deck.aspect_ratio != "16:9":
        raise ValueError("Event pitch deck must remain 16:9")
    if (
        config.deck.main_slide_count != 8
        or config.deck.appendix_slide_count != 4
        or config.deck.total_slide_count != 12
    ):
        raise ValueError("Event pitch deck cardinalities must remain 8 main, 4 appendix, 12 total")
    if config.timing.default_profile != "5_MIN" or config.timing.profiles != [
        "3_MIN",
        "5_MIN",
        "7_MIN",
    ]:
        raise ValueError("Event pitch timing profiles must remain 3_MIN, 5_MIN and 7_MIN")
    if config.timing.live_demo_seconds != 90:
        raise ValueError("Event pitch live demo must remain 90 seconds")
    if any(
        (
            config.deck.external_assets_enabled,
            config.deck.external_links_enabled,
            config.deck.include_real_names,
            config.deck.include_confidential_source_text,
            config.security.network_enabled,
            config.security.external_api_enabled,
            config.security.telemetry_enabled,
            config.security.server_enabled,
        )
    ):
        raise ValueError("Event pitch requires local-only, no-egress and redacted output")
    for path in (
        config.runtime.pipeline_config,
        config.runtime.demo_config,
        config.runtime.pitch_contract,
        config.runtime.slide_content,
        config.runtime.timing_profiles,
        config.runtime.live_demo_script,
        config.runtime.qa_bank,
        config.runtime.backup_demo_contract,
        config.runtime.presentation_copy,
        config.runtime.speaker_assignments,
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Event pitch contract input not found: {path}")
    return config
