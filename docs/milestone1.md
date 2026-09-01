# M1 — Evidence Contract & Selective-QA Evaluation Harness

M1 adds a verification layer over the M0 pipeline without changing
`RiskonPipeline.run(QueryInput) -> PipelineResult`. The new
`run_verified()` interface verifies claims, provenance, scope, required links,
critical controls, and unsupported modalities before returning a
`VerifiedRun`.

## Run M1

```bash
uv sync --frozen
uv run riskon evaluate --config config/milestone1.toml
```

The command writes:

- `data/generated/m1/evaluation.json`
- `data/generated/m1/evaluation.md`
- `data/generated/m1/audit.jsonl`

M1 remains local-only and uses only the seven synthetic M1 HTML pages, one
synthetic XLSX manifest, and one intentionally unlabelled SVG fixture.

## Verification contract

The verifier admits an answer only when each substantive claim has a local
provenance reference, explicit support, correct scope, and all relevant
mandatory controls. It returns `CLARIFY` for missing context or ambiguous
acronyms. It returns `ABSTAIN` for unsupported applicability, missing linked
references, image-only evidence, or approval requests.

The M1 confidence label remains
`DETERMINISTIC_GATE_PLACEHOLDER`; it is not a calibrated probability.
