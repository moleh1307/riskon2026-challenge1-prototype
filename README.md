# RiskON Challenge 1 — M0/M1/M2/M3/M4D/M5B + ER-A/ER-B/ER-C prototype

This repository is a local-first, deterministic prototype for RiskON 2026
Challenge 1. It uses synthetic knowledge only and deliberately exposes a CLI
rather than an HTTP service.

The implemented flow is:

```text
Question → Plan → Hybrid Retrieval → Evidence Check
         → Answer / Clarify / Abstain → Configurable Expert Routing
         → Governed Knowledge Overlay → Audit Log → Pitch Package
```

## Run the evaluation

```bash
uv sync --frozen
uv run riskon evaluate --config config/milestone0.toml
```

The command writes `data/generated/evaluation.json` and appends one JSON object
per scenario to `data/generated/audit.jsonl`. A successful run ends with:

```text
M0 PASS: 5/5 scenarios matched; network disabled; audit schema valid.
```

## Run M1

```bash
uv run riskon evaluate --config config/milestone1.toml
```

M1 runs the five M0 regression cases and seven synthetic evidence-contract
cases. It writes `data/generated/m1/evaluation.json`,
`data/generated/m1/evaluation.md`, and `data/generated/m1/audit.jsonl`, then
ends with:

```text
M1 PASS: 12/12 scenarios matched; M0 regression 5/5; claim support valid; network disabled.
```

## Run M2

```bash
uv run riskon evaluate --config config/milestone2.toml
```

M2 adds a deterministic query planner, declared alias normalization, optional
query decomposition, exact/word/character/table-row retrieval, explicit scope
filtering, weighted reciprocal-rank fusion, and retrieval diagnostics. It
keeps the public M0/M1 interfaces unchanged and writes its artifacts under
`data/generated/m2/`.

The canonical success line is:

```text
M2 PASS: aggregate 20/20; M0 5/5; M1-new 7/7; M2-new 8/8; query plans 8/8; evidence recall@5 1.000; context violations 0; network disabled.
```

## Run M3

```bash
uv run riskon evaluate --config config/milestone3.toml
```

M3 adds configurable synthetic expert routing, structured routing
explanations, support-function hot-swapping, and fixture-backed evaluation
over the unchanged M2 pipeline. The router receives no raw query or retrieved
text. Routing occurs only for an actual `ABSTAIN`; `ANSWER` and `CLARIFY` are
explicitly not routed. See [`docs/milestone3.md`](docs/milestone3.md).

The canonical success line is:

```text
M3 PASS: aggregate 28/28; M0 5/5; M1-new 7/7; M2-new 8/8; M3-new 8/8; support functions 8/8; person-or-queue 8/8; hot-swap 1/1; hard-constraint violations 0; network disabled.
```

## Run M4A

```bash
uv run riskon evaluate --config config/milestone4a.toml
```

M4A adds a zero-worker orchestration shell over frozen M2 planned/verified
runs and the existing M3 route boundary. It implements `FAST_PATH`,
`SHORT_CIRCUIT_CLARIFY`, and `HUMAN_FIRST`; it preserves the baseline and
keeps all worker metrics at zero. `DUAL_CHECK` and `FULL_ORCHESTRA` are
explicitly deferred to M4B and fail closed in M4A. See
[`docs/milestone4a.md`](docs/milestone4a.md).

The canonical success line is:

```text
M4A PASS: zero-worker paths 5/5; FAST_PATH 1/1; SHORT_CIRCUIT_CLARIFY 1/1; HUMAN_FIRST 3/3; M0-M3 regression 28/28; active agents 0; baseline mutations 0; network disabled.
```

## Run M4B

```bash
uv run riskon evaluate --config config/milestone4b.toml
```

M4B adds the first real fan-out/fan-in boundary, but only with bounded
deterministic workers over the frozen local M4 corpus. Worker roles are chosen
from declared risk signals, discovery is capped at three concurrent tasks, and
one Skeptic challenge wave follows deterministic fan-in. Existing M1
verification and the material-objection gate retain final decision authority.
M4B uses deterministic bounded workers. It does not yet use an LLM or claim to
be a model-driven swarm. Counterfactual handling remains reserved for M4C.
Artifacts are written under `data/generated/m4b/`.

