# Memory Lifecycle Benchmark

- **Suite:** `memory-lifecycle-2026-11-22`
- **Scenarios / probes / fields:** 12 / 24 / 73
- **Arms:** 8, one completed run each
- **Corpus:** `sha256:1fd4d52163294f166fd481569bb6ab3f5654852ad0e3bdace72f74ce6158934f`
- **Run config:** `sha256:645e9b85c1c175c3a16fe45439d2333b55433bf62b0ff22416e8375b51a8cf42`
- **Models:** `meta/muse-ember` for the agent (`reasoning: low`) and memory work (`reasoning: minimal`), route `google-vertex/global`
- **Embedding:** local `nemotron-3-embed-1b-bf16`, 2048 dimensions in the run config; Claude-Mem uses its built-in 384-dimension ONNX model and Supermemory a 2000-dimension Matryoshka slice (see their manifests)

The machine-readable evidence lives in
[`benchmarks/memory-lifecycle-2026-11-22/`](benchmarks/memory-lifecycle-2026-11-22/).

## What this benchmark asks

Retrieving a related sentence is not enough to establish that an agent memory is
useful. This suite asks whether a memory system preserves the *current* state of
real work across a full lifecycle:

```text
real work history → memory formation → online updates (add / replace / merge)
                  → later probe → correct current state, not an old draft
```

Twelve scenarios were built from real project sessions. Each scenario has two or
three stages and two probes drawn from those stages. A probe asks a fresh agent
for a small set of fields using only that arm's memory; the agent must record
every requested field and finish. The agent never sees the expected values, the
forbidden values, the corpus, or the source transcript beyond what the tested
memory mechanism returns.

The families are:

- **E — execution:** completed, failed, and rolled-back work.
- **I — identity:** which component, value, or reference a project name points to.
- **K — knowledge evolution:** superseding and replacing earlier state.
- **R — delivery:** running-session versus next-session applicability and
  procedures with prerequisites.

## Workload

The corpus holds 12 scenarios, 24 probes, and 73 checked fields across 323
source rounds. The same frozen corpus and config were used for every arm; no arm
received the expected answers.

Field values are scored by a **semantic** review of what the recorded answer
means. It was performed over the recorded answers against the typed rubric and
the source history, and confirmed by the project owner. The pipeline's own
`semantic_review_status=pending_manual` in the original `summary.json` only
means the automated pipeline never wrote manual verdicts; the authoritative
verdicts are published in `summary.json` and `evidence.json`.

## Results

| Arm | Version | Semantic (24 / 73) | Agent input tokens | Total cost |
|---|---:|---:|---:|---:|
| **LedgerMind** | 5.0.0 | **24/24, 73/73** | 269,844 | **$0.345350** |
| Raw history | — | 24/24, 73/73 | 14,531,917 | $0.407496 |
| ReMe | 0.4.2.3 | 24/24, 73/73 | 366,693 | $1.085034 |
| Claude-Mem | 16.0.4 | 22/24, 68/73 | 514,426 | $0.607301 |
| Cognee | 1.6.10 | 21/24, 68/73 | 79,039 | $0.765784 |
| Hindsight | 1.2.3 | 19/24, 66/73 | 500,616 | $1.585927 |
| Mem0 OSS | 2.2.1 | 18/24, 60/73 | 172,064 | $0.288878 |
| Supermemory Local | 0.0.9 | 15/24, 57/73 | 162,023 | $0.893317 |

All eight arms completed 24/24 probes with zero technical failures and zero
unfinished tasks.

### How to read the result

LedgerMind scored **24/24 probes and 73/73 fields** at **$0.345350**, with
269,844 agent input tokens. ReMe matched it at 24/24 but cost **$1.085034**, or
**3.14× LedgerMind**. Raw history also reached 24/24, but only by sending the
agent **14,531,917 input tokens** (53.9× LedgerMind) at a total of $0.407496,
which is **18.0% more** than LedgerMind (LedgerMind is 15.3% cheaper).

