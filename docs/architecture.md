# M0/M1/M2/M3/M4D/M5B + ER-A/ER-B/ER-C architecture

`RiskonPipeline` is the base public pipeline surface. It receives a
`QueryInput` and returns a validated `PipelineResult`; M5B adds a separate
overlay-enabled surface without changing that base contract.

1. `config.py` loads TOML with `tomllib` and rejects network-enabled runtime
   configuration.
2. `ingestion.py` reads the synthetic workbook manifest and local HTML files.
   It creates one `Section` per heading and preserves text, lists, tables,
   links, and image references.
3. `context.py` extracts only deterministic structured hints such as region,
   channel, workflow stage, and need type.
4. `retrieval.py` builds a TF-IDF index with lowercase text, English stop words,
   1–2 word n-grams, and L2 normalization. The five highest-scoring sections
   are returned with stable tie-breaking.
5. `evidence.py` applies the deterministic evidence gate. Missing channel
   context becomes `CLARIFY`; scope conflicts, technical failures, and weak
   evidence become `ABSTAIN`.
6. `answering.py` composes an extractive answer from the selected local
   evidence. It does not generate unsupported content.
7. `routing.py` applies the structured reason/need policy to synthetic expert
   records. Raw query keyword matching is not used for routing.
8. `audit.py` appends a local JSONL trace with evidence references and the
   deterministic confidence placeholder.

The decision contract is intentionally small:

- `ANSWER`: substantive extractive answer and evidence, without a route.
- `CLARIFY`: exactly one specific clarifying question, without an answer or
  route.
- `ABSTAIN`: one or more reason codes, a route, and no speculative answer.

Confidence values are gate outputs, not calibrated probabilities. Every result
is labelled `DETERMINISTIC_GATE_PLACEHOLDER`.

## M1 verification layer

M1 loads a separate seven-page synthetic corpus and keeps the M0 corpus/config
unchanged. `RiskonPipeline.run_verified(QueryInput)` first obtains the same
deterministic provisional result, then applies `VerificationEngine`:

- `ProvenanceIndex` addresses sections, sentences, table rows, and assets with
  stable `local://` references.
- `AnswerClaim` objects map substantive answer claims to those references.
- Explicit-support, scope, critical-control, required-reference, modality, and
  relevance gates produce a `VerificationReport`.
- A failed gate converts an unsafe provisional answer to `CLARIFY` or
  `ABSTAIN`, while `run()` retains the M0 behavior.
- `M1Evaluator` combines M0 regression and M1 cases into deterministic metrics
  and JSON/Markdown reports.

## M2 planned retrieval layer

M2 keeps `run()` and `run_verified()` unchanged and adds:

```text
RiskonPipeline.run_planned(QueryInput) -> PlannedVerifiedRun
```

The M2 flow is:

```text
Question
→ QueryPlan
→ Exact / Word TF-IDF / Character TF-IDF / Table-Row channels
→ Explicit scope filtering
→ Weighted RRF fusion
→ M1-style claim/evidence verification
→ Answer / Clarify / Abstain
```

`QueryPlan` is closed-world and deterministic. It contains the original and
normalised query, one of six allowed intents, canonical terms, required and
missing context, at most three explicit-conjunction subqueries, selected
channels, and a retrieval-short-circuit flag. Alias normalization is driven
only by `data/synthetic/m2/aliases.json`; there is no generic fuzzy correction.

`HybridRetriever` indexes table rows with page title, section heading, table
headers, and row values. It fuses channel ranks with
`weight / (60 + channel_rank)` and breaks ties by provenance reference. Every
candidate decision is captured in `RetrievalDiagnostics`, including explicit
scope exclusions and final-rank inclusion.

M2 uses custom stable `local://synthetic-m2/` section and table-row references,
while the existing M0/M1 provenance reference style remains unchanged. M2
does not add external APIs, embeddings, model downloads, vector databases,
OCR, image understanding, UI, HTTP, deployment, or event-day data.

## M3 configurable routing layer

M3 preserves the M2 upstream result and adds a separate routing boundary:

```text
QueryInput
  → run_planned()
  → PlannedVerifiedRun
  → route_planned(RoutingContext, routing_profile)
  → RoutedRun
```

`run_routed()` is the convenience path that composes these calls. The router
is invoked only for an actual `ABSTAIN`. Its input is a closed structured
`RoutingRequest`; raw query text, normalised query text, answer text, and raw
retrieved text are not passed to it. An upstream legacy support-function
conflict blocks the route rather than silently changing the M0/M1/M2 result.

The routing layer loads versioned synthetic support rules, expert profiles,
and network edges from `data/synthetic/m3/`. Hard constraints run before
configured weighted scoring. The result is either a selected expert or a
functional queue fallback, with deterministic top-k diagnostics and a
machine-readable explanation. Profile selection and thresholds are configured
in `config/milestone3.toml`.

