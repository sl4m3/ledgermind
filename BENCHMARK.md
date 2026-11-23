# Memory Lifecycle Benchmark

- **Suite:** `memory-lifecycle-2026-11-22`
- **Scenarios / probes / fields:** 12 / 24 / 73
- **Arms:** 9, one completed run each
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

The corpus holds 12 scenarios, 24 probes, and 73 checked fields. The same frozen
corpus and config were used for every arm; no arm received the expected answers.
The 22 probes outside the two `E3` probes are reported separately as
**memory-dependent**, because the `E3` field contracts alone suggest plausible
defaults.

Field values are scored twice:

1. **Semantic** — a completed manual review of what the recorded answer means.
2. **Literal** — the automated `evaluate_action_task` check, which is stricter
   about exact wording and reported separately.

The semantic review is the headline number. It was performed over the recorded
answers against the typed rubric and the source history, and confirmed by the
project owner. The pipeline's own `semantic_review_status=pending_manual` in the
original `summary.json` only means the automated pipeline never wrote manual
verdicts; the authoritative verdicts are published in
`summary.json` and `evidence.json`.

## Results

| Arm | Version | Semantic all (24 / 73) | Memory-dependent (22 / 65) | Literal (24 / 73) | Agent input tokens | Total cost |
|---|---:|---:|---:|---:|---:|---:|
| **LedgerMind** | — | **24/24, 73/73** | **22/22, 65/65** | 16/24, 61/73 | 269,844 | **$0.345350** |
| ReMe | 0.4.2.3 | 24/24, 73/73 | 22/22, 65/65 | 15/24, 60/73 | 366,693 | $1.085034 |
| Raw history | — | 24/24, 73/73 | 22/22, 65/65 | 18/24, 64/73 | 14,531,917 | $0.407496 |
| Claude-Mem | 16.0.4 | 22/24, 68/73 | 21/22, 63/65 | 17/24, 59/73 | 514,426 | $0.607301 |
| Cognee | 1.6.10 | 21/24, 68/73 | 19/22, 60/65 | 15/24, 56/73 | 79,039 | $0.765784 |
| Hindsight | 1.2.3 | 19/24, 66/73 | 17/22, 58/65 | 15/24, 57/73 | 500,616 | $1.585927 |
| Mem0 OSS | 2.2.1 | 18/24, 60/73 | 16/22, 52/65 | 12/24, 51/73 | 172,064 | $0.288878 |
| Supermemory Local | 0.0.9 | 15/24, 57/73 | 14/22, 51/65 | 12/24, 51/73 | 162,023 | $0.893317 |
| No memory | — | 2/24, 8/73 | 0/22, 0/65 | 2/24, 8/73 | 69,592 | $0.019096 |

All nine arms completed 24/24 probes with zero technical failures and zero
unfinished tasks.

### How to read the result

LedgerMind scored **24/24 probes and 73/73 fields** at **$0.345350**, with
269,844 agent input tokens. ReMe matched it at 24/24 but cost **$1.085034**, or
**3.14× LedgerMind**. Raw history also reached 24/24, but only by sending the
agent **14,531,917 input tokens** (53.9× LedgerMind) at a total of $0.407496.

The no-memory control scored **2/24** and **0/65 memory-dependent fields**: it
guessed `E3-P1` and `E3-P2` from the field contracts and recorded `unknown` (or
inverted values in `I2-P2`) for everything else.

The literal column tells a different story: raw history leads at 18/24, because
it reproduces exact source wording, while semantic scoring accepts source-grounded
equivalents. The two scales are deliberately not merged.

## Per-arm disclosures

### LedgerMind

24/24 and 73/73 with zero incorrect or forbidden values on the semantic review.
Memory cost was `$0.321172` over 1,202 core calls; the full run, including the 24
agent probes, was `$0.345350`. The agent consumed 269,844 input tokens. Literal
scoring was 16/24, 61/73: the eight literal probe misses are wording differences,
not wrong state.

### ReMe 0.4.2.3

24/24 and 73/73, with 0 incorrect and 0 forbidden answers. ReMe rewrites a single
daily note per session with `[SUPERSEDED]` markers and a current snapshot, which
let it pass every probe the other systems lost. Two answers are **borderline** and
accepted in the base score:

- `E2-P1.test_status = "blocked"` instead of `failed`, with the correct
  `AttributeError: 'dict' object has no attribute 'start'` traceback.
- `R2-P2.scales = "[1.5,1.25,1.0,0.75,0.5]"` lists five real scales instead of
  the literal `5`.

A strict alternate that rejects both records **22/24, 71/73** overall and
**20/22, 63/65** on memory-dependent probes. Cost was **$1.085034**,
**3.14× LedgerMind**, driven by 2,347 memory LLM calls and 25.07M input tokens
from re-reading and editing the growing note (up to 354 KB in `K3`).

### Raw history

24/24 and 73/73 by supplying the source history without compression. The price
is context volume: 14,531,917 agent input tokens, 53.9× LedgerMind, across 99
calls. Total cost was $0.407496. Raw history is the literal-accuracy ceiling
(18/24, 64/73) but does not demonstrate a memory lifecycle; it demonstrates what
unbounded context can buy.

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

19/24 and 66/73, with the highest total cost among the six memory systems:
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

### No memory

2/24 and 8/73. Only `E3-P1` and `E3-P2` were guessed from narrow field
contracts; the calibration flag `calibration_valid` is false. On the other 22
probes it produced 0/65 fields, answering `unknown` in 21 probes and inverting
`I2-P2`. Cost $0.019096. This arm is the floor, not a memory system.

## Evidence and reproducibility

Published in `benchmarks/memory-lifecycle-2026-11-22/`:

| File | Contents |
|---|---|
| `summary.json` | Aggregates for nine arms, including the alternate strict scores. |
| `rubric.json` | 24 probes: `id`, `family`, `expected`, `forbidden`, typed `fields`. |
| `evidence.json` | 216 records (9 × 24): recorded answer, semantic verdict, note, token/cost totals, source sha256. |
| `artifact-digests.json` | 234 sha256 digests of the source manifests, summaries, and result files. |
| `manifests/<arm>.json` | Nine run manifests with versions and budgets. |
| `hashes.sha256` | Authoritative corpus and config digests. |
| `verify.py` | Offline consistency and privacy checker. |

Run from the repository root:

```bash
python benchmarks/memory-lifecycle-2026-11-22/verify.py
```

The checker is standard-library only and performs no network calls. It validates
every JSON file, the nine arms and 24 probes per arm, the 24-probe / 73-field
rubric, the pass counts against `summary.json` (counting `pass_borderline` as a
pass), all 234 digests, and the absence of prompts, messages, action histories,
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
- **Literal versus semantic.** Exact-wording scoring produces lower numbers than
  source-grounded semantic scoring; neither scale alone describes usefulness.