The chart in the main README plots the headline trade-off: semantic accuracy
against total run cost. LedgerMind is the only arm at 100% accuracy below
$0.35, and the same SVG is published as
`benchmarks/memory-lifecycle-2026-11-22/accuracy-vs-cost.svg`.

## Per-arm disclosures

### LedgerMind

24/24 and 73/73 with zero incorrect or forbidden values on the semantic review.
Memory cost was `$0.321172` over 1,202 core calls; the full run, including the 24
agent probes, was `$0.345350`. The agent consumed 269,844 input tokens across all
recorded calls: the 24 probes plus the two failed repair attempts. The store held
1,343 active knowledge values across 195 active memory objects at the end of the
suite, with zero protocol repairs.

### Raw history

24/24 and 73/73 by supplying the source history without compression. The price
is context volume: 14,531,917 agent input tokens, 53.9× LedgerMind, across 97
successful calls; two failed repair attempts add 185,413 tokens and are included
in the published total. Total cost was $0.407496. Raw history does not
demonstrate a memory lifecycle; it demonstrates what unbounded context can buy.

### ReMe 0.4.2.3

24/24 and 73/73, with 0 incorrect and 0 forbidden answers. ReMe rewrites a single
daily note per session with `[SUPERSEDED]` markers and a current snapshot, which
let it pass every probe the other systems lost. Two answers are **borderline** and
accepted in the base score:

- `E2-P1.test_status = "blocked"` instead of `failed`, with the correct
  `AttributeError: 'dict' object has no attribute 'start'` traceback.
- `R2-P2.scales = "[1.5,1.25,1.0,0.75,0.5]"` lists five real scales instead of
  the number `5`.

A strict alternate that rejects both records **22/24, 71/73**. Cost was
**$1.085034**, **3.14× LedgerMind**, driven by 2,347 memory LLM calls and
25.07M input tokens from re-reading and editing the growing note (up to 354 KB
in `K3`).

### Claude-Mem 16.0.4

22/24 and 68/73, the strongest third-party result in this run and one of two
third-party systems to pass `K3-P2`. Two probes failed, both on early or
intermediate CSS chronology:

- `E3-P1`: an early 16px/all-sides version instead of the final `::after` 20px
  bottom-only buffer; the 4,096-token injection cap was reached before the final
  state.
- `K3-P1`: `leave_delay_ms="150"` and animation classes as the title, instead of
  `80` and `static`.

Total cost $0.607301, 1.76× LedgerMind, with 514,426 agent input tokens.

### Cognee 1.6.10

21/24 and 68/73, including correct `I2` separation, the exact `K2` scale count,
and the `R1-P2` numeric limits. It lost three temporal-overwrite probes:

- `K1-P2`: `leave_delay_ms="150ms"` instead of `0ms`.
- `K3-P1`: stale `150` delay and an animated title.
- `K3-P2`: intermediate `200` delay and an active rAF instead of `0` and
  `absent`.

Under a stricter requirement for self-contained `I2` values the score would be
19/24, 64/73. Total cost $0.765784.

### Hindsight 1.2.3

19/24 and 66/73, with the highest total cost among the eight arms:
**$1.585927**, 4.59× LedgerMind. Injections averaged roughly 3,718 tokens per
probe, producing 500,616 agent input tokens without deterministic replacement of
stale versions. It lost `K1-P2`, `K3-P1`, `K3-P2` on stale delays and widths,
`E2-P1` on an earlier container-start error instead of the final traceback, and
`R2-P2` on stage order that omitted alignment.

### Mem0 OSS 2.2.1

18/24 and 60/73. It lost `I2-P1` by inverting the demo-link/card facts, both
`K3` probes on stale delays and titles, `R1-P2` by answering `unknown` for every
numeric limit, and both `K2` probes by answering `"multiscale"` without the exact
count `5`. A lenient reading of `K2.scales` would raise it to at most 20/24.
Total cost $0.288878.

### Supermemory Local 0.0.9