The M3 evaluator uses complete frozen `PlannedVerifiedRun` fixtures under
`data/synthetic/m3/upstream_runs/`. The source M0/M1 scenario ID is lineage
only; evaluator cases do not rerun source queries. This keeps routing
evaluation independent from upstream retrieval changes while the live
`run_routed()` path remains connected to the actual M2 result.

## M4A zero-worker orchestration shell

M4A adds a separate boundary over the frozen planned result:

```text
PlannedVerifiedRun
  → orchestrate_planned(OrchestraContext, activation_profile)
  → OrchestraRun
```

The runtime validates the frozen activation policy and supports only
`FAST_PATH`, `SHORT_CIRCUIT_CLARIFY`, and `HUMAN_FIRST`. The first two preserve
the verified result directly. `HUMAN_FIRST` calls the existing
`route_planned()` callback and converts the structured route into a
`CaseCapsule`; it does not alter the baseline.

M4A creates no worker tasks and has no worker package, model adapter, network
client, or `run_orchestrated()` convenience method. `DUAL_CHECK` and
`FULL_ORCHESTRA` raise a typed fail-closed error until M4B implements their
worker fan-out. M4A evaluation consumes only frozen fixtures and records a
separate structured audit contract under `data/generated/m4a/`.

## M4B deterministic bounded worker orchestra

M4B consumes the same shape of frozen `PlannedVerifiedRun` through the
following closed execution graph:

```text
PlannedVerifiedRun
  → signal-driven role selection
  → bounded discovery fan-out (max 3)
  → deterministic fan-in / append-only Evidence Ledger
  → candidate claim builder
  → one Skeptic challenge wave
  → Material Objection Gate
  → existing M1 VerificationEngine
  → ANSWER or ABSTAIN
  → M3 route and M4B case capsule only after ABSTAIN
```

The four implemented roles are `EVIDENCE_SCOUT`, `SCOPE_SENTINEL`,
`PROCESS_TABLE_SCOUT`, and `SKEPTIC`. Workers can cite only local corpus
references; they cannot cite another worker, delegate recursively, route to an
expert, or make the final decision. Worker selection is driven by the frozen
signal policy, never by case-ID branches. M4B has exactly one discovery wave
and one challenge wave; `COUNTERFACTUAL_SENTINEL` and repair waves are M4C
scope.

Source content is treated as untrusted data. Suspicious instruction-like text
is recorded as a safe diagnostic and excluded from candidate evidence. The
M4B evaluator writes safe task, ledger, objection, audit, JSON, and Markdown
artifacts under `data/generated/m4b/`; those artifacts contain references and
structured metadata, not raw queries or source-document dumps.

## M4C local counterfactual boundary

M4C adds one bounded `COUNTERFACTUAL_SENTINEL` wave for explicit, structured
scope changes. Each variant runs through the local planned pipeline and is
adjudicated for a safe transition such as `ANSWER → ABSTAIN` on a scope leak
or `ANSWER → CLARIFY` when required context is removed. Counterfactual
execution never routes to an expert and never delegates recursively. An open
material scope objection blocks the unsafe final answer.

## M4D unified runtime

M4D is the single live orchestration path:

```text
QueryInput
  → run_planned() exactly once
  → automatic risk-signal detection
  → activation-profile precedence
  → OrchestraContext
  → orchestrate_planned()
  → OrchestraRun
```

`M4DRiskonPipeline.run_orchestrated()` selects one of five profiles in frozen
precedence order: `SHORT_CIRCUIT_CLARIFY`, `HUMAN_FIRST`, `FULL_ORCHESTRA`,
`DUAL_CHECK`, and `FAST_PATH`. The detector records signal provenance from
baseline decision/reason codes, structured context, evidence metadata,
verification state, retrieval diagnostics, and source-safety diagnostics; it
does not receive or rewrite an expected case ID.

`FAST_PATH`, clarification short-circuit, and `HUMAN_FIRST` use zero workers.
The two worker profiles use the M4B bounded discovery/challenge graph, and
`FULL_ORCHESTRA` may add the local M4C counterfactual wave. Structural limits
are seven total worker tasks, one worker depth, three parallel discovery
workers, one challenge round, three counterfactual variants, and one
counterfactual depth.

Failure behavior is decision-aware and fail-closed. A failed worker or local
counterfactual check on a baseline `ANSWER` raises
`OrchestraFailClosedError` with no answer or invented route. A failed worker
on a baseline `ABSTAIN` discards partial findings, preserves the existing M3
route and case capsule, and opens a material `ORCHESTRATION_INCOMPLETE`
objection. Invalid policy, schema, security, or budget configuration raises
`OrchestraConfigurationError` or the typed budget error without a fallback.

