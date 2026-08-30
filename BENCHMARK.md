# Workflow Transfer Benchmark

## What the benchmark measures

LedgerMind is intended to make completed work useful on the next similar task.
The Workflow Transfer Benchmark therefore measures a product outcome rather
than the wording of a stored memory:

```text
source experience → memory formation → new workflow → recall → agent actions
```

An arm succeeds only when the agent calls `finish`, the hidden workflow state
satisfies every completion condition, and no safety violation occurred.
There is no model-based semantic judge and no hand-written answer oracle for
the memory itself.

## Development result

The machine-readable, sanitized aggregate is available at
[`benchmarks/workflow-transfer-20260829T194140Z.json`](benchmarks/workflow-transfer-20260829T194140Z.json).
It contains the published metrics, run identity, manual audit result, and known
limitations without local filesystem paths, credentials, raw conversations, or
private Core artifacts.

The comparison run completed 36 trajectories: 12 transfer workflows in each of
three memory modes.

| Metric | LedgerMind | Mem0 OSS | Raw history |
|---|---:|---:|---:|
| Successful workflows | **12 / 12** | 12 / 12 | 12 / 12 |
| Finished workflows | **12 / 12** | 12 / 12 | 12 / 12 |
| Safety violations | **0** | 0 | 0 |
| Agent actions | **76** | 76 | 76 |
| Agent input tokens | **89,710** | 97,780 | 166,195 |
| Agent output tokens | **6,862** | 6,954 | 7,015 |
| Total agent execution tokens | **96,572** | 104,734 | 173,210 |
| Memory injected across agent prompts | **5,945** | 15,690 | 82,265 |
| Context returned at recall | **1,289** | 2,701 | 14,957 |
| Initial memory formation tokens | **28,446** | 56,313 | Not applicable |
| Online memory update tokens | 173,229 | **138,701** | Not applicable |
| Final authoritative changes retained | **4 / 4** | 1 / 4 | Not applicable |

### Agent-facing efficiency

Against raw history, LedgerMind used:

- 76,638 fewer agent execution tokens (**44.2% less**);
- 76,320 fewer injected memory tokens (**92.8% less**);
- 13,668 fewer returned context tokens (**91.4% less**).

Against Mem0 OSS, LedgerMind used:

- 8,162 fewer agent execution tokens (**7.8% less**);
- 9,745 fewer injected memory tokens (**62.1% less**);
- 1,412 fewer returned context tokens (**52.3% less**);
- 27,867 fewer tokens for initial memory formation (**49.5% less**).

All three arms produced almost the same number of output tokens and performed
exactly 76 actions. The measured advantage came from reducing agent input, not
from truncating the answer, skipping steps, or lowering the success bar.

### Cumulative agent tokens

| After transfer | LedgerMind | Mem0 OSS | Raw history |
|---|---:|---:|---:|
| T1 across four families | **27,493** | 30,470 | 44,584 |
| T2 across four families | **59,059** | 64,702 | 105,431 |
| T3 across four families | **96,572** | 104,734 | 173,210 |

The context advantage persisted as each memory accumulated more experience.

## Knowledge quality after the final update

Backend processing tokens cannot be interpreted without examining what the
backend produced. LedgerMind spent 173,229 tokens on online memory updates,
while Mem0 spent 138,701. Those numbers look worse for LedgerMind only if the
resulting memories are assumed to be equivalent. They were not.

A manual post-run inspection checked whether each memory contained the final
authoritative T3 change for its workflow family:

| Workflow family | Final authoritative change | LedgerMind | Mem0 OSS |
|---|---|---:|---:|
| Production rollout | Immutable snapshot replaces legacy backup; CAB remains mandatory | **Retained** | Missing |
| Incident recovery | Forensic snapshot is mandatory before failover | **Retained** | Missing |
| Secure offboarding | Legal hold replaces wiping with archival | **Retained** | Retained |
| Business-data processing | Preserve `legacy_id`; destructive deduplication is prohibited | **Retained** | Missing |

LedgerMind retained **4 of 4** authoritative changes. Mem0 retained **1 of 4**.
Raw history is not scored here because it preserves trajectories rather than
forming consolidated knowledge.