15/24 and 57/73, the weakest of the six third-party memory systems.
Across 2,459 `CreateMemory` calls the built-in memory agent called
`forgetMemory` once and `linkMemories` once, so stale drafts survived alongside
final state and displaced it in the top-10. It lost nine probes: `E2-P1`,
`E2-P2`, `E3-P1`, `I3-P1`, `K1-P2`, `K3-P1`, `K3-P2`, `R2-P1`, `R2-P2`.
Total cost $0.893317.

## LedgerMind versus raw history

LedgerMind and raw history both reach **24/24 probes and 73/73 semantic fields**,
so the difference is not answer quality. It is what each system has to put in
front of the agent, how much token volume is processed at query time and across
the lifecycle, and how cost scales as history grows:

| Dimension | LedgerMind 5.0.0 | Raw history | Ratio (Raw / LedgerMind) |
|---|---:|---:|---:|
| Probes / semantic fields | **24/24, 73/73** | 24/24, 73/73 | 1.00× |
| Agent LLM calls (24 probes) | 96 | 99 | 1.03× |
| Agent input tokens | **269,844** | 14,531,917 | **53.85×** |
| Agent cached input tokens | 204,032 | 11,024,732 | 54.03× |
| Agent uncached input tokens | **65,812** | 3,507,185 | **53.29×** |
| Mean agent input tokens per probe | **11,244** | 605,497 | **53.85×** |
| Mean agent input tokens per call | **2,811** | 146,787 | **52.22×** |
| Agent output tokens | 31,575 | 25,357 | 0.80× |
| Agent reasoning tokens | 18,262 | 10,898 | 0.60× |
| Memory LLM calls (323 source rounds) | 1,202 (860 gen + 342 decision) | 0 | — |
| Memory input tokens | 3,611,181 | 0 | — |
| Memory output tokens | 583,046 | 0 | — |
| Total input tokens (agent + memory) | **3,881,025** | 14,531,917 | **3.74×** |
| Total output tokens (agent + memory) | 614,621 | 25,357 | 0.04× |
| Total tokens across full run | **4,495,646** | 14,557,274 | **3.24×** |
| Agent query cost (24 probes) | **$0.023185** | $0.407496 | **17.58×** |
| Memory formation cost (323 rounds) | $0.321172 | $0.000000 | — |
| Total run cost | **$0.345350** | $0.407496 | **1.18×** |
| Mean query cost per probe | **$0.000966** | $0.016979 | **17.58×** |
| Stored state at the end | 1,343 active knowledge values / 195 memory objects | verbatim transcript, no memory store | — |
| Protocol repairs | **0** | 2 | — |
| Privacy and scaling boundary | compact formed memory; source history is not replayed; query cost is bounded by working context | full transcript is placed in the model context on every probe; query cost grows with transcript length | — |

Key takeaways from the comparison:

- **53.9× less agent input context:** On the 24 evaluation probes, LedgerMind
  feeds the agent 269,844 input tokens (11,244 per probe, 2,811 per call) versus
  14,531,917 for raw history (605,497 per probe, 146,787 per call). Uncached
  agent input drops by the same factor (65,812 versus 3,507,185).
- **17.6× cheaper per probe at query time:** Because memory formation is paid
  once when work happens (`$0.321172` across 323 rounds, or `$0.000994` per
  round), answering the 24 probes with LedgerMind costs only `$0.023185`
  (`$0.000966` per probe) compared with `$0.407496` (`$0.016979` per probe) for
  raw history.
- **3.24× fewer total tokens even including memory formation:** Combining every
  memory-generation call, memory-decision call, and agent probe call, LedgerMind
  processes 4,495,646 tokens in total (3,881,025 input + 614,621 output),
  whereas raw history processes 14,557,274 tokens.
- **Zero protocol repairs:** LedgerMind completed all 24 probes with 0 protocol
  repairs; raw history required 2 repair attempts (`185,413` extra input tokens,
  `$0.022615`) when the agent mishandled tool output inside an oversized prompt.

## Token and cost breakdown

