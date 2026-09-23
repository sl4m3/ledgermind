# ledgermind-local

`ledgermind-local` is the local LedgerMind service. It accepts structured
`RawRound` payloads, stores transport state, and communicates with the closed
Rust Core over IPC. Core owns the domain-level object-facet state and its
processing; Local performs only technical generic execution tasks.

## Trust boundaries and data ownership

- Local owns `rounds.db`: raw-round metadata and payloads, durable Core command
  delivery, retention state, inference profile metadata, technical profile-slot
  bindings, and the egress audit.
- Local **never opens the live `knowledge.db`**. Knowledge is accessible only
  through a supervised `CoreGateway` connected to the separate signed Rust
  process `ledgermind-core`; Core SQL and its migrations are not part of Local.
- Local does not import internal Core code and does not own Core storage.

## External APIs and egress

Local calls only external APIs whose endpoint and model were selected and
configured by the user. A payload sent by Local to a provider or a selected
Cloud endpoint may therefore leave the user's machine. Before enabling egress,
review the provider's endpoint, retention, region, and policy. Secrets are
addressed through the Local secret store and `secret_ref`; they are not bundled
with the package and must not appear in RawRound payloads, ordinary logs, or
backups.

## Readiness is deliberately split

### Capture-ready

Capture-ready means an integration can observe a completed round, create a
valid RawRound, and persist or deliver it without an enabled model provider.
In this mode, `rounds.db`, the durable spool, and repeatable delivery are the
critical components; temporary Core or provider unavailability must not destroy
captured data.

### Full-ready

Full-ready additionally requires:

- an available and verified signed `ledgermind-core` binary with its signature
  and public key;
- working Core IPC and a local `knowledge.db` in the Core directory;
- a user-configured inference endpoint and profile with the corresponding
  `secret_ref`;
- a ready generic execution worker and technical profile slots.

Capture-ready must not be reported as full-ready: capture and delivery may be
healthy while inference or Core is temporarily unavailable.

## Signed Core bundle

Local does not import a Python implementation of Core. For the process
boundary, build the Rust binary from the adjacent private `ledgermind-core`
workspace and place the signed bundle in `$LEDGERMIND_HOME/../core/bin/`:

```text
ledgermind-core
ledgermind-core.sig   # raw Ed25519 signature over the exact binary
ledgermind-core.pub   # raw 32-byte Ed25519 public key
```

For release signing, use `scripts/sign_core_binary.py` with a private key that
is not stored in the repository:

```bash
python scripts/sign_core_binary.py \
  --binary /path/to/ledgermind-core \
  --private-key "$LEDGERMIND_CORE_SIGNING_KEY" \
  --signature release/ledgermind-core.sig \
  --public-key release/ledgermind-core.pub
```

## Backup archive sensitivity

A backup archive must be treated as sensitive secret material. It may contain
raw conversation and tool payloads, inference metadata, the egress audit, and
opaque Core snapshot artifacts. Transfer an archive only through a trusted
channel, restrict its file permissions, encrypt it in transit and at rest, and
verify its source and integrity before restoring it. Never commit an archive to
the repository or include it in a public release artifact.

## Local development

```bash
pip install -e .[dev]
pytest -q
```

## Optional retrieval reranker

The setup wizard offers three explicit modes: disabled, API, or local. Existing
installations migrate to disabled/Core ranking unless they had already enabled
the local runtime. When enabled, Core first supplies up to 32 eligible
candidates and the selected reranker reorders only those candidates. Injection keeps
the first six complete knowledge items, then adds later complete items while
the rendered context fits the 400-token soft target. A long seventh item can
be skipped for a shorter eighth. A failed or timed-out reranker falls back to
Core order; `selection_diagnostics` reports the fallback. API credentials are
stored only in LedgerMind's private secret store. The endpoint must be the full
Cohere-compatible `/rerank` operation URL or NVIDIA NIM `/ranking` or
`/reranking` URL.

