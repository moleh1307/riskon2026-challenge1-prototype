# M3 — Configurable expert routing

M3 extends the unchanged M2 planning, retrieval, and verification pipeline with
deterministic, configurable expert routing. It remains a local-only synthetic
prototype: the router receives structured fields, never the original query,
retrieved text, or answer text.

## Integration contract

The live path is:

```text
run_routed(QueryInput)
  → run_planned(QueryInput)
  → route_planned(PlannedVerifiedRun, RoutingContext, profile)
  → routed result or no route
```

`run_routed()` delegates to the public `route_planned()` method. Routing is
mandatory only when the actual M2 result is `ABSTAIN`. `ANSWER` and `CLARIFY`
return `expert_route = null` with `NOT_ROUTED_DECISION`. A legacy M0/M1/M2
support-function conflict fails closed with `BLOCKED` and
`LEGACY_ROUTE_CONFLICT`.

`route_planned()` does not mutate the upstream `PlannedVerifiedRun`. The
`RoutingRequest` is limited to these structured fields:

- need type
- reason codes
- topics
- jurisdiction
- region
- system
- requester team
- routing profile

Reason codes must match the upstream verified result; a routing context cannot
override them.

## Frozen evaluator fixtures

The M3 contract is schema `1.1`. Each of the eight M3 cases contains a
`LINEAGE_ONLY` source scenario ID and a local fixture reference. The evaluator
loads a complete synthetic `PlannedVerifiedRun` from
`data/synthetic/m3/upstream_runs/`; it does not rerun the source M0/M1 query.
The source scenario is lineage only.

Every fixture is required to contain an `ABSTAIN` result with no answer or
clarifying question, `INSUFFICIENT` verification, non-empty reason codes, and
a non-null legacy support-function route with no legacy person ID. The frozen
fixture envelope is versioned as `SYNTHETIC_ROUTING_FIXTURE_V1`.

## Routing inputs and behavior

Routing is data-driven by versioned synthetic files:

- `support_model_v1.json` and `support_model_v2.json` map structured need and
  reason combinations to support functions.
- `expert_profiles_v1.json`, `expert_profiles_capacity_stress.json`, and
  `expert_profiles_v2.json` provide synthetic expert capabilities and status.
- `network_edges.json` provides deterministic synthetic requester-to-expert
  proximity weights.
- `config/milestone3.toml` defines thresholds, weights, tie-breaking, reference
  time, and the profiles `default`, `capacity_stress`, and `support_v2`.

Hard gates exclude inactive, out-of-window, wrong-function, wrong-mandate,
wrong-jurisdiction, wrong-region, wrong-system, or unavailable experts.
Eligible candidates are scored with configured applicable-weight
renormalisation. The router returns either a person route or a functional
queue fallback. Person selection requires the configured minimum score and
margin; low-confidence cases remain at the queue level.

The confidence label is
`DETERMINISTIC_ROUTING_HEURISTIC_V1`, not a calibrated probability. Selection,
top-k candidates, exclusions, fallback reason, decisive factors, and
alternatives are emitted as structured explainability fields.

## Evaluation and artifacts

Run the complete M3 evaluation with:

```bash
uv sync --frozen
uv run riskon evaluate --config config/milestone3.toml
```

The evaluator includes M0/M1/M2 regression cases and the eight M3 cases. The
canonical success line is:

```text
M3 PASS: aggregate 28/28; M0 5/5; M1-new 7/7; M2-new 8/8; M3-new 8/8; support functions 8/8; person-or-queue 8/8; hot-swap 1/1; hard-constraint violations 0; network disabled.
```

Generated M3 artifacts are written under `data/generated/m3/`:

- `evaluation.json` and `evaluation.md`
- `routing_diagnostics.jsonl`
- `audit.jsonl`

## Non-goals and safety boundary

M3 does not add a real bank directory, real employee data, external APIs,
cloud services, LLM calls, embeddings, deployment, event-day ingestion, or
person-level authority. It is a synthetic routing and explainability
demonstration. Any later use with event or bank data requires organiser
answers, approved data handling, and a separate milestone.
