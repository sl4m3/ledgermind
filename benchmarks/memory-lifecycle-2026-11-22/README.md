# Memory Lifecycle Benchmark — 2026-11-22

This directory publishes the evidence for the 2026-11-22 memory-lifecycle
suite: **12 scenarios, 24 probes and 73 checked fields** across **8 arms**.

Every arm ran against the same frozen corpus and the same run configuration.
Semantic accuracy comes from a completed manual review of the recorded answers;
it is not an LLM-judge score.

- Corpus: `corpus.json`, `sha256:1fd4d52163294f166fd481569bb6ab3f5654852ad0e3bdace72f74ce6158934f`
- Config: `config/muse_ember_config.json`, `sha256:645e9b85c1c175c3a16fe45439d2333b55433bf62b0ff22416e8375b51a8cf42`
- Agent and memory model: `meta/muse-ember`, route `google-vertex/global`
- Reasoning: `low` for the agent, `minimal` for memory work
- Embedding: local `nemotron-3-embed-1b-bf16`, 2048 dimensions (config default; per-arm deviations are recorded in the manifests)

The scenario families are **E** (execution), **I** (identity), **K** (knowledge
evolution) and **R** (delivery). Two probes per scenario give 24 probes; the
checked fields per probe sum to 73.

## Layout

| File | Contents |
|---|---|
| [`summary.json`](summary.json) | Machine-readable aggregates for all eight arms: probe and field counts, semantic totals, agent and memory token totals, agent and memory cost, total cost, review caveats. |
| [`rubric.json`](rubric.json) | The 24 probes with `id`, `family`, `expected`, `forbidden` and the typed `fields` rubric used for scoring. |
| [`evidence.json`](evidence.json) | 8 arms × 24 probes: the recorded answer, the manual semantic verdict (`pass`, `fail` or `pass_borderline`), a short note, token/cost totals and the sha256 of the original result file. |
| [`artifact-digests.json`](artifact-digests.json) | sha256 digests of the 8 source `manifest.json`, 8 `summary.json` and 192 `results/*.json` files (208 entries). |
| [`manifests/<arm>.json`](manifests) | The eight run manifests: versions, models, budgets, retrieval settings and data-handling flags. |
| [`accuracy-vs-cost.svg`](accuracy-vs-cost.svg) | Static chart of semantic accuracy against total run cost, with every arm labelled. |
| [`hashes.sha256`](hashes.sha256) | The authoritative corpus and config digests recorded before the run. |
| [`verify.py`](verify.py) | Offline consistency checker (standard library only). |

## What is published and what is not

Published: final recorded answers (`recorded`), expected and forbidden values,
per-probe semantic verdicts, aggregate token and cost figures, run manifests,
version and budget metadata, and sha256 digests of the original artifacts.

Not published: the raw corpus scenarios, the run configuration, agent prompts,
message histories, action histories, provider calls, telemetry payloads,
request identifiers, credentials and local paths. The eight run manifests are
published with their model, budget and data-handling metadata, so they retain
the harness's loopback embedding/reranker address (`127.0.0.1`); no remote
endpoints or credentials are included. The source sessions are real work
sessions, so the raw transcript stays private. The
published rubric, recorded answers and digests are enough to audit the scoring
and to match every record against the original artifact by hash.

## How to verify

From the repository root:

```bash
python benchmarks/memory-lifecycle-2026-11-22/verify.py
```

The checker confirms that all JSON parses, that there are eight arms with 24
probes each, that the rubric holds 24 probes and 73 fields, that the
`pass`/`pass_borderline` counts per arm agree with `summary.json`, that
`artifact-digests.json` holds 208 well-formed digests, that the accuracy-versus-cost
chart is present and labels every arm, that the published files contain no
removed terms, and that the published evidence contains no prompts, histories,
provider calls, request identifiers, endpoints or credentials. It prints `PASS`
or `FAIL` and exits `0` or `1`.

`hashes.sha256` pins the private source files. Its entries cannot be re-checked
without those files; `verify.py` checks that the same digests are declared in
`summary.json`.

## Reading `evidence.json`

Each record has a fixed shape:

```json
{
  "arm": "ledgermind",
  "task_id": "E1-P1",
  "family": "E1",
  "stage": "historical_continuation",
  "recorded": {"entrypoint": "src/index.ts", "production": "NO-GO", "slice": "Wave 7A"},
  "semantic_verdict": "pass",
  "notes": "",
  "usage": {"input_tokens": 9046, "output_tokens": 1025, "cost_usd": 0.00078273, "successful_calls": 4},
  "source_sha256": "59dc42f3632ed032c1829991bbe76b49111a068e8faa7e7cb8c5b47cdeff012a"
}
```

`notes` is empty when a probe needs no explanation. `pass_borderline` marks a
probe accepted in the base score but disputed under a stricter reading; the
tables in [`../../BENCHMARK.md`](../../BENCHMARK.md) state those alternative
scores explicitly.

## Caveats

- One completed run per arm; no repeated-run variance is published.
- Semantic verdicts are a single-reviewer manual audit confirmed by the
  project owner, not an independent multi-reviewer adjudication.
- The corpus is a development set built from shared real sessions, not a held
  out test set.
