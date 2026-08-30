<p align="center">
  <img src="assets/ledgermind-mark.svg" width="144" alt="LedgerMind logo">
</p>

<h1 align="center">LedgerMind</h1>

## Agents should not have to relearn the same work

LedgerMind turns completed agent workflows into compact, reusable knowledge.
When a similar task appears later, the agent gets the relevant procedure,
constraints, and current decisions without replaying the entire history that
produced them.

It is memory built for the next action—not a transcript archive and not a pile
of extracted notes.

LedgerMind is for anyone who wants an agent to remember what it has learned:
individual agent users, developers building local assistants, platform teams
adding memory to their products, and enterprises that need a controlled local
knowledge layer.

[See the benchmark](BENCHMARK.md) · [Follow releases](https://github.com/sl4m3/ledgermind/releases) · [Contact LedgerMind](mailto:s.zotov@ledgermind.org)

> **Status:** LedgerMind 4.0 is under active development. The current Local
> package is an alpha release (`4.0.0a1`).

## Your knowledge stays local by design

LedgerMind Core is proprietary, but it is not a cloud service and it has no
hidden network path. Core runs as a local, network-isolated process and owns a
private local knowledge database.

- Core contains no HTTP, TLS, DNS, or cloud client.
- Core never receives API keys, provider credentials, model endpoints, or
  remote-service configuration.
- Core communicates only with the local LedgerMind runtime through a versioned
  process boundary.
- All external communication is handled outside Core by publicly inspectable
  components: [Integrations](https://github.com/sl4m3/ledgermind-integrations)
  and [Local](https://github.com/sl4m3/ledgermind-local).
- The operator chooses every model and delivery endpoint. With local generation
  and embedding models, the complete memory workflow can remain on the user's
  machine.

This is an architectural boundary, not a promise that proprietary code will
simply behave. The knowledge engine has no provider secret and no networking
capability with which to send user memory anywhere.

If an operator configures a remote model provider, the necessary model payload
can leave the machine through Local. That egress is explicit, auditable, and
limited to the endpoint selected by the operator; it never originates from
Core itself.

## Same outcomes. Much less context.

In our latest 12-workflow transfer benchmark, LedgerMind, Mem0 OSS, and raw
history all completed every task with no safety violations. LedgerMind reached
the same outcomes while sending substantially less context to the agent.

| Result | LedgerMind | Mem0 OSS | Raw history |
|---|---:|---:|---:|
| Successful workflows | **12 / 12** | 12 / 12 | 12 / 12 |
| Safety violations | **0** | 0 | 0 |
| Agent execution tokens | **96,572** | 104,734 | 173,210 |
| Memory injected into agent prompts | **5,945** | 15,690 | 82,265 |
| Returned memory context | **1,289** | 2,701 | 14,957 |
| Agent actions | **76** | 76 | 76 |
| Final authoritative changes retained as knowledge | **4 / 4** | 1 / 4 | Not applicable |

That means LedgerMind used:

- **44.2% fewer agent tokens than raw history**;
- **7.8% fewer agent tokens than Mem0 OSS**;
- **92.8% less injected memory than raw history**;
- **62.1% less injected memory than Mem0 OSS**;
- **49.5% fewer tokens to form the initial memory than Mem0 OSS**.

The output-token totals remained nearly identical. The reduction came from
giving the agent less irrelevant input—not from shortening its work or
accepting fewer completed tasks.

LedgerMind did spend more tokens on online memory updates: 173,229 versus
138,701 for Mem0 OSS. That number is reported, but it is not an apples-to-apples
efficiency result. A manual inspection of the resulting memories found that
LedgerMind retained the final authoritative change in all four workflow
families; Mem0 retained one of four. The two systems therefore did not produce
equivalent memory. Cheaper post-processing is not a product win when the
updated knowledge is absent.

[Read the benchmark methodology, calculations, and limitations](BENCHMARK.md).

## Memory that compounds

The product loop is deliberately simple:

```mermaid
flowchart LR
    A[Completed work] --> B[LedgerMind]
    B --> C[Reusable knowledge]
    C --> D[Relevant recall]
    D --> E[Next similar task]
    E --> A
```

A useful memory system must do more than find a similar sentence. It must help
an agent carry experience forward as the environment changes.

LedgerMind is designed to:

- preserve reusable knowledge while leaving exploratory noise behind;
- recognize when new evidence refers to something already known;
- revise knowledge when an authoritative rule changes;
- retain source evidence and change history;
- return a focused working context instead of an ever-growing transcript.

The result is a memory that can become more useful over time without requiring
the agent to reread everything it has ever done.

## Tested on changing workflows

The Workflow Transfer Benchmark does not grade the wording of stored memories.
It tests whether memory helps an agent complete the next workflow.

The current pilot covers four operational families:

- production configuration rollout;
- incident diagnosis and recovery;
- user offboarding and equipment release;
- business-data cleanup and publication.

Each family contains three sequential transfer tasks:

1. repeat the process with different entities;
2. apply the same principle in a changed environment;
3. follow a new or conflicting rule without blindly repeating old experience.

The agent sees only public tools, observations, and the context supplied by its
memory mode. Completion and safety are checked against hidden simulator state,
not by a semantic judge. Every compared arm receives the same source experience
and uses the same agent model, prompts, action limit, and public task inputs.

This isolates the question LedgerMind exists to answer:

> Can an agent reuse experience with less context while remaining correct and
> safe?

In this development run, the answer was yes.

## What the agent receives

LedgerMind does not ask the next agent to reread the transcript that created a
piece of knowledge. It returns a small working context containing the current
procedure and the conditions that matter to the new task.

For example, a rollout history may contain investigation, a failed legacy
backup attempt, a corrected immutable snapshot step, CAB approval, execution,
and validation. On the next rollout, the useful result is closer to:

```text
Production rollout

- Create an immutable snapshot before making the change.
- CAB approval remains mandatory.
- Apply the configuration, validate health, and use the snapshot for rollback.
- Do not use the superseded legacy backup step.
```

The exact wording is model-produced and can vary. What matters is that the
agent receives the current reusable procedure instead of the full path of
experiments and corrections that produced it. In the benchmark, this was
validated by the agent reaching the same hidden workflow state with much less
injected context.

## Built around trust boundaries

LedgerMind separates capture, orchestration, knowledge storage, and external
model execution.

| Component | Responsibility | Network boundary |
|---|---|---|
| [Integrations](https://github.com/sl4m3/ledgermind-integrations) | Capture completed interactions and deliver them to the selected runtime | Delivery only; public source |
| [Local](https://github.com/sl4m3/ledgermind-local) | Runtime supervision, configured model calls, secrets, retries, and egress audit | Operator-selected endpoints; source available |
| Core | Own and retrieve durable knowledge | None; local process only |

Core runs as a separate signed process. It does not receive provider
credentials and cannot call external services. Local executes model work using
profiles chosen by the operator, while integrations remain capture-only.

This separation keeps raw data, provider access, and durable memory behind
explicit boundaries instead of blending them into one opaque agent process.
The closed knowledge engine is surrounded by network-facing code that users can
inspect, configure, and audit.

## Data flow and control

| Data | Where it is handled | Can it leave the machine? |
|---|---|---|
| Completed messages and tool activity | Captured by Integrations and delivered to the configured runtime | Only through the delivery endpoint selected by the operator |
| Raw workflow payloads | Stored by Local for durable processing and bounded retention | Only when Local sends the necessary payload to a configured remote model |
| Provider credentials | Stored by reference in Local's secret boundary | Used only to authenticate to the operator-selected provider; never passed to Core |
| Durable knowledge | Owned by Core in its private local database | Core has no network client and cannot transmit it |
| Recalled working context | Returned locally to the requesting integration or agent | It may subsequently leave through that caller if the operator uses a remote agent |

Raw workflow payload bodies expire after 30 days by default; the retention
period is configurable. Operators can run a bounded purge explicitly:

```bash
ledgermind maintenance retention --limit 100
```

Local supports coordinated backup and restore of its database and the opaque
Core-owned data:

```bash
ledgermind backup create --destination /secure/path
ledgermind backup restore --source /secure/path/ledgermind-core-backup.zip
```

Backup archives can contain sensitive workflow data and must be protected like
credentials. A normal uninstall preserves memory, configuration, and secrets.
Permanent removal is explicit and requires confirmation through the
`--purge-data`, `--purge-config`, and `--yes` flags.

## What ships

| Component | Purpose | Source and license |
|---|---|---|
| LedgerMind Integrations | Capture completed agent interactions and deliver versioned RawRounds | Public source, Apache-2.0 |
| LedgerMind Local | Installer, local service, provider profiles, secrets, retries, retention, backup, and egress audit | Source available, Business Source License 1.1 |
| LedgerMind Protocol | Public contracts, schemas, canonical JSON, and conformance fixtures | Public source, Apache-2.0 |
| LedgerMind Core | Durable knowledge formation, revision, and retrieval | Proprietary signed local binary |

Local's Business Source License permits internal-tool and non-commercial
deployments under its Additional Use Grant and changes to GPLv3-or-later on
the stated Change Date. Production uses outside that grant require a commercial
license. The license file shipped with each release is authoritative.

## Current compatibility

| Capability | Current support |
|---|---|
| Operating systems | Linux x86_64 and Linux aarch64 |
| Agent integration | Hermes |
| Generation | Operator-selected OpenAI-compatible API |
| Embeddings | Operator-selected OpenAI-compatible API or a signed local CPU/GPU model catalog entry |
| Installation | Rootless, XDG directory layout, signed release artifacts |
| Runtime mode | On demand through client TTL leases |

This table describes the current implementation, not a promise of unlisted
platforms or integrations.

## What LedgerMind is not

LedgerMind is not:

- long-term storage for every message an agent has seen;
- a vector database presented as a complete memory system;
- an autonomous source of truth;
- a semantic benchmark optimized to match a hand-written answer key.

It is a knowledge memory whose value is measured downstream: whether the next
task is completed correctly with less repeated investigation and less context.

## Repositories

- **`ledgermind`** — this public project page and future release entry point.
- **[`ledgermind-integrations`](https://github.com/sl4m3/ledgermind-integrations)**
  — public capture adapters and the versioned protocol package.
- **[`ledgermind-local`](https://github.com/sl4m3/ledgermind-local)** — local
  service, provider boundary, runtime supervision, and installer.
- **`ledgermind-core`** — the private knowledge engine, distributed as a signed
  binary with authorized releases.

## Installation

The public release bundle and rootless installer are being prepared. The
planned release interface is:

```bash
curl -fsSL https://github.com/sl4m3/ledgermind/releases/latest/download/install.sh | sh
ledgermind doctor --json
ledgermind runtime status --json
```

Until the first release is published, treat these commands as the intended
interface rather than an available installation channel. Development setup is
maintained in the component repositories.

## Choose your path

- **Using an agent yourself?** Follow
  [LedgerMind releases](https://github.com/sl4m3/ledgermind/releases) for the
  self-hosted local package.
- **Building an agent or platform?** Start with the public
  [Integrations](https://github.com/sl4m3/ledgermind-integrations) and
  [Local runtime](https://github.com/sl4m3/ledgermind-local), or
  [contact us](mailto:s.zotov@ledgermind.org) to discuss an integration.
- **Evaluating LedgerMind for an organization?** Contact
  [s.zotov@ledgermind.org](mailto:s.zotov@ledgermind.org) about deployment,
  licensing, and enterprise requirements.

## License

The contents of this repository are licensed under the
[Apache License 2.0](LICENSE.md). LedgerMind Integrations and Protocol are also
Apache-2.0. LedgerMind Local uses Business Source License 1.1, and LedgerMind
Core is proprietary. Consult the license included with each component before
use or redistribution.
