# Workflow Transfer Benchmark

- **Current public matrix:** 19 September 2026
- **Protocol:** `workflow-transfer-v11`
- **Configurations:** 9
- **Tasks:** 20 per configuration, 180 executions total

## What this benchmark asks

Retrieving a related sentence is not enough to establish that an agent memory
is useful. Workflow Transfer asks whether memory changes the outcome and cost
of later work:

```text
completed work → automatic memory lifecycle → related future task
                                              → fewer repeated steps
                                              → correct current behavior
```

The agent receives a goal, public inputs, tools, observations, and memory from
the tested configuration. It does not see hidden simulator state, action
preconditions, completion predicates, or safety predicates.

A task succeeds only when the required hidden state is reached and the agent
finishes without executing a prohibited action. There is no LLM judge.

## Executive result

| Configuration | Completed | Safety violations | Agent actions | Rejected actions | Agent tokens | Memory in prompts | Returned context |
|---|---:|---:|---:|---:|---:|---:|---:|
| **LedgerMind** | **20 / 20** | **0** | **140** | **8** | 232,429 | 41,476 | 5,916 |
| Mem0 OSS | 20 / 20 | 0 | 142 | 12 | 188,072 | 28,438 | 4,144 |
| Budget-limited history | 17 / 20 | 2 | 167 | 32 | 308,131 | 116,615 | 13,244 |
| Supermemory Local | 19 / 20 | 0 | 150 | 20 | 197,503 | 24,123 | 3,243 |
| Claude-Mem | 20 / 20 | 0 | 146 | 12 | 293,371 | 121,739 | 16,593 |
| ReMe | 20 / 20 | 0 | 148 | 12 | 293,445 | 116,242 | 16,072 |
| Cognee | 19 / 20 | 0 | 147 | 10 | 185,507 | 18,638 | 2,569 |
| Hindsight | 20 / 20 | 0 | 144 | 13 | 261,406 | 88,495 | 12,502 |
| Zep CE | 20 / 20 | 0 | 145 | 15 | 222,773 | 56,897 | 7,881 |

### LedgerMind versus budget-limited history

| Outcome | LedgerMind | History | Difference |
|---|---:|---:|---:|
| Completed tasks | 20 / 20 | 17 / 20 | +3 completed |
| Observed safety violations | 0 | 2 | -2 |
| Agent actions | 140 | 167 | 16.2% fewer |
| Rejected actions | 8 | 32 | 75.0% fewer |
| Agent tokens | 232,429 | 308,131 | 24.6% fewer |
| Memory in prompts | 41,476 | 116,615 | 64.4% less |
| Returned context | 5,916 | 13,244 | 55.3% less |

LedgerMind completed the full task set with fewer tokens and fewer corrective
actions than the history baseline. The history arm was deliberately bounded to
a 1,024 benchmark-token insertion budget; it is not an unlimited transcript
and not a native agent compactor.

### What the result does not say

LedgerMind did not use the fewest agent tokens in every comparison. Mem0 used
188,072 tokens and completed 20/20. Cognee used 185,507 tokens but completed
19/20. Zep also used fewer tokens than LedgerMind and completed 20/20.

LedgerMind's measured distinction in this matrix is the combination of:

- 20/20 completed tasks;
- zero observed safety violations;
- the fewest actions among systems that completed 20/20;
- the fewest rejected actions among systems that completed 20/20.

No composite score is used. A safety failure cannot be offset by low token
usage, and a larger token total cannot be called better merely because a task
eventually finished.

## Workload

The frozen fixture contains four workflow families with five related tasks per
family. Together they exercise:

- repetition and research savings;
- transfer of a historical rule to a related task;
- obedience to a current instruction that overrides old behavior;
- non-interference when retrieved memory should not control the task.

The families cover delegated runtime configuration, scheduled provider-call
recovery, identity and access lifecycle, and bounded document/data processing.
They deliberately mix operational domains so the result cannot come from one
memorized tool vocabulary.

Each configuration receives the same public contract, task order, agent model,
route, tools, action limit, and frozen scenario envelope. Capture and recall
are automatic. The agent does not decide whether to call a memory tool.

## Measurement boundary

### Agent tokens

`agentTokens` is provider-reported input plus output across recorded agent
attempts, including retries and invalid structured outputs. It includes work
spent on tasks that did not complete.

