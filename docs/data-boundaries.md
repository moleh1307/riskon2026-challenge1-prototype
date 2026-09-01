# Data and privacy boundaries

M0 is intentionally self-contained:

- Runtime reads only `data/synthetic/`.
- Runtime writes only `data/generated/`.
- Every evidence reference uses the `local://synthetic/` scheme.
- No network, API key, endpoint, cloud SDK, model download, or external
  telemetry is present.
- The repository contains no event-day or confidential reference material.
- The SVG fixture is stored and cited as an image reference; no pixels are
  interpreted and no OCR is attempted.
- JSONL audit output is local and contains only synthetic scenario data.

M1 adds only `data/synthetic/m1/` and keeps its generated outputs under
`data/generated/m1/`. Its provenance references use either
`local://synthetic/` or `local://synthetic-m1/`; absolute filesystem paths and
HTTP/HTTPS references are rejected by the evaluation and reporting checks.
The intentionally unlabelled M1 SVG is detected as an unsupported modality;
it is not interpreted.

M2 adds only `data/synthetic/m2/` and keeps its generated outputs under
`data/generated/m2/`. Its provenance references use
`local://synthetic-m2/`, including the explicitly declared synthetic form
attachment. The M2 evaluator rejects absolute paths, HTTP/HTTPS references,
contact details, and unsupported network evidence. M2 uses deterministic
word/character TF-IDF and structure-aware table-row retrieval only; it does not
use embeddings, a local or hosted LLM, OCR, image understanding, or a vector
database.

M3 adds only synthetic routing inputs under `data/synthetic/m3/`:

- versioned support-function rules;
- synthetic expert profiles and routing profiles;
- synthetic network edges; and
- complete frozen `PlannedVerifiedRun` fixtures for the eight routing cases.

The M3 evaluator uses `local://synthetic-m3/` fixture references and never
reruns source M0/M1 queries. The source scenario ID is lineage only. The
routing component receives only structured fields; it does not receive the
original query, normalised query, answer text, or retrieved text. Generated
M3 diagnostics and audit records remain under `data/generated/m3/` and are
checked for absolute paths, HTTP/HTTPS references, and contact details.
M3 adds no real expert data, external API, cloud, LLM, embedding, or network
runtime.

## ER-A event corpus boundary

ER-A accepts a repo-external event package as a read-only source root. The
package may contain HTML, local assets, and an XLSX filename/title manifest;
the manifest may be supplied as an explicit external read-only file, while
output must remain outside the HTML source root. Source symlinks are resolved
before use and any root escape blocks intake. The event paths are supplied at
invocation time and are not hard-coded into production configuration.

The adapter opens only non-macro XLSX data with `read_only=True` and
`data_only=True`, using the frozen alias registry or an explicit logical-column
mapping. It does not evaluate formulas, open external workbook links, call
external URLs, execute HTML/scripts/forms/source instructions, invoke a
subprocess, or mutate/copy the source package. External links, missing local
assets, orphan HTML, unsupported files, and instruction-like text are safe
inventory warnings; unsafe paths, duplicate filenames, missing manifest HTML,
encoding/parse failures, and output-root violations block preparation.

ER-A reports and prepared objects contain only relative paths, titles, counts,
hashes, local-link relationships, descriptors, and issue codes. They exclude
raw HTML and paragraphs, client or Bank content, credentials, absolute paths,
external URLs, API payloads, and private reasoning. Compatibility smoke tests
use only an ephemeral sanitized copy outside the source root to exercise the
existing M2 retrieval and M1 verification components; that temporary copy is
removed after the run. Persisted outputs are limited to ignored
`data/generated/event_intake/` artifacts, and `network_enabled`, external
fetching, source mutation, instruction execution, and subprocess activity are
all disabled.

The boundary is a prototype constraint, not a claim that the event-day data
may be processed by any particular provider. External data handling, derived
artefacts, retention, and approved processors remain open questions for the
event organisers. The 26 August Q&A is therefore non-blocking for M2/M3
synthetic evaluation but still controls any later event-data, real routing, or
deployment milestone.

## Event runtime boundary

The event runtime reads the ER-A-approved HTML source root and external XLSX
manifest directly from operator-supplied paths. It never copies those inputs
into the repository and never writes inside the source root. The event corpus
is held in memory as the M4D `LocalCorpus`; generated intake descriptors and
structured audit rows remain under ignored `data/generated/event_runtime/`.