Source: each arm's `summary.json` under `arms/<arm>/` in the run artifacts. For
ReMe, Claude-Mem, Cognee, Hindsight, Mem0 OSS and Supermemory Local the agent
figures come directly from `agent_usage_totals` (`agent_provider_attempts` for
call counts) and the memory figures from `memory_generation_usage_totals`
(`memory_generation_attempts` for call counts). For LedgerMind and raw history
the agent input/output figures are the sums over all recorded agent calls in the
call index, including the two failed repair attempts, which consumed tokens and
were billed (harness preflight is outside these sums); the matching cached-input
and reasoning figures come from the same call index. Uncached input is
`input − cached input`.

### Agent token expenditure (24 probes)

| Arm | Agent LLM calls | Agent input | Agent cached input | Agent uncached input | Agent output | Agent reasoning | Mean input / probe |
|---|---:|---:|---:|---:|---:|---:|---:|
| **LedgerMind** | 96 | 269,844 | 204,032 | 65,812 | 31,575 | 18,262 | 11,244 |
| Raw history | 99 | 14,531,917 | 11,024,732 | 3,507,185 | 25,357 | 10,898 | 605,497 |
| ReMe | 99 | 366,693 | 274,316 | 92,377 | 26,682 | 12,258 | 15,279 |
| Claude-Mem | 102 | 514,426 | 389,168 | 125,258 | 36,306 | 21,709 | 21,434 |
| Cognee | 97 | 79,039 | 57,716 | 21,323 | 19,718 | 13,345 | 3,293 |
| Hindsight | 100 | 500,616 | 366,824 | 133,792 | 36,803 | 20,593 | 20,859 |
| Mem0 OSS | 97 | 172,064 | 126,068 | 45,996 | 29,686 | 22,938 | 7,169 |
| Supermemory Local | 98 | 162,023 | 118,576 | 43,447 | 39,306 | 29,939 | 6,751 |

### Memory-formation token expenditure (323 source rounds)

| Arm | Memory LLM calls | Memory input | Memory cached input | Memory uncached input | Memory output | Memory reasoning | Local embedding attempts |
|---|---:|---:|---:|---:|---:|---:|---:|
| **LedgerMind** | 1,202 | 3,611,181 | — | — | 583,046 | 0 | 0 |
| Raw history | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ReMe | 2,347 | 25,072,304 | 17,752,316 | 7,319,988 | 516,700 | 46,165 | 631 |
| Claude-Mem | 1,796 | 15,783,760 | 12,932,600 | 2,851,160 | 476,438 | 37,089 | 0 |
| Cognee | 1,459 | 5,582,573 | 3,265,140 | 2,317,433 | 1,017,515 | 248,202 | 3,220 |
| Hindsight | 3,633 | 15,267,328 | 10,452,624 | 4,814,704 | 2,058,797 | 453,411 | 3,624 |
| Mem0 OSS | 323 | 4,682,602 | 2,642,444 | 2,040,158 | 108,691 | 26,678 | 657 |
| Supermemory Local | 1,208 | 17,832,361 | 11,696,108 | 6,136,253 | 416,870 | 42,886 | 4,112 |

### Combined token volume and cost breakdown

| Arm | Total LLM calls | Total input tokens | Total output tokens | Total tokens (in + out) | Agent cost | Memory cost | Total cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| **LedgerMind** | 1,298 | 3,881,025 | 614,621 | 4,495,646 | **$0.023185** | **$0.321172** | **$0.345350** |
| Raw history | 99 | 14,531,917 | 25,357 | 14,557,274 | $0.407496 | $0.000000 | $0.407496 |
| ReMe | 2,446 | 25,438,997 | 543,382 | 25,982,379 | $0.023676 | $1.061358 | $1.085034 |
| Claude-Mem | 1,898 | 16,298,186 | 512,744 | 16,810,930 | $0.032235 | $0.575065 | $0.607301 |
| Cognee | 1,556 | 5,661,612 | 1,037,233 | 6,698,845 | $0.012222 | $0.753561 | $0.765784 |
| Hindsight | 3,733 | 15,767,944 | 2,095,600 | 17,863,544 | $0.033248 | $1.552679 | $1.585927 |
| Mem0 OSS | 420 | 4,854,666 | 138,377 | 4,993,043 | $0.019947 | $0.268931 | $0.288878 |
| Supermemory Local | 1,306 | 17,994,384 | 456,176 | 18,450,560 | $0.024472 | $0.868845 | $0.893317 |