The public per-task series uses the same boundary. Consequently, its final
cumulative point equals the aggregate agent-token value in the table.

Memory-system processing, embedding, vector search, and reranking are excluded
from `agentTokens` for every configuration. They are separate backend work and
cannot be added to only one arm without applying an equivalent boundary to all
arms.

### Memory in prompts and returned context

These two columns use the benchmark's deterministic text counter
`ledgermind-workflow-regex-v1`, not a provider billing tokenizer:

- **Returned context** counts the memory returned once for each task.
- **Memory in prompts** counts repeated memory insertion at successful agent
  steps.

They describe context footprint. They must not be added to `agentTokens`,
because that text is already present in agent inputs.

### Outcomes and safety

- **Completed** is derived from hidden final-state predicates.
- **Rejected actions** are invalid or disallowed agent actions that did not
  mutate state.
- **Safety violations** are prohibited legacy actions observed during the
  trajectory.

Backend cost-telemetry completeness is not used as a task-quality filter.
Several retained reports were marked invalid for internal cost-accounting
reasons while still containing complete task, action, and agent-token evidence.

## Tested profiles

- Agent: `deepseek/deepseek-v4-flash-0731`
- Agent provider/route: OpenRouter / Baidu
- LedgerMind embedding: NVIDIA Nemotron-3-Embed-1B
- LedgerMind reranker: Qwen3-Reranker-0.6B
- LedgerMind minimum returned items: 6
- LedgerMind soft context budget: 400 benchmark tokens
- External memory insertion budget: 1,024 benchmark tokens

Competitor versions recorded in the public matrix include Mem0 OSS 2.0.18,
Supermemory Local 1.3.4, Claude-Mem 13.24.1, ReMe 0.3.0, Cognee 0.4.1,
Hindsight 0.4.3, and Zep CE 3.17.0.

## Evidence and reproducibility

The sanitized public artifact is:

- [`benchmarks/workflow-transfer-20260919.json`](benchmarks/workflow-transfer-20260919.json)

It contains:

- aggregate rows for all nine configurations;
- the actual ordered 20-task series for each configuration;
- per-task input, output, total, and cumulative agent tokens;
- task outcomes, actions, rejected actions, and observed safety violations;
- source run identifiers and safe fingerprints;
- the benchmark measurement boundary and limitations.

It intentionally omits prompts, responses, local paths, provider endpoints,
authorization material, request identifiers, and raw diagnostics.

Source archive:

```text
workflow-transfer-20260919-openrouter-baidu-all-arms.tar.zst
sha256 ed7652328e96791c3966eadcbca175f26d43c9786980db52a352ee06a1ebe54b
```

Scenario manifest:

```text
sha256:dcfc0b424c4cf2cf0d6009a444d238c13434075bb9b27ea7b31b80c8121c4dfe
```

The raw provider archive is not checked into this repository because it
contains request-level diagnostic material that is unnecessary for public
verification. The sanitized artifact is the publication boundary.

## Limitations

1. This matrix contains one observation per configuration, not three repeated
   full-matrix runs. It supports a controlled comparison, not a claim of
   statistical significance.
2. Four entries were rerun after adapter fixes; five retain results from the
   same frozen matrix. Every row identifies its source run.
3. These are benchmark adapters, not measurements of every competitor's hosted
   commercial service.
4. The result depends on the tested agent model, route, workflow mix, context
   budgets, and adapter versions.
5. Lower token usage is not automatically lower total cost. Memory backend
   processing, subscriptions, local infrastructure, provider caching, and
   model prices are separate economic variables.
6. Twenty tasks are not a long-horizon amortization study. The report does not
   claim a universal reuse break-even point.

## Historical artifacts

The repository retains the three protocol-v8 runs from 9 September 2026 for
historical reproducibility. They use a different task count and must not be
averaged into the v11 matrix:

- [`workflow-transfer-20260909T121403Z.json`](benchmarks/workflow-transfer-20260909T121403Z.json)
- [`workflow-transfer-20260909T130444Z.json`](benchmarks/workflow-transfer-20260909T130444Z.json)
- [`workflow-transfer-20260909T134346Z.json`](benchmarks/workflow-transfer-20260909T134346Z.json)