The reranker runtime is a separate downloadable, signed archive, not part of
the main platform bundle. Download its `.tar.zst`, `.json`, and `.sig` files
together. Install with `scripts/install-reranker-runtime.py`, passing the
installed release's `signatures/manifest.pub` as `--trusted-public-key` and a
new private `--destination`. The installer verifies the signature, archive
size and SHA-256 before extraction, and rejects unsafe archive members. Set
`reranker.runtime_path` to that destination and `reranker.model_path` to its
`model/snapshots/<pinned-revision>` directory. Use
`scripts/smoke-reranker-runtime.py` for an offline inference check. Source
installs can instead use `pip install -e '.[reranker]'`. Inference never calls a
model provider or downloads files in local mode; the main Local service does
not import PyTorch. The wizard exposes CPU, NVIDIA CUDA, and AMD ROCm choices.

## Docker

Build from the LedgerMind workspace root because Core, Local,
and protocol live in adjacent directories. Rust Core is compiled in a separate
multi-stage builder; the legacy Python runtime is not included in the image:

```bash
cd /path/to/ledgermind
docker build -f ledgermind-engine/ledgermind-local/Dockerfile \
  -t ledgermind-local .
```

The image intentionally does not generate a signature. Before starting it,
mount the signature and public key for the binary produced by the same Docker
build. The entrypoint fails closed if either signature file is missing;
`verify_core_signature` remains enabled.

## Compatibility

Legacy contract payloads are migrated once before Local workers start. Legacy
runtime routes, operation names and aliases are not supported; new capture
arrives through Integrations. Local executes Core-owned generic tasks and does
not own `HypothesisCandidate`, `MemoryObject`, `Target`, `Facet`, Merge, or
Replace semantics. The application Core coordinator owns those decisions;
Local only transports provider work and reports opaque results.

## Install on Linux

The current release supports rootless Linux installation. The installer uses
one configuration engine for the interactive wizard and agent-driven JSON
installs. It accepts only an
OpenAI-compatible generation API and either an OpenAI-compatible embeddings
API or a signed local CPU/GPU model catalog entry:

```bash
curl -fsSL https://github.com/sl4m3/ledgermind/releases/latest/download/install.sh | sh
ledgermind install schema --json
ledgermind integrations discover --json
ledgermind integrations status --json
ledgermind doctor --json
ledgermind runtime status --json
```

Without arguments, `install.sh` starts a navigable terminal wizard (with a
line-mode fallback for restricted terminals and SSH). It checks the Linux
host, lets the user choose English, Spanish, German, French, Russian, or any
custom BCP-47 memory language, detects agents, selects shared or per-agent
memory, and then configures generation, embeddings, and the optional reranker.
One generation model is
used throughout the complete knowledge pipeline; there is no separate Object
Resolution model prompt. The token is entered privately and displayed only as
a masked fingerprint during review. Nothing is installed before confirmation.
Provider credentials and persisted configuration are private (`0600`).

Use a generation model with at least 120B parameters. Its provider endpoint
must implement strict JSON Schema structured outputs; plain JSON mode is not a
substitute. All full provider-backed benchmark and integration runs reported
for the current implementation used the tested reference model
`deepseek/deepseek-v4-flash-0731`. Alternative models are supported only when
they satisfy the same capability requirements. The installer verifies strict
structured-output support with a real provider probe. For OpenRouter it queries
the selected model's current endpoints, lists only providers advertising
strict structured outputs, and lets the user choose one primary route and at
most one fallback. The same restricted route chain and
`require_parameters=true` are used during the probe and every production
request; automatic provider routing is disabled. A capability verified on one
model/route cannot be reused after either changes.

Provider recovery is deliberately bounded. If a successful HTTP response
contains JSON that does not satisfy the requested strict schema, Local rejects
it before Core and makes at most one retry. With two configured OpenRouter
routes, that retry selects the fallback route while preserving the exact model,
prompt, and schema. A second invalid response fails the task; Local never edits
or guesses semantic output.

API embedding dimensions are detected from an actual vector response rather
than entered by hand. Releases that include the signed local catalog also
offer `nvidia/Nemotron-3-Embed-1B-BF16` (2048 dimensions) on CPU, NVIDIA CUDA,
or AMD ROCm. Model files are pinned to an upstream revision and verified by
size and SHA-256; the matching device runtime is part of the signed release.