The canonical success line is:

```text
M4B PASS: worker paths 5/5; DUAL_CHECK 3/3; FULL_ORCHESTRA non-counterfactual 2/2; recovered answers 3/3; safety outcomes 2/2; worker tasks 12/12; M4A regression 5/5; M0-M3 regression 28/28; baseline mutations 0; agent-to-agent citations 0; network disabled.
```

## Run M4C

```bash
uv run riskon evaluate --config config/milestone4c.toml
```

M4C adds bounded local counterfactual execution for explicit scope changes.
The Counterfactual Sentinel verifies safe transitions and can block an unsafe
answer with a material scope objection. Its frozen evaluation covers two
counterfactual cases and writes artifacts under `data/generated/m4c/`.

## Run M4D

```bash
uv run riskon evaluate --config config/milestone4d.toml
uv run riskon run --config config/milestone4d.toml \
  "What is the Synthetic Stability Marker?"
```

M4D unifies automatic risk-signal detection, activation precedence, bounded
deterministic workers, local counterfactual checks, M3 expert routing, and
safe failure handling behind the additive
`M4DRiskonPipeline.run_orchestrated(QueryInput)` interface. A normal request
calls `run_planned()` exactly once. `ANSWER` worker failures fail closed; an
`ABSTAIN` worker failure preserves the abstention, route, and case capsule while
opening `ORCHESTRATION_INCOMPLETE`. No partial answer, recursive orchestration,
agent-to-agent citation, API call, LLM, or model-driven agent autonomy is used.
Artifacts are written under `data/generated/m4d/`.

The canonical success line is:

```text
M4D PASS: end-to-end 5/5; auto-activation 5/5; FAST_PATH 1/1; SHORT_CIRCUIT_CLARIFY 1/1; HUMAN_FIRST 1/1; DUAL_CHECK 1/1; FULL_ORCHESTRA 1/1; local counterfactual transitions 3/3; failure contracts 3/3; M4A regression 5/5; M4B regression 5/5; M4C regression 2/2; M0-M3 regression 28/28; partial answers after failure 0; baseline mutations 0; network disabled.
```

## Run M5B

```bash
uv run riskon evaluate --config config/milestone5b.toml
uv run riskon run --config config/milestone5b.toml \
  "Does Control Meridian apply to Service Basic in Region Beta?" \
  --context '{"region":"REGION_BETA","service_model":"SERVICE_BASIC"}'
```

M5B is the final architecture milestone. It converts structured expert
resolutions into proposed knowledge patches, runs the eleven mandatory Policy
CI checks, requires an independent human decision, creates an explicit
release, and compiles only active/current patches into an immutable retrieval
overlay. Existing M0-M4D behavior and the official corpus remain unchanged;
the overlay has no ranking boost and cannot be activated automatically. The
runtime is local-only and deterministic: it does not train or fine-tune a
model, call an API, use an LLM, or mutate official knowledge. See
[`docs/milestone5b.md`](docs/milestone5b.md) for the acceptance matrix and
governance boundary.

The evaluator writes `data/generated/m5b/evaluation.json` and `.md`,
`policy_ci_reports.jsonl`, `governance_events.jsonl`,
`knowledge_releases.jsonl`, `overlay_snapshot.json`, and `audit.jsonl`.
The canonical success line is:

```text
M5B PASS: governed evolution 5/5; activated patches 1/1; awaiting approval 1/1; rejected unsafe patches 2/2; expired patches excluded 1/1; Policy CI checks 55/55; regression gate 45/45; scope transitions 4/4; automatic approvals 0; automatic activations 0; self-approvals 0; official corpus mutations 0; expired evidence retrievals 0; network disabled.
```

## Event Readiness (ER-A)

ER-A is the additive, read-only adapter for the event-day HTML plus Excel
manifest package. It inspects a corpus outside the repository, inventories
structure, links, assets, and safety signals, and prepares only descriptors.
It does not copy or rewrite source files, fetch external URLs, execute source
instructions, or add a retrieval/LLM/API layer. Generated reports belong under
the ignored `data/generated/event_intake/` path.

Inspect a corpus:

