# Benchmark artifacts

The current analysis and measurement boundary are documented in
[`BENCHMARK.md`](../BENCHMARK.md).

## Current public matrix

- [Workflow Transfer v11 — 19 September 2026](workflow-transfer-20260919.json)

This sanitized artifact contains aggregate results for nine configurations and
the actual ordered 20-task series used by the public comparison. It includes
per-task agent-token totals and outcomes, but excludes prompts, responses,
provider endpoints, request identifiers, credentials, and local paths.

The final cumulative token value for every configuration is validated against
its published aggregate before release.

## Historical series

These three files are preserved protocol-v8 runs from 9 September 2026. They
use 12 tasks per arm and belong to a different benchmark protocol. They are not
combined with the current v11 matrix.

- [Run 1 — workflow-transfer-20260909T121403Z](workflow-transfer-20260909T121403Z.json)
- [Run 2 — workflow-transfer-20260909T130444Z](workflow-transfer-20260909T130444Z.json)
- [Run 3 — workflow-transfer-20260909T134346Z](workflow-transfer-20260909T134346Z.json)
