# M5A — Governed Evolution and Policy CI Contract

M5A freezes the governance boundary for learning from an abstained case. The
system may propose a versioned knowledge change from a synthetic expert
resolution, test that proposal, and queue it for a human decision. It must not
turn an expert answer into authoritative knowledge by itself.

```
An expert resolution is evidence for a proposed change,
not an automatic change to authoritative knowledge.

No agent may approve or activate its own knowledge.
```

## Why M5 exists

The challenge rewards a feedback loop and knowledge-base enrichment, while the
core safety contract requires official-source grounding, abstention under
uncertainty, correct escalation, and an audit trail. M5 treats learning as a
governed change process rather than uncontrolled memory:

```text
CaseCapsule
  → ExpertResolution (CANDIDATE_RESOLUTION)
  → KnowledgePatch (PROPOSED)
  → PolicyCIReport
  → HumanApproval
  → KnowledgeRelease
```

An approved overlay is additive and versioned. The official corpus remains
immutable and is never rewritten by a patch.

## Architecture mapping

| Layer | Frozen responsibility | M5A relationship |
| --- | --- | --- |
| M0 | Local deterministic baseline | Supplies the original decision contract. |
| M1 | Evidence and abstention | Keeps an unresolved case at `ABSTAIN`. |
| M2 | Structured retrieval and query planning | Remains the source of baseline evidence. |
| M3 | Functional expert routing | Provides a synthetic route and support function. |
| M4A | Activation profiles and capsules | Supplies the structured `CaseCapsule`. |
| M4B | Bounded workers and objections | Produces diagnostic findings, never approval. |
| M4C | Local counterfactual sentinel | Tests scope containment, never authoritative evidence. |
| M4D | Unified orchestration and safe failure | Remains unchanged by the contract freeze. |
| M5A | Governed evolution contract | Defines proposal, CI, approval, release, and expiry. |

## Lifecycle

The canonical lifecycle is:

```text
PROPOSED → TESTED → AWAITING_APPROVAL → APPROVED → ACTIVE
```

Alternative outcomes are `REJECTED`, `SUPERSEDED`, `EXPIRED`, and
`ROLLED_BACK`. `APPROVED` is not `ACTIVE`: activation requires a separate
explicit `KnowledgeRelease` containing the approved patch. A patch with an
expired effective period is excluded from the active overlay and cannot turn
an abstention into an answer.

The five synthetic cases are:

| Case | Expected governance result |
| --- | --- |
| `M5A-046` | All checks pass, human approval is present, and `KB-SYN-V2` activates the exact scope. |
| `M5A-047` | Automated checks pass but no human approval exists; patch remains `AWAITING_APPROVAL`. |
| `M5A-048` | Critical-control contradiction fails CI and the patch is rejected. |
| `M5A-049` | Patch scope overreach fails containment and counterfactual CI; patch is rejected. |
| `M5A-050` | Previously activated knowledge is expired and excluded from retrieval. |

## Contracts

### Case capsule

Each capsule is the existing structured M4D `CaseCapsule` model. Every M5A
case starts with `baseline_decision = ABSTAIN` and
`verification_status = INSUFFICIENT`. It carries only synthetic routing state,
scope context, reason codes, and local references. It contains no raw query,
private chain-of-thought, document dump, or person contact data.

### Expert resolution

An `ExpertResolution` starts as `CANDIDATE_RESOLUTION`. It records its capsule,
author role, claims, authoritative local references, explicit scope, effective
period, review date, and knowledge owner. Its scope is the maximum scope a
resulting patch may claim. It cannot be retrieved or used as authoritative
knowledge merely because it exists.

### Knowledge patch

The patch supports `ADD`, `UPDATE`, and `DEPRECATE` operations, with
`NORMAL` or `CRITICAL` risk. Its claims and evidence references must be subsets
of the resolution, and its scope must be contained by the resolution. An
`UPDATE` must identify `supersedes_patch_id`; silent overwrites are forbidden.

### Policy CI

Every patch declares the following mandatory checks:

```text
EVIDENCE_COMPLETENESS
CLAIM_SUBSET
SCOPE_CONTAINMENT
CONTRADICTION_DETECTION
CRITICAL_CONTROL_PRESERVATION
REFERENCE_RESOLUTION
M0_M4D_REGRESSION
COUNTERFACTUAL_CONTAINMENT
SEPARATION_OF_DUTIES
HUMAN_APPROVAL_PRESENT
EFFECTIVE_PERIOD_VALID
```

Each result has `check_id`, `status`, `reason_codes`, `evidence_refs`, and
`details`; status is `PASS`, `FAIL`, or `NOT_RUN`. Activation is prohibited if
any mandatory check is `FAIL` or `NOT_RUN`. The frozen regression gate is:

```text
M0-M3 28/28 + M4A 5/5 + M4B 5/5 + M4C 2/2 + M4D 5/5 = 45/45
```

Scope-sensitive proposals require four counterfactual transitions:

```text
exact patch scope       → ANSWER
alternate region        → ABSTAIN
alternate service model → ABSTAIN
required context removed → CLARIFY
```

### Separation of duties and human approval

Only `actor_type = HUMAN_ROLE` can approve. Automatic approval, agent approval,
and activation without approval are forbidden. The resolution author and
approval actor must have different role IDs. Synthetic approval roles are
limited to the role IDs in `approval_policy.json`; no real names, emails, or
phone numbers are used.

No orchestration role has approval authority merely by participating in the
case. This includes the Conductor, workers, router, patch proposer, Policy CI,
and counterfactual sentinel. A human approval cannot override a failed
mandatory Policy CI check.

### Knowledge overlay and release

The future retrieval view is:

```text
Official Knowledge Corpus (immutable)
+ Approved Knowledge Overlay (versioned)
```

Only a patch that is approved, within its effective period, and included in an
active `KnowledgeRelease` may enter the overlay. A patch can belong to only one
active release at a time. A new release supersedes the prior release. Rollback
creates a new release; it does not silently reactivate an old one. The official
corpus version therefore remains unchanged and the overlay version is explicit.

## Privacy and data boundaries

M5A uses synthetic data only and remains local-only. It contains no real Bank
data, employee or expert data, confidential pre-read copy, external API,
telemetry, cloud storage, real approval record, or internal policy change. All
fixture references are local `local://synthetic-m5a/...` references. The
contract changes no existing M0–M4D source or official corpus.

## Explicitly out of scope

M5A does not implement production patch generation, overlay retrieval, a real
expert-resolution form, automatic patch generation, an LLM, a local model, UI,
API, real event data, real approvals, automatic approval, automatic activation,
Knowledge Debt Radar, feedback-based expert scoring, or Policy CI execution.

## Future M5B sequence

After this contract is accepted, the only next architecture implementation is
M5B — Governed Knowledge Overlay, Policy CI Execution & Human-Approved
Activation. M5B may add execution around this frozen contract, but it must keep
the official corpus immutable, require explicit human approval and release
activation, preserve M0–M4D regression gates, and keep expiry/rollback visible.

After M5B, no new architecture milestone is planned before the event. The
remaining work is the real-corpus inspection adapter, a thin demo surface, an
evaluation dashboard, and the pitch/backup demo.
