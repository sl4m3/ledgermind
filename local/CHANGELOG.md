# Changelog

## 4.1.0 - 2026-09-20

- Made the compact Round Semantic schema version 4 the only production semantic
  extraction contract and removed obsolete versions 1 through 3 execution paths from the
  self-hosted runtime.
- Improved retrieval with complete facet passages, exact related-object links,
  related-object scoring, and non-recursive expansion of applicable
  constraints, decisions, and procedures.
- Added hybrid context selection: the first six complete knowledge items are
  retained and additional whole items may be packed up to a 400-token soft
  target without truncating knowledge.
- Added an optional retrieval reranker with three installer modes: disabled,
  provider API, or a separately downloaded local CPU, NVIDIA CUDA, or AMD ROCm
  runtime. Reranker failure remains fail-open to the deterministic Core order.
- Hardened provider telemetry, strict-schema validation and recovery while
  preserving precise terminal failure reasons and existing memory databases.
- Kept the public self-hosted distribution SQLite-only. LedgerMind Cloud and
  PostgreSQL components are not included.

## 4.0.8 - 2026-09-06

- Replaced parallel user and execution claim sections with one coherent
  completed-round semantic result while preserving user-only, execution-only,
  and mixed provenance for every claim.
- Raised the generation input ceiling to 64,000 tokens and retained complete
  evidence records when bounding large rounds.
- Added automatic, scoped recovery for safe pre-materialization failures after
  the exact provider profile has passed strict-JSON capability verification.
- Preserved verified provider capabilities across time; profile fingerprint
  changes and explicit failed probes still invalidate them.
- Replaced generic Core rejection diagnostics with bounded, content-free reason
  codes for semantic contracts, references, provenance, and result validation.
- Made runtime activity diagnostics non-blocking while Core is busy, retained a
  stale last-known backlog for observability, and kept idle shutdown fail-closed.
- Cleared the reusable bundle extraction directory before every signed update,
  preventing removed Python files from an older release from shadowing the new
  runtime.
- Kept the public self-hosted distribution SQLite-only. LedgerMind Cloud and
  PostgreSQL components are not included.

## 4.0.7 - 2026-09-04

- Updated the bundled Core contract for explicit Round Semantic extraction or
  abstention outcomes, avoiding unnecessary provider retries for deliberate
  empty results.
- Added compatibility with the shared Object Resolution candidate pool while
  preserving existing configurations, hooks, provider profiles, and memory.
- Kept the public self-hosted package SQLite-only; cloud PostgreSQL components
  are not distributed.

## 4.0.6 - 2026-09-04

- Shipped the single-pass Round Semantic pipeline while preserving distinct
  user and execution provenance throughout staging and durable knowledge.
- Updated SQLite Core to the current schema revision with separately persisted
  technical anchors and symmetric Object Resolution candidate embeddings.
  Existing knowledge and integration configuration are preserved during an
  in-place upgrade.
- Removed legacy object aliases from operational identity matching and fixed
  stale candidate-passage handling before Object Resolution.
- Kept the public self-hosted distribution SQLite-only. LedgerMind Cloud and
  its PostgreSQL runtime are not included in this package.

## 4.0.5 - 2026-09-04

- Raised the operational round-semantic output budget from 3072 to 6144 tokens
  so rich rounds are no longer cut off mid-answer; token-limit truncation is
  reported under its own `length_truncation` code instead of a generic provider
  error, and the failing class is covered by contract and provider tests.
- Covered silent provider-response loss in the OpenAI-compatible path: missing
  choices, non-JSON bodies, and truncated bodies are distinguished in
  telemetry and mapped into the retryable/permanent failure classes.
- Shipped the Cursor lifecycle wiring alongside the existing agent adapters
  (hooks, memory space, profile bindings are verified on connect).

## 4.0.4 - 2026-09-02

- Made one accepted Object Resolution call final and normalized overlapping
  model components deterministically, eliminating redundant identity review
  calls without moving semantic identity decisions into Core.
- Improved semantic card identity by preserving independent subject boundaries
  and stable distinguishing descriptions across User and Execution Semantic.
- Preserved the 120-character generation guidance for technical anchors while
  accepting longer non-empty paths and identifiers returned by a provider.
- Simplified Object Resolution to the current name, stable description, and
  Core-owned Target, preventing claims and historical facets from influencing
  object identity while preserving durable-card reconciliation.
- Made Knowledge Resolution copy a selected incoming claim verbatim for
  `replace`; only `merge` may generate combined content, and Core continues to
  own exact same-object, same-Target, same-facet conflict groups.
- Rebuilt stale object signatures and identity embeddings before candidate
  retrieval so recently changed cards remain discoverable without creating
  semantic duplicates.
- Added bounded, cursor-based knowledge export pages and explicit diagnostics
  for malformed cursors, changed snapshots, oversized items, and IPC frames.
- Made the authenticated HTTP plane available after the secure Core handshake
  while slow maintenance finishes, avoiding cold-start recall timeouts without
  weakening readiness or isolation checks.
- Cleared stale integration network diagnostics after a successful recall.

## 4.0.3 - 2026-09-01

- Made Knowledge Resolution operate only on Core-owned conflict groups and
  return one final `merge` or `replace` decision for every group.
- Added deterministic handling for non-conflicting facets and replacement
  precedence when a group contains both merge and replace evidence.
- Added one bounded empty-result recheck on the configured fallback provider;
  invalid structured output still fails closed after the bounded recovery path.
- Hardened large-round normalization, patch/tool evidence projection, object
  candidate resolution, retrieval text, and embedding persistence sequencing.