All event evidence uses `local://event-wiki/` references. Absolute paths,
HTTP/HTTPS URLs, synthetic M4D references, source instructions, and credentials
are excluded from the query payload. The runtime reuses the frozen M2/M1/M3/M4D
components and keeps overlays, network access, external APIs, and recursive
execution disabled. A missing or incomplete structured routing context can
leave a safe `ABSTAIN` unable to produce an M3 expert route; the CLI reports
that configuration failure rather than inventing a route.

## M4A boundary

M4A reads only the frozen M4 activation policy, case set, and local upstream
`PlannedVerifiedRun` fixtures. Its production surface is a zero-worker shell:
no `asyncio` task creation, worker import, agent-catalog execution, LLM/model
adapter, API call, or network access is permitted. `HUMAN_FIRST` delegates
only to the existing deterministic M3 route boundary and emits a structured
case capsule containing local evidence references and routing state; it does
not copy raw source text or private reasoning. `DUAL_CHECK` and
`FULL_ORCHESTRA` are fail-closed and reserved for M4B.

M4A writes `evaluation.json`, `evaluation.md`, and its structured `audit.jsonl`
under ignored `data/generated/m4a/`. The M4A audit has no query field, raw
source text, absolute path, HTTP/HTTPS URL, credential, or contact-like data;
it records zero active agents and zero worker executions.

## M4B boundary

M4B reads the frozen M4 activation policy, worker-selection policy, agent
catalog, source-safety policy, manifest, HTML corpus, and upstream
`PlannedVerifiedRun` fixtures. It writes only ignored outputs under
`data/generated/m4b/`. The worker backend is
`DETERMINISTIC_WORKER_V1`; there is no LLM, model adapter, cloud call, API
client, agent chat, recursive delegation, or network egress.

The worker ledger and reports contain local provenance references and safe
structured metadata. They do not contain raw query text, raw source-document
dumps, absolute filesystem paths, HTTP/HTTPS URLs, credentials, or real Bank
data. Source instructions are data, not executable instructions; suspicious
content produces `SOURCE_INSTRUCTION_IGNORED` diagnostics and cannot affect
tools, routing, or the final decision. M4B handles only the five frozen
non-counterfactual worker cases. Counterfactual handling is explicitly
reserved for M4C.

## M4C boundary

M4C reads the frozen synthetic M4 corpus plus its structured context-value
registry and local counterfactual policy. Counterfactual variants are bounded,
local planned-pipeline executions. They contain only explicit context deltas
and local provenance references; they do not call an API, route to an expert,
or invoke recursive orchestration. The M4C audit and evaluation artifacts are
written under ignored `data/generated/m4c/`.

## M4D boundary

M4D reads only the synthetic M4D corpus, its manifest, runtime/failure policy,
and frozen baseline/counterfactual snapshots. The normal request path calls
the local `run_planned()` pipeline exactly once, then passes structured
assessment/context objects into the bounded orchestra. Query text is not
copied into orchestration context or audit rows; successful audits retain only
a query hash.

M4D keeps the following controls disabled: network access, external APIs,
recursive orchestration, counterfactual routing, and agent-to-agent
citations. Worker failures on an `ANSWER` baseline fail closed without an
answer or route. Failures on an `ABSTAIN` baseline discard partial findings
and preserve only the baseline abstention, existing M3 route, case capsule,
and an open `ORCHESTRATION_INCOMPLETE` material objection. No partial answer
is enabled and no retry is performed.

M4D generated JSONL, audit, and report artifacts contain safe structured
metadata and local references only. They exclude raw source-page dumps,
private chain-of-thought, absolute filesystem paths, HTTP/HTTPS URLs,
credentials, contact details, and real Bank or event data. M4D is a
deterministic runtime with bounded workers and local counterfactual checks;
it is not an LLM, cloud, API, UI, or deployment boundary.

## M5B boundary

M5B reuses only the frozen synthetic M5A/M4D contracts and local M5B fixture
inputs under `data/synthetic/m5b/`. Structured expert resolutions are treated
as proposals, not evidence. A proposed patch becomes retrievable only after
all eleven mandatory Policy CI checks, a separate human approval, and an
explicit release activation. No automatic, agent, or self-approval is
allowed; `APPROVED` is still non-active.