An agent can run the same installation non-interactively. It should first
collect the deployment choices from the user, write the current-schema JSON,
then execute one command and consume its machine-readable result:

```bash
curl -fsSL https://github.com/sl4m3/ledgermind/releases/latest/download/install.sh \
  | sh -s -- install --non-interactive --config /secure/install.json --json
```

Provider credentials should be supplied through `token_env`, `token_stdin`, or
an existing `secret_ref`; the persisted installer config never contains the
token value. One platform installation may connect several agent integrations.
Set `memory_mode` to `shared` to give those agents one knowledge space, or to
`per_agent` to keep their knowledge separate. The interactive wizard asks for
the same choice and defaults to `per_agent` for compatibility.
Their lifecycle is independent from the platform transaction:

```bash
ledgermind integrations discover
ledgermind integrations connect hermes
ledgermind integrations connect codex
ledgermind integrations connect claude-code
ledgermind integrations connect opencode
ledgermind integrations connect openclaw
ledgermind integrations status
ledgermind integrations disable hermes --json
ledgermind integrations enable hermes --json
ledgermind integrations disconnect hermes --json
```

Cursor integration is retained as experimental code but is not part of the
current Linux acceptance matrix; it will be validated separately. The other
listed agents have dedicated lifecycle adapters. Human-readable `discover`,
`status`, and `connect` output identifies the detected installation, hook
verification, memory space, and any activation step. Add `--json` for
automation.

The states are intentionally distinct: `installed` means the LedgerMind
platform exists, `connected` means an adapter is registered, `enabled` means it
will attach to future agent sessions, and `active` means the installed adapter
is enabled and has no remaining activation step. Codex CLI requires the user to
review and trust newly installed hooks with `/hooks`; status reports this step
instead of claiming that the integration is active. A failed agent connection
returns a partial result and never rolls back a successfully verified platform
installation.

Install data follows XDG directories. Signed manifests, bundle artifacts,
Core, model files, and embedding runtimes are verified before `current` is
switched. The installer asks how local embedding and reranker models should
remain resident. `Session` (the default) holds one crash-safe lease from prompt
recall through the agent's final response, so a long-running turn does not
unload and reload the models. `Idle timeout` keeps them warm for 5, 10, 15, or
30 minutes after work, while `Always on` disables automatic shutdown. The
session safety TTL releases abandoned leases after a crashed agent. Ordinary
uninstall preserves user memory, configuration, and secrets.

### Existing installations

Running the installer again never silently replaces provider settings. The
interactive installer requires one explicit action:

1. **Add an agent** connects one or more detected agents and leaves generation,
   embeddings, memory mode, storage, and existing integrations unchanged.
2. **Update LedgerMind** installs the current signed release while preserving
   provider configuration, agents, and memory.
3. **Repair** restores binaries, links, permissions, and already-selected
   integrations, then runs diagnostics. It does not select new models.
4. **Reconfigure providers** probes and replaces generation, embedding, and
   reranker profiles. Memory, agents, language, runtime settings, and storage
   remain unchanged.
5. **Exit** makes no changes.

The same actions are available without prompts:

```bash
ledgermind install --existing-mode add-agent --agent opencode --non-interactive
ledgermind install --existing-mode update --non-interactive
ledgermind install --existing-mode repair --non-interactive
ledgermind install --existing-mode reconfigure \
  --non-interactive --config /secure/providers.json
```

For OpenRouter, generation roles use one ordered route chain: one required
primary provider and, optionally, one fallback. Embeddings are configured by
endpoint and model only; they do not inherit the generation provider chain.

### Updates and removal

An update consumes a signed manifest and bundle but always reuses the installed
provider identities, secrets, memory configuration, and selected agents. Use
explicit provider reconfiguration when those values must change:

```bash
ledgermind update --manifest install-manifest.json --bundle release.tar.zst
ledgermind doctor
```

Default removal disconnects hooks and removes installed release binaries while
preserving configuration, secrets, models, and knowledge data. Before removal
it writes a private backup of the memory directory and prints its location.
Destructive removal must be requested explicitly:

```bash
ledgermind uninstall
ledgermind uninstall --purge-data --purge-config --yes
```