```bash
uv run riskon inspect-corpus \
  --root <SOURCE_ROOT> \
  --manifest <MANIFEST_XLSX> \
  --output <IGNORED_OUTPUT_ROOT>
```

Run the bounded compatibility smoke suite:

```bash
uv run riskon smoke-corpus \
  --root <SOURCE_ROOT> \
  --manifest <MANIFEST_XLSX> \
  --cases <SMOKE_CASES_JSON> \
  --output <IGNORED_OUTPUT_ROOT>
```

For non-standard workbook headers, pass an explicit mapping such as
`--column-mapping '{"filename":"Document","title":"Page"}'`. The
adapter accepts only the frozen `filename`/`title` aliases (with optional
`url`) or an explicit mapping; it never guesses an unknown schema.

## Event runtime

After ER-A inspection, create the ignored local config at
`data/private/event_runtime.toml` from
[`config/event_runtime.template.toml`](config/event_runtime.template.toml).
The HTML corpus and manifest remain outside the repository. Run one question
through the unified event-backed M4D/M3 runtime with:

```bash
uv run riskon event-query \
  --config data/private/event_runtime.toml \
  --question "Is it mandatory for a Power of Attorney holder to have a K&E document?" \
  --context '{"need_type":"COMPLEX_CASE"}'
```

The output is a safe JSON summary containing the decision, local evidence
references, route, activation profile, and worker counters. It does not print
raw HTML or absolute source paths. A structured context may be required for
M3 routing; the runtime will abstain or fail closed instead of guessing.

The committed synthetic packs exercise the complete status contract:

```text
valid_pack   → READY; compatibility 3/3
warning_pack → READY_WITH_WARNINGS; external fetches 0
invalid_pack → BLOCKED; no prepared corpus or smoke execution
```

The exact ER-A acceptance command and boundary are documented in
[`docs/architecture.md`](docs/architecture.md) and
[`docs/data-boundaries.md`](docs/data-boundaries.md). ER-A is the final
event-readiness intake step before the separately scoped ER-B demo surface;
there is no M6 architecture milestone.

## Event Demo (ER-B)

ER-B is a local, static, self-contained presentation surface over the frozen
M0-M5B runtime and ER-A contracts. It is intentionally not a new retrieval,
agent, API, or server architecture. The five synthetic stories are sourced
from the actual M4D runtime and M5B evaluator:

```text
ERB-001  FAST_PATH              ANSWER
ERB-002  SHORT_CIRCUIT_CLARIFY  CLARIFY
ERB-003  FULL_ORCHESTRA         ANSWER + counterfactuals
ERB-004  HUMAN_FIRST            ABSTAIN + functional route
ERB-005  GOVERNED_EVOLUTION     ANSWER + M5B lifecycle
```

Build the canonical event-day demo bundle:

```bash
uv run riskon demo-build --config config/event_demo.toml
```

This writes the ignored, reproducible output directory
`data/generated/event_demo/`:

```text
index.html                 story-led presentation surface
dashboard.html             evaluator-backed metrics and matrix
demo_bundle.json           typed story and dashboard payload
dashboard_metrics.json     typed dashboard payload
audit.jsonl                compact ER-B build audit
```

Open `index.html` or `dashboard.html` directly with `file://`. Both pages use
inline CSS and JavaScript only, contain no CDN/font/image/API/server
dependency, and set a restrictive Content Security Policy. The dashboard
labels each metric with its actual source and keeps the following safety
values explicit: M0-M4D regression `45/45`, M5B `5/5`, Policy CI `55/55`,
counterfactual containment `4/4`, and zero automatic approvals, automatic
activations, scope violations, unsafe cases, unsupported decisions, and
network violations.

Render one story as a standalone case card:

```bash
uv run riskon demo-case --config config/event_demo.toml \
  --case ERB-003 --output data/generated/event_demo/case-ERB-003.html
```

Run one synthetic live query through the production-shaped orchestrated
surface. The command calls `run_orchestrated()` exactly once and accepts only
local context presets:

```bash
uv run riskon demo-query --config config/event_demo.toml \
  --question "What is the Synthetic Stability Marker?" \
  --output data/generated/event_demo/live.html
```