Notes:

- LedgerMind's memory work combines generation (`860` calls: `2,287,326` input /
  `429,001` output, `$0.265570`) and memory-decision (`342` calls: `1,323,855`
  input / `154,045` output, `$0.055602`) calls. Its internal Core telemetry logs
  total memory input/output tokens and provider cost without a per-call
  cached-input split (`—` above). Agent cost covers all 96 agent calls,
  including the two failed repair attempts; the run total also includes
  `$0.000993` of harness preflight, which is why
  `$0.023185 + $0.321172 + $0.000993 = $0.345350`.
- Raw history has no memory store or memory-generation calls; all cost is agent
  cost. Two failed repair attempts account for `185,413` input tokens and
  `$0.022615` not present in the per-probe sums.
- Local embedding attempts were executed by the local runtime and are not billed
  through the provider; the column shows how often the local embedder was used.
- Agent and memory costs are provider-reported call sums. They add up to the
  published total for every third-party arm.

## Evidence and reproducibility

Published in `benchmarks/memory-lifecycle-2026-11-22/`:

| File | Contents |
|---|---|
| `summary.json` | Aggregates for eight arms, including agent and memory token counts, agent and memory cost, and the alternate strict scores. |
| `rubric.json` | 24 probes: `id`, `family`, `expected`, `forbidden`, typed `fields`. |
| `evidence.json` | 192 records (8 × 24): recorded answer, semantic verdict, note, token/cost totals, source sha256. |
| `artifact-digests.json` | 208 sha256 digests of the source manifests, summaries, and result files. |
| `accuracy-vs-cost.svg` | Static accuracy-versus-cost chart with every arm labelled. |
| `manifests/<arm>.json` | Eight run manifests with versions and budgets. |
| `hashes.sha256` | Authoritative corpus and config digests. |
| `verify.py` | Offline consistency, public-content and privacy checker. |

Run from the repository root:

```bash
python benchmarks/memory-lifecycle-2026-11-22/verify.py
```

The checker is standard-library only and performs no network calls. It validates
every JSON file, the eight arms and 24 probes per arm, the 24-probe / 73-field
rubric, the pass counts against `summary.json` (counting `pass_borderline` as a
pass), the arm order and versions, the per-probe token sums for LedgerMind and
raw history, all 208 digests, the presence of the accuracy-versus-cost chart,
the absence of removed benchmark variants and scoring terms from the published
markdown, JSON and SVG, and the absence of prompts, messages, action histories,
provider calls, telemetry, request identifiers, endpoints, credentials and
workspace paths in `evidence.json`.

The raw corpus and config are not published because the scenarios are real
sessions containing private work. The corpus and config digests are pinned; the
rubric, the recorded answers, the manual verdicts and the per-file digests are
published so the scoring can be audited and every record can be matched to the
original artifact by hash.

## Historical notes

The earlier Workflow Transfer series
(`benchmarks/workflow-transfer-20260909T*.json` and
`benchmarks/workflow-transfer-20260919.json`) remains in the repository as an
archive of a different protocol with different tasks and scoring. Those files
are not part of the current result and must not be combined with this suite.

## Limitations

- **One run per arm.** No repeated-run variance or confidence interval is
  published; a difference of one probe is not a stability claim.
- **Manual semantic review.** Verdicts come from a single-reviewer audit
  confirmed by the project owner, not independent multi-reviewer adjudication.
- **Borderline and alternate scores.** ReMe's 24/24 includes two accepted
  borderlines; the strict alternate is 22/24. Mem0 and Cognee also have stricter
  alternates. The base score and the alternates are both published.
- **Development corpus.** The scenarios are a development set built from shared
  real sessions, not a held-out benchmark, and the simulator records historical
  state rather than replaying live deployment.
