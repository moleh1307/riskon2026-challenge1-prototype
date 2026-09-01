# M2 — Context-Aware Hybrid Retrieval & Robustness Harness

M2 is a deterministic, synthetic-only retrieval milestone. Its purpose is to
make the M1 evidence contract robust to declared typos, paraphrases, explicit
acronym expansion, table-row lookup, multi-part questions, and explicit
business-context conflicts.

## Public interface

M0 and M1 remain unchanged:

```text
RiskonPipeline.run(QueryInput) -> PipelineResult
RiskonPipeline.run_verified(QueryInput) -> VerifiedRun
```

M2 adds:

```text
RiskonPipeline.run_planned(QueryInput) -> PlannedVerifiedRun
```

`PlannedVerifiedRun` contains exactly a `QueryPlan`, `RetrievalDiagnostics`,
and the existing `VerifiedRun`. `PipelineResult` and `VerifiedRun` serialization
are unchanged.

## Frozen contract

The first M2 build gate is held in:

- `data/synthetic/m2/evaluation_cases.json`
- `data/synthetic/m2/aliases.json`
- `tests/test_m2_contract.py`

The contract contains exactly `M2-013` through `M2-020`. Alias changes are
version-controlled and limited to `DECLARED_TYPO`, `DECLARED_SYNONYM`, and
`DECLARED_ACRONYM`. Generic fuzzy correction is not allowed.

## Retrieval behavior

The planner detects one of six closed-world intents, optionally decomposes an
explicit conjunction into at most three subqueries, and short-circuits to
`CLARIFY` when required context is missing. Retrieval uses four deterministic
channels:

```text
EXACT       2.00
TABLE_ROW   1.25
WORD_TFIDF  1.00
CHAR_TFIDF  0.75
```

Final fusion is weighted reciprocal rank fusion:

```text
score(candidate) = sum(channel_weight / (60 + channel_rank))
```

Table rows are indexed with page title, section heading, caption/headers, and
row values. Explicit scope conflicts are excluded before final fusion, and
provenance-reference ascending is the tie-breaker.

## Evaluation and artifacts

Run:

```bash
uv run riskon evaluate --config config/milestone2.toml
```

The command runs the five M0 cases, seven M1-new cases, and eight M2-new cases.
It writes:

- `data/generated/m2/evaluation.json`
- `data/generated/m2/evaluation.md`
- `data/generated/m2/retrieval_diagnostics.jsonl`
- `data/generated/m2/audit.jsonl`

The required acceptance metrics are defined in `src/riskon/evaluation.py` and
the canonical success line is:

```text
M2 PASS: aggregate 20/20; M0 5/5; M1-new 7/7; M2-new 8/8; query plans 8/8; evidence recall@5 1.000; context violations 0; network disabled.
```

The 26 August Q&A is non-blocking for M2. Event-day PDFs, MP4s, XLSX files,
real bank content, external APIs, models, OCR, image interpretation, UI,
HTTP, deployment, retention, and access-control decisions are outside this
milestone.