All M4D runtime and failure audit rows are local structured records. They keep
query identity as a hash and exclude raw queries, source dumps, private
reasoning, absolute paths, URLs, credentials, and real Bank content. The
runtime is deterministic and does not add an LLM, model adapter, API, UI,
deployment, recursive orchestration, or agent-to-agent citation path.

## M5B governed knowledge overlay

M5B is an additive governance boundary over the working M4D runtime. It does
not modify the official corpus or the existing pipeline methods:

```text
Structured ExpertResolution + KnowledgePatch
  → append-only proposal event
  → Policy CI (11 mandatory checks)
  → independent HumanApproval
  → APPROVED patch (still not retrievable)
  → explicit KnowledgeRelease activation
  → active/current KnowledgeOverlaySnapshot
  → run_planned_with_overlay() / run_orchestrated_with_overlay()
```

The patch lifecycle is closed and explicit:
`PROPOSED → TESTED → AWAITING_APPROVAL → APPROVED → ACTIVE`, with
`TESTED/AWAITING_APPROVAL → REJECTED` and `ACTIVE → EXPIRED`. Direct
shortcuts, automatic approval, automatic activation, agent approval, and
self-approval are rejected. Governance events are append-only JSONL records
with stable event type, actor, status, and reason-code fields.

Policy CI evaluates exactly these checks in stable order:

```text
EVIDENCE_COMPLETENESS → CLAIM_SUBSET → SCOPE_CONTAINMENT
→ CONTRADICTION_DETECTION → CRITICAL_CONTROL_PRESERVATION
→ REFERENCE_RESOLUTION → M0_M4D_REGRESSION
→ COUNTERFACTUAL_CONTAINMENT → SEPARATION_OF_DUTIES
→ HUMAN_APPROVAL_PRESENT → EFFECTIVE_PERIOD_VALID
```

The overlay compiler admits only `ACTIVE` patches whose effective period
contains the reference time and whose release is active. Each overlay unit
has explicit scope, preserved backing evidence references, an immutable local
provenance reference of the form
`local://knowledge-overlay/<release-id>/<patch-id>#claim-<claim-id>`, and no
special retrieval boost. Official evidence remains separate. If official and
overlay claims conflict, retrieval/verification fails closed; an expert
resolution or a governance approval is never treated as evidence by itself.

The M5B evaluator replays five frozen M5A-derived cases: one successful
activation, one awaiting independent approval, two unsafe rejections, and one
expired patch exclusion. It emits deterministic reports under
`data/generated/m5b/`, including Policy CI JSONL, release/event ledgers, the
compiled overlay snapshot, and a compact audit whose schema rejects network,
URL, path, contact, and raw-content leakage. M5B remains local-only and
deterministic: it does not train or fine-tune a model from expert
conversations, call an external API, use an LLM, or activate a patch by
itself. After M5B there is no M6 architecture milestone.

## ER-A event corpus intake and compatibility adapter

ER-A is an operational readiness boundary, not a new architecture milestone.
It sits beside the frozen M0-M5B runtime and adapts a repo-external event
package into the existing local ingestion/retrieval/verification path:

```text
external source root (read-only)
  → path and symlink checks
  → XLSX manifest mapping
  → HTML structure/link/asset inventory
  → descriptor-only PreparedCorpus
  → temporary sanitized smoke view
  → existing M2 planner + hybrid retriever + M1 verifier
```

`EventCorpusAdapter` exposes three closed methods:

```text
inspect(CorpusIntakeRequest) → CorpusIntakeReport
prepare(CorpusIntakeRequest) → PreparedCorpus | None
smoke_test(PreparedCorpus, tuple[CorpusSmokeCase, ...])
  → CorpusCompatibilityReport
```

The input source and manifest are never changed. The manifest is opened with
`read_only=True` and `data_only=True`; macros, formula execution, and external
workbook links are not used. Header detection is limited to the versioned
alias registry, with explicit mappings available for event-specific headers.
An unsafe path, missing required HTML, duplicate filename, encoding/parse
failure, root escape, or output-inside-source condition blocks preparation.

HTML inspection keeps counts, hashes, titles, relative references, and issue
codes only. Scripts, styles, forms, comments, hidden nodes, external URLs,
and instruction-like source text are treated as untrusted inventory signals;
none is executed or fetched. Compatibility creates an ephemeral sanitized
copy in a temporary directory only so the existing deterministic M1/M2
components can be exercised. No event HTML is copied into the repository,
and no event-specific retrieval or answer logic is added.

The two commands are:

