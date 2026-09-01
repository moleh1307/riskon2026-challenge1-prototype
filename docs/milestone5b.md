# M5B — Governed Knowledge Overlay

M5B is the final architecture milestone for the RiskON Challenge 1
prototype. It turns a structured expert resolution into a retrievable
knowledge change only through a governed sequence:

```text
ExpertResolution + KnowledgePatch
  → Policy CI (11 mandatory checks)
  → independent HumanApproval
  → explicit KnowledgeRelease activation
  → active/current KnowledgeOverlaySnapshot
```

`APPROVED` is not `ACTIVE`. Automatic approval, automatic activation, agent
approval, and self-approval are disabled. The official M4D corpus is immutable;
the overlay is a separate versioned evidence namespace:

```text
Official Knowledge Corpus (read-only)
+ Approved Knowledge Overlay (versioned, local-only)
```

## Acceptance matrix

| Case | Result |
| --- | --- |
| `M5A-046` | Policy CI and four scope transitions pass; independent approval and `KB-SYN-V2` activation produce one active patch. |
| `M5A-047` | Automated checks pass, but the patch remains `AWAITING_APPROVAL` and is not retrievable. |
| `M5A-048` | Contradiction and critical-control checks fail; the patch is rejected and approval cannot override the failure. |
| `M5A-049` | Scope containment and counterfactual checks fail; the overbroad patch is rejected. |
| `M5A-050` | The expired patch is excluded from the overlay and cannot answer the query. |

The overlay provenance form is:

```text
local://knowledge-overlay/<release-id>/<patch-id>#claim-<claim-id>
```

Overlay units preserve their original backing evidence references, carry
explicit scope and effective periods, receive no ranking boost, and are
excluded when rejected, awaiting approval, superseded, future, or expired.
An expert resolution, approval record, or governance event is not evidence.
Official/overlay conflicts fail closed.

## Runtime and artifacts

```bash
uv run riskon evaluate --config config/milestone5b.toml
```

The evaluator reuses the frozen M5A cases and runs the frozen M0–M4D
regression gate in process. It writes the following under
`data/generated/m5b/`:

- `evaluation.json` and `evaluation.md`
- `policy_ci_reports.jsonl`
- `governance_events.jsonl`
- `knowledge_releases.jsonl`
- `overlay_snapshot.json`
- `audit.jsonl`

M5B does not train or fine-tune a model from expert conversations. It uses no
LLM, external API, telemetry, cloud service, event-day corpus, or network
runtime. After M5B, the remaining work is the event corpus adapter, a thin
demo/dashboard, and the pitch/backup demo; there is no M6 milestone.