This manual audit is intentionally reported separately from the simulator's
task-success gate. It is not a deterministic semantic oracle. Its purpose is
to prevent a misleading conclusion from backend token totals: a system that
does less post-processing but misses three authoritative updates has not
produced the same memory more cheaply.

## Benchmark design

### Workflow families

The pilot uses four kinds of operational work:

1. production configuration rollout;
2. incident diagnosis and recovery;
3. user offboarding and equipment release;
4. business-data cleanup and publication.

Each family starts with the same successful source experience for every arm.
That experience contains useful actions, irrelevant investigation, and a
corrected mistake. Three transfer tasks then test progressively harder reuse:

- **T1 — repetition:** the same process with different entities;
- **T2 — adaptation:** a changed environment with the same underlying
  principle;
- **T3 — revision:** a conflicting or authoritative new rule that makes
  literal reuse unsafe.

### Compared memory modes

- **Raw history** supplies the source and accumulated workflow transcripts.
- **Mem0 OSS** uses `mem0ai==2.0.18` with isolated local Qdrant and SQLite
  storage, without graph memory, a reranker, custom instructions, or the cloud
  API.
- **LedgerMind** forms and recalls knowledge through its public runtime
  boundaries.

The full comparison intentionally omitted the no-memory arm after scenario
calibration; repeating it would add provider cost without contributing to the
memory-to-memory comparison.

### Controls

The run enforced:

- identical source digests across all arms;
- one agent model and route for every trajectory;
- the same public goal, tools, observations, prompts, and action limit;
- the same generation identity for LedgerMind and Mem0;
- the same embedding identity for LedgerMind and Mem0;
- isolated online memory for every family and arm;
- hidden simulator state, preconditions, effects, completion predicates, and
  safety predicates;
- provider-reported token telemetry.

The tasks were executed sequentially inside each family. After every completed
task, each online memory backend received its own actual trajectory, including
errors and the final outcome.

## Metric definitions

- **Agent execution tokens** are provider-reported input and output tokens for
  the agent performing transfer tasks.
- **Memory injection tokens** count memory text appearing in agent prompts,
  including the retained working set on later action calls.
- **Returned context** is the memory content produced by the initial recall for
  each task.
- **Initial memory formation tokens** are the one-time backend tokens required
  to process the four shared source experiences.
- **Online memory update tokens** are backend tokens used to process the 12
  completed transfer trajectories. They are reported separately from agent
  execution and are not treated as user-visible prompt savings.
- **Authoritative changes retained** is a manual inspection of the final memory
  state, not part of the deterministic success gate.

## Run identity

- Run: `workflow-transfer-20260829T194140Z`
- Created: `2026-08-29T20:07:50Z`
- Manifest digest:
  `sha256:ad87ded5fb8bb672c4041a6ed87f3228e585b88e92b28651c9d16d5038ffae0f`
- Memory snapshot: `3d3be41c0617bf6d78b1ea5e`
- Agent and generation model: `deepseek/deepseek-v4-flash-0731`
- Provider and route: OpenRouter, `baidu/fp8`
- Embeddings: `nvidia/nemotron-3-embed-1b-local-bf16`, 2,048 dimensions
- Mem0: `mem0ai==2.0.18`
- Successful task calls had complete provider token telemetry.

## Limitations

This is a development benchmark, not an independent third-party result.

- It is one run and does not support statistical claims about stability.
- The four workflow families are synthetic, deterministic simulations of
  operational work.
- The run used development worktrees with uncommitted changes, so it is not yet
  a release-grade reproducibility artifact.
- The upstream Baidu pool returned 50 transient HTTP 429 responses. Retry
  accounting is preserved in the artifact; all scored workflows completed.
- One LedgerMind online update reported an embedding-queue error after the
  scored WT01-T3 task. The Unicode length mismatch was fixed afterward, and a
  targeted recovery processed all 9 queued embeddings and returned the current
  procedure and constraint. A complete comparison rerun on the patched release
  binary is still required before treating these numbers as final release
  claims.
- The 4/4 versus 1/4 knowledge result is a manual semantic audit and should be
  independently reviewed or replaced by repeated downstream transfer tests.

The current numbers are best read as evidence that the product hypothesis is
working: LedgerMind can deliver a much smaller agent context while retaining
authoritative workflow changes that a flatter memory process may miss.