```bash
uv run riskon inspect-corpus \
  --root <SOURCE_ROOT> \
  --manifest <MANIFEST_XLSX> \
  --output <IGNORED_OUTPUT_ROOT>

uv run riskon smoke-corpus \
  --root <SOURCE_ROOT> \
  --manifest <MANIFEST_XLSX> \
  --cases <SMOKE_CASES_JSON> \
  --output <IGNORED_OUTPUT_ROOT>
```

Reports under `data/generated/event_intake/` contain no raw HTML, raw
paragraphs, absolute paths, external URLs, credentials, or private reasoning.
The acceptance boundary is `READY`, `READY_WITH_WARNINGS`, or `BLOCKED`, with
the valid synthetic pack passing three of three compatibility cases. ER-A
does not add a UI, dashboard, OCR, LLM, API, deployment, real event-data
ingestion, or M6 milestone. ER-B and ER-C are separately scoped presentation
layers that consume only accepted local outputs.

## ER-B local demo and evaluation dashboard

ER-B is a thin read-only presentation layer over the frozen runtime. It does
not alter M0-M5B or ER-A contracts and does not introduce a second
orchestration engine:

```text
event_demo.toml + synthetic story contracts
  → DemoCatalog
  → M4D run_orchestrated() / M5B evaluator
  → redacted StoryView + DashboardView
  → inline static HTML
```

The five story cases are fixed in `data/synthetic/event_demo/` and map to
M4D-041, M4D-042, M4D-045, M4D-043, and M5A-046. The runner executes the
actual local M4D paths, including the auxiliary M4D-044 regression case used
by the dashboard matrix, then sources governance metrics from the actual M5B
evaluation document. Expected view files validate decision, activation
profile, reason codes, route fields, evidence presence, counterfactual count,
and the governed lifecycle before rendering.

The static renderer is deliberately dependency-free: vanilla HTML, inline
CSS, and minimal inline JavaScript. It provides keyboard-operable tabs,
visible focus states, semantic headings/tables/lists, responsive layout, and
print CSS. The exact CSP is:

```text
default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none';
```

All dynamic values are HTML-escaped and JSON-embedded with `<`, `>`, and `&`
escaped before insertion. Sanitization removes source scripts, styles,
comments, URLs, absolute paths, instruction-like content, and controls; an
evidence excerpt is capped at 280 characters. Rendered pages contain no
external asset references or network requests.

`demo-build` writes only the ignored `data/generated/event_demo/` bundle and
the compact audit record. `demo-case` creates one standalone story card.
`demo-query` is the only interactive path: it reads a local query and
optional local JSON context, calls `M5BRiskonPipeline.run_orchestrated()` once,
and writes one standalone card. None of these commands starts a server,
opens a socket, calls an API, loads a model, or reaches the event corpus.

ER-B is complete at the static demo boundary. ER-C consumes the generated
ER-B bundle and dashboard outputs but does not add another runtime or
orchestration engine.

## ER-C final pitch package

ER-C is the final event-facing artifact boundary. It turns the accepted ER-B
stories and evaluator outputs into an editable PowerPoint, modular presenter
scripts, a ninety-second live-demo cue sheet, a deterministic offline backup,
a Q&A bank, and an event-day runbook:

```text
frozen ER-C contracts + ER-B demo bundle/dashboard metrics
  → 12-slide editable deck (8 main + 4 appendix)
  → 3-, 5- and 7-minute timing profiles
  → 90-second live demo and six-scene offline replay
  → Q&A bank, speaker profiles and event-day runbook
```

The source contract is under `data/synthetic/event_pitch/` and is loaded by
`config/event_pitch.toml`. The deck uses only PowerPoint-native text and
shapes; it embeds no media, external font, logo, hyperlink or image. The
`python-pptx` package is dev-only and is not part of the RiskON runtime
dependency surface. Generated files are confined to the ignored
`data/generated/event_pitch/` directory.

Slide-seven evaluator values are read from the current ER-B
`dashboard_metrics.json` source at build time. The generated manifest records
metric provenance, slide/timing/demo/Q&A/backup cardinalities and leakage
counts; evaluator values are not duplicated as literals in deck-generation
source. The backup HTML embeds sanitized ER-B run objects and uses only
inline CSS/JavaScript, so it is independent of the Python runtime, CLI,
terminal, live pipeline, evaluator execution, network and server.

The public commands are:

```bash
uv run riskon pitch-build --config config/event_pitch.toml
uv run riskon pitch-validate --config config/event_pitch.toml
uv run riskon pitch-script --config config/event_pitch.toml --profile 5_MIN
```

ER-C is the stop boundary before the event. It does not add new agents,
retrieval, governance, LLM/OCR, API, deployment or an M6 architecture
milestone. After this package is frozen, only event-day ER-A inspection,
compatibility testing and targeted fixes for observed corpus failures remain.