- Kept the public Local distribution on the SQLite storage adapter. The private
  LedgerMind Cloud PostgreSQL runtime is not included in this package.

## 4.0.2 - 2026-09-01

- Rejected provider responses that are valid JSON but do not satisfy the
  requested strict JSON Schema before they can reach Core.
- Added one bounded retry for that failure class. When an ordered OpenRouter
  provider chain is configured, the retry keeps the same model, prompt, and
  schema while selecting the next configured route.
- Kept recovery fail-closed: Local does not repair JSON, infer missing fields,
  alter semantic content, or retry more than once.
- Added regression coverage for local schema validation, route fallback, and
  terminal failure when both configured routes return invalid structures.

## 4.0.1 - 2026-08-31

- Preserved large agent sessions as one semantic trajectory while compacting
  oversized tool payloads before delivery to Core.
- Prevented runtime shutdown while accepted Local or Core work remains active,
  and aligned hook and transport timeouts with long-running agent turns.
- Made warning and informational integrity findings visible without blocking
  secure startup; error-severity findings continue to fail closed.
- Improved object consolidation, knowledge conflict routing, structured-output
  recovery, and embedding persistence without weakening provenance checks.

## 4.0.0 - 2026-08-31

- Promoted the verified Linux memory pipeline to the first stable 4.0 release.
- Includes transactional configuration, bounded recovery, provider retry
  classification, quiescence-aware lifecycle management, and authenticated
  memory-health diagnostics validated throughout the 4.0 beta cycle.

## 4.0.0b5 - 2026-08-31

- Classified embedding timeouts, transport failures, HTTP 429 responses, and
  transient HTTP 5xx responses as retryable provider failures so one temporary
  outage no longer terminates the affected memory pipeline.
- Preserved permanent handling for authentication, invalid request, response
  shape, model identity, and embedding dimension failures.

## 4.0.0b4 - 2026-08-31

- Made the runtime file secret store the single provider-credential source of
  truth and prevented signed updates from rewriting installed credentials.
- Made provider reconfiguration transactional across config, secrets, Local
  profiles, and their SQLite state.
- Added read-only memory-pipeline health diagnostics and an authenticated,
  bounded replay endpoint for normalization rejects and pre-materialization
  User Semantic failures.

## 4.0.0b3 - 2026-08-31

- Prevented idle shutdown while Local-to-Core delivery, semantic processing,
  object/knowledge resolution, or embedding work remains queued or leased.
- Started the idle grace period only after the durable Local and Core queues
  become fully quiescent, regardless of how long the agent or provider takes.
- Made unknown activity fail closed so a temporary Core/status failure cannot
  discard accepted work, and rechecked work and leases immediately before stop.
- Added an authenticated, content-free runtime activity endpoint and exposed
  its state through runtime status for lifecycle diagnostics.

## 4.0.0b2 - 2026-08-31

- Added a detached idle watcher so Core and Local stop after the configured
  grace period when the final agent lease is released or expires.
- Cancelled and re-armed idle shutdown when another agent acquires a lease.
- Preserved explicit `--home` roots in the watcher for isolated and rootless
  installations.

## 4.0.0b1 - 2026-08-30

- Made repeated installation explicit and non-destructive: users choose to add
  agents, repair the current installation, or reconfigure provider profiles.
  Adding an agent cannot rewrite inference or memory configuration.
- Made signed updates reuse the installed provider identities, credentials,
  memory topology, storage, and agent selection instead of reopening setup.
- Made ordinary uninstall stop the runtime and create a private memory backup
  while preserving knowledge and configuration; destructive purge still
  requires explicit purge flags and confirmation.
- Added actionable terminal summaries for install, provider reconfiguration,
  repair, removal, and integration lifecycle operations.
- Added explicit OpenRouter provider-route selection after model selection:
  one required primary provider and at most one optional fallback, with no
  implicit provider default. Routes remain part of every generation profile
  fingerprint and provider probe.
- Kept agent integration lifecycle operations isolated from inference
  configuration so connecting or toggling an agent cannot rewrite provider
  routes or invalidate verified capabilities.
- Persisted successful installer strict-JSON probes into Local's capability
  cache so the first semantic task uses the exact provider/model/route that
  passed preflight instead of failing before the provider call.
- Made validated reconfiguration rematerialize Local profiles and
  refresh their capability rows instead of updating only the installer JSON.
- Replaced the plain prompt chain with a guided terminal setup, OpenRouter
  reference defaults, consolidated agent selection, endpoint normalization,
  fail-fast provider checks, and actionable embedding probe diagnostics.
- Prevented false generation-probe failures when a reasoning model consumed
  the previous 32-token capability-check budget before emitting strict JSON.
- Accepted OpenRouter's canonical embedding model response when a request uses
  the `:free` routing suffix or its response uses the known
  `private/openrouter/` namespace, while retaining strict mismatch detection.
- Created and preserved the Local API bearer token during installation, added
  authenticated runtime ownership checks, and rejected stale process state.
- Bundled the pinned CPython 3.12 runtime with Local instead of relying on an
  ABI-compatible system `python3`.
- Made secure Bubblewrap isolation enter an unprivileged user namespace before
  creating its network namespace, including on hosts that forbid direct
  unprivileged network namespace creation.
- Prevented API embedding profiles from spawning a local embedding service and
  preserved all managed process records across nested runtime supervisors.
- Documented Local/Core and Local/provider trust boundaries, split capture/full
  readiness, and the sensitivity of backup archives.
- Added release-content assertions for the Local wheel's runtime data and
  generated-artifact/secrets exclusions.
