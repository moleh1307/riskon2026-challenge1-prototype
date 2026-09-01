# M4A zero-worker orchestration shell

M4A adds an additive orchestration boundary over frozen M2 `PlannedVerifiedRun`
inputs and the existing M3 router. It is deliberately not an agent swarm and
does not execute workers, call a model, or make network requests.

## Public boundary

```text
RiskonPipeline.orchestrate_planned(
    planned_verified_run,
    orchestration_context,
    orchestration_profile,
) -> OrchestraRun
```

The input is consumed without changing its query plan, retrieval diagnostics,
verification report, evidence, or legacy route. `run_orchestrated()` is not
part of M4A.

## Implemented profiles

- `FAST_PATH` preserves a baseline `ANSWER` with no route, capsule, tasks,
  findings, objections, counterfactuals, or worker executions.
- `SHORT_CIRCUIT_CLARIFY` preserves a baseline `CLARIFY` and its exact
  clarification text without routing or workers.
- `HUMAN_FIRST` preserves a baseline `ABSTAIN`, invokes the existing
  `route_planned()` boundary, and creates a structured `CaseCapsule`.

`DUAL_CHECK` and `FULL_ORCHESTRA` are present in the closed activation policy
but fail closed with `OrchestraWorkersNotImplementedError`. Their deterministic
worker fan-out is an M4B concern.

## Evaluation

```bash
uv sync --frozen
uv run riskon evaluate --config config/milestone4a.toml
```

The evaluator reads the five selected cases from frozen M4 upstream fixtures;
it does not rerun their source queries. It writes the ignored artifacts
`data/generated/m4a/evaluation.json`, `evaluation.md`, and `audit.jsonl`.
The audit contains only structured activation, decision, route-summary, and
zero-worker metrics; it contains no raw query or source text.

The M4A acceptance line is:

```text
M4A PASS: zero-worker paths 5/5; FAST_PATH 1/1; SHORT_CIRCUIT_CLARIFY 1/1; HUMAN_FIRST 3/3; M0-M3 regression 28/28; active agents 0; baseline mutations 0; network disabled.
```