ER-B redacts source text into bounded evidence excerpts, local provenance
references, structured traces, functional queues, case-capsule metadata, and
governance metadata. It never renders raw prompts, private reasoning,
absolute paths, external URLs, credentials, or real event/Bank data. The
canonical build check ends with:

```text
Event demo PASS: stories 5/5; dashboard metrics sourced; self-contained HTML 2/2; external assets 0; network disabled.
```

ER-B is the accepted demo-surface step in this repository. It does not add an
M6 milestone or authorize processing of real event-day data.

## Event Pitch (ER-C)

ER-C packages the accepted ER-B stories and evaluator outputs for the final
RiskON pitch. It is an artifact layer, not a new architecture milestone: the
deck is generated from editable PowerPoint-native text and shapes, and the
backup is a deterministic standalone HTML replay. No real event or Bank data,
external asset, external link, network request or real person name is used.

Build the complete package:

```bash
uv run riskon pitch-build --config config/event_pitch.toml
```

Validate the generated package or render one duration profile:

```bash
uv run riskon pitch-validate --config config/event_pitch.toml
uv run riskon pitch-script --config config/event_pitch.toml --profile 5_MIN
```

The build writes the ignored `data/generated/event_pitch/` directory:

```text
riskon_orchestra_pitch.pptx   12 slides: 8 main + 4 appendix
speaker_script_3min.md        3-minute modular script
speaker_script_5min.md        5-minute canonical script
speaker_script_7min.md        7-minute extended script
live_demo_script_90s.md       90-second cue sheet
backup_demo.html              six-scene offline replay
backup_demo_runbook.md        backup operator cues
qa_bank.md                    18 bounded Q&A topics
event_day_runbook.md          opening/data/pitch checklist
one_page_summary.md           presenter summary
pitch_manifest.json           machine-readable build receipt
```

The three profiles deliberately do not assume an official team duration.
The canonical profile is 300 seconds including the 90-second live demo. Slide
seven reads its seven displayed metrics from the current generated ER-B
dashboard output rather than hard-coding evaluator values in the deck source.
The generated manifest validates 12/12 slides, 3/3 profiles, 18/18 Q&A
topics, 6/6 backup scenes, zero external assets/links/leaks and network
disabled. `python-pptx` is dev-only; it is not a production runtime
dependency.

ER-C is the stop boundary before the event. After it is frozen, the only
technical path is: inspect the real corpus read-only, validate its manifest,
run compatibility smoke tests, fix only observed adapter/retrieval failures,
then rebuild and refreeze the event package.

## Quality checks

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src/riskon
uv run pytest --disable-socket --cov=src/riskon --cov-branch --cov-report=term-missing --cov-fail-under=90
```

## Scope boundary

M0 has no external API calls, model downloads, LLM, OCR, image interpretation,
UI, HTTP server, vector database, or cloud telemetry. The image fixture is
catalogued as a reference with alt text; it is not interpreted. See
[`docs/data-boundaries.md`](docs/data-boundaries.md) and
[`docs/architecture.md`](docs/architecture.md).

M1 adds deterministic provenance, claim-level verification, selective QA, and
reporting over a separate synthetic corpus. M2 adds context-aware hybrid
retrieval over another synthetic corpus. M3 adds fixture-backed configurable
routing over structured fields. M4A adds `orchestrate_planned()` only for
frozen planned runs. M4B adds bounded deterministic workers only for frozen
planned runs. M4C adds bounded local counterfactual checks. M4D composes these
boundaries into a live, local-only `run_orchestrated()` path. M5B adds
governed knowledge evolution as an additive overlay over the unchanged M4D
runtime. These milestones do not alter the M0 `RiskonPipeline.run()` contract;
M1 remains available through
`run_verified()`, M2 adds `run_planned()`, M3 adds `run_routed()` plus
`route_planned()`. M4A/M4B/M4C retain their frozen boundaries; only an M4D
configured pipeline exposes live orchestration. M5B adds only the explicit
`run_planned_with_overlay()` and `run_orchestrated_with_overlay()` methods.
There is no M6 milestone in this prototype. ER-A handles read-only event
corpus readiness, ER-B is the static demo/dashboard, and ER-C is the final
pitch/backup/Q&A package. No new architecture, agents, LLM/OCR, API,
Kubernetes or deployment layer is planned after ER-C.