The official M4D corpus is read-only. The overlay is a separate in-memory and
serialized snapshot under `data/generated/m5b/`; it contains only active,
current, explicitly scoped claims. Rejected, awaiting-approval, superseded,
future, and expired patches are excluded. Overlay evidence keeps its original
backing references and uses only local provenance references in the
`local://knowledge-overlay/` namespace. A resolution ID, approval ID, or
governance event is not evidence. Official/overlay contradiction is a
fail-closed condition, and overlay claims receive no ranking boost.

M5B outputs are compact structured JSON/JSONL/Markdown artifacts: evaluation,
Policy CI reports, append-only governance events, release records, the
compiled overlay snapshot, and an audit. The M5B audit has a closed schema and
rejects network-enabled rows, URLs, absolute paths, contact-like strings, and
duplicate case IDs. The runtime has no event corpus adapter, external API,
LLM, model training/fine-tuning, telemetry, cloud service, or network egress;
real event-day or confidential Bank data is outside this repository and this
prototype. M5B is the final architecture milestone; no M6 implementation is
planned.

ER-A is an operational adapter after the M5B architecture freeze. It is not
an M6 layer and does not authorize real event-data ingestion beyond a future
operator-controlled local inspection. ER-B (demo/dashboard) and ER-C (pitch
and backup demo) are separate, review-gated presentation layers.

## ER-B demo boundary

ER-B reads only the committed synthetic event-demo contracts under
`data/synthetic/event_demo/`, the frozen local M4D/M5B configuration and
fixtures, and the existing local runtime. Its generated artifacts are ignored
and confined to `data/generated/event_demo/`. No event-day HTML, Excel
manifest, Bank material, credentials, or real expert identity is copied into
the repository or embedded in the pages.

The five cards and dashboard are built from typed, redacted view models. They
may expose bounded evidence excerpts, local provenance references, structured
worker-stage labels, synthetic functional queues, case-capsule metadata, and
governance counters. They do not expose raw source pages, raw prompts, private
chain-of-thought, absolute paths, contact details, external URLs, or source
instructions. Excerpts are limited to 280 characters; HTML values are escaped
and embedded JSON escapes `<`, `>`, and `&` to prevent markup breakout.

The pages are usable as `file://` documents and have no server, socket,
external asset, CDN, font, image, API, telemetry, cloud, LLM, or model
dependency. Their runtime security contract keeps network access, external
APIs, telemetry, and local servers disabled. `demo-query` remains local and
calls the existing `run_orchestrated()` surface once; it does not add a live
provider or a second orchestration path.

Dashboard metrics are evaluator-backed rather than hand-entered: M0-M4D
regression `45/45`, M5B `5/5`, Policy CI `55/55`, and counterfactual
containment `4/4`. Zero-valued safety metrics are labelled explicitly when
they measure disabled behavior, and unsupported or unsafe cases are not
silently presented as successful answers. ER-B is a presentation and
evaluation boundary only; it does not authorize real event-data processing,
deployment, or an M6 milestone.

## ER-C pitch and backup boundary

ER-C reads only the frozen ER-C contracts, the generated ER-B
`demo_bundle.json`, and the generated ER-B dashboard metric source. It writes
only ignored artifacts under `data/generated/event_pitch/`. The tracked source
contains no real event package, Bank material, real person identity, contact
detail, credential, absolute filesystem path or confidential source excerpt.

The PowerPoint is built from editable text and shapes with no media or
external relationships. Metric values are resolved by ID from the current
dashboard output and retain a source label in the deck notes and manifest.
The six-scene backup is a standalone HTML document with inline CSS and
JavaScript; it makes no request, opens no server, and does not depend on the
Python runtime, CLI, terminal or evaluator execution after generation.

ER-C is not a new retrieval, worker, governance or deployment architecture.
Its security switches remain network/API/telemetry/server disabled, and its
honest-limitations slide explicitly distinguishes deterministic prototype
evidence from unproven production accuracy, access control, image
interpretation, calibration, latency and scale. After ER-C, only read-only
event-corpus inspection, compatibility smoke testing and targeted fixes for
observed event-data failures are in scope.
