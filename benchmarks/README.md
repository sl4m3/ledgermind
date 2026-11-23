# Benchmark artifacts

The current analysis and measurement boundary are documented in
[`BENCHMARK.md`](../BENCHMARK.md).

## Current suite

### Memory Lifecycle Benchmark — 2026-11-22

- [Suite directory](memory-lifecycle-2026-11-22/README.md)

Twelve scenarios, 24 probes and 73 checked fields across nine arms, scored by a
completed manual semantic review and a separate literal check. The directory
holds the per-probe rubric, the recorded answers with verdicts, aggregate
token/cost figures, nine run manifests, sha256 digests of the original
artifacts, and an offline `verify.py`.

The raw corpus and run config are private because the scenarios come from real
sessions; their authoritative sha256 pins are published in `hashes.sha256` and
`summary.json`.

## Historical suites

These files are preserved for provenance. They use different protocols, task
sets and scoring, and are not combined with the current suite.

### Workflow Transfer v11 — 19 September 2026

- [workflow-transfer-20260919.json](workflow-transfer-20260919.json)

A sanitized aggregate for nine configurations over 20 ordered tasks. It includes
per-task agent-token totals and outcomes, but excludes prompts, responses,
provider endpoints, request identifiers, credentials, and local paths.

### Workflow Transfer protocol v8 — 9 September 2026

Three preserved protocol-v8 runs with 12 tasks per arm. They belong to a
different benchmark protocol and are not part of the current matrix.

- [Run 1 — workflow-transfer-20260909T121403Z](workflow-transfer-20260909T121403Z.json)
- [Run 2 — workflow-transfer-20260909T130444Z](workflow-transfer-20260909T130444Z.json)
- [Run 3 — workflow-transfer-20260909T134346Z](workflow-transfer-20260909T134346Z.json)
