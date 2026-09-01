# 26 August Q&A — open items

These are carried forward in the same priority and order as the preparation
list. All remain `OPEN` until answered by the organisers.

M1, M2, and the current M3 routing evaluation proceed independently of these
answers using synthetic data only. The answers remain gates for later cloud,
event-data ingestion, real expert routing, deployment, and real-data
persistence milestones. M2/M3 make no assumptions about the event HTML
adapter, external API permission, hidden evaluation, jury weights, or final
UI/API deliverable.

## 1. P0 — Exact event-day data package

**Question:** Could you please specify the exact event-day data package: the approximate number and size of HTML files, the Excel schema, text encoding, folder structure, and whether all embedded images, icons, CSS files, tables, downloadable attachments and locally resolvable links will be included? Should we expect any missing assets or broken links?

**Decision impact:** Determines ingestion, asset handling, and whether multimodal parsing is possible.

**Status:** OPEN  
**Answer:** null

## 2. P0 — External OpenAI/Gemini API use

**Question:** Are we explicitly permitted to send any part of the event-day data—including user questions, retrieved passages, embeddings, images or model logs—to external APIs such as OpenAI or Gemini? If yes, under which approved accounts, contractual/privacy conditions, retention settings and redaction rules?

**Decision impact:** Determines model, embedding, image, observability, and logging architecture.

**Status:** OPEN  
**Answer:** null

## 3. P0 — Internet and outbound API access

**Question:** Will outbound internet and external API access be available and reliable throughout both challenge days? Should teams assume any blocked domains, rate limits, credential restrictions, proxy requirements or temporary network outages?

**Decision impact:** Determines cloud use and offline fallback planning.

**Status:** OPEN  
**Answer:** null

## 4. P0 — Structured evaluation context

**Question:** Will evaluation queries be plain natural-language text only, or will they be accompanied by structured context such as the user’s role, advisory location, booking centre, client domicile and classification, service model, solicitation type, workflow stage and system? If the context is absent, is the assistant expected to ask for it interactively?

**Decision impact:** Determines extraction versus structured-input versus clarification behavior.

**Status:** OPEN  
**Answer:** null

## 5. P0 — Jury metrics and weights

**Question:** Could you share the jury rubric and the weighting across factual correctness, completeness, evidence and citation quality, clarification quality, abstention, expert routing, multimodal extraction, explainability, novelty, latency and user experience?

**Decision impact:** Determines the two-day prioritisation across retrieval, routing, UI, and multimodal work.

**Status:** OPEN  
**Answer:** null

## 6. P0 — Hidden evaluation and clarification scoring

**Question:** Will there be a hidden evaluation set? For ambiguous or insufficiently supported questions, how will the system be scored if it asks a clarification, abstains immediately, or routes to an expert? Is unnecessary escalation penalised, and how many clarification turns are allowed?

**Decision impact:** Determines decision thresholds, conversation flow, and selective-QA metrics.

**Status:** OPEN  
**Answer:** null

## 7. P0 — Expert-routing evaluation

**Question:** How will expert routing be evaluated: against a labelled support function, a named individual SME, a ranked top-k list, or the quality of the routing explanation? Is routing to a functional queue acceptable when person-level confidence is low?

**Decision impact:** Determines the expert data model and routing ground truth.

**Status:** OPEN  
**Answer:** null

## 8. P0 — Final deliverable and demo limits

**Question:** What is the minimum expected final deliverable: a live working demo, a user interface, a documented REST or gRPC API, a source repository, an architecture proposal, or a combination? What are the exact pitch, live-demo and Q&A time limits, and are prerecorded demos allowed?

**Decision impact:** Determines integration, presentation, and live-demo scope.

**Status:** OPEN  
**Answer:** null

## 9. P1 — Synthetic expert-data fields and scale

**Question:** What minimum fields and scale do you expect in the synthetic organisation and SME dataset—for example support tier, function, domain, product expertise, jurisdiction, booking centre, system expertise, mandate or approval authority, availability, contact channel, historical response quality and collaboration network?

**Decision impact:** Determines routing demonstrability and data-modelling effort.

**Status:** OPEN  
**Answer:** null

## 10. P0 — API, offline, Kubernetes, and tests

**Question:** Slide 10 says that the technical items will not be part of the evaluation criteria, but several bullets use the word “must”. Are API exposure, offline and local-model fallback, Kubernetes manifests, commercial-use licence checks, automated tests and the coverage target mandatory deliverables, recommended design considerations, or possible tie-breakers?

**Decision impact:** Determines whether time goes to delivery infrastructure or evidence verification.

**Status:** OPEN  
**Answer:** null

## 11. P1 — Source hierarchy and conflicts

**Question:** For evaluation, is the event-day Suitability Wiki extract the only authoritative answer source, or may teams also use and cite the pre-reading One-Pager and Advisory Duties materials? How should we handle duplicated, outdated, conflicting or explicitly scope-limited pages, and are there any source-precedence rules?

**Decision impact:** Determines source ranking and conflict-abstention behavior.

**Status:** OPEN  
**Answer:** null

## 12. P1 — Storage, logging, and deletion

**Question:** What are the rules for storing, logging, sharing and deleting the event data and derived artefacts after the challenge, including local vector indexes, embeddings, prompts, model traces, screenshots, repositories, backups and team collaboration tools?

**Decision impact:** Determines repository, collaboration, audit, and cleanup policy.

**Status:** OPEN  
**Answer:** null
