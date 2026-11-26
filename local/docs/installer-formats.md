# Installer and knowledge formats

**Status:** reference for the Local installer and the knowledge path.

This is the single reference for **both** format layers: (1) install config,
secrets and agent hooks, and (2) the formats of the knowledge itself. It does
not contain secret values: every token field below is a name or a reference,
never a value.

## Legend

| Mark | Meaning |
| --- | --- |
| **DEFAULT** | Safe value chosen by the wizard without asking; may still be overridden explicitly. |
| **ASK** | Asked of the user during installation; not inferred from the host or from prompt text. |
| **ADVANCED** | Not part of the basic flow; available through `--config` / explicit advanced mode. |

---

## Layer 1 — install config, secrets and hooks

### Install config

| Format | Where it lives | DEFAULT / ASK / ADVANCED |
| --- | --- | --- |
| Installer input payload, JSON Schema draft 2020-12, `schema_version: 2`, `additionalProperties: false` | `installer/schema.py` (`INSTALL_CONFIG_SCHEMA`) and `local/schemas/install-config.schema.json`; validated by `InstallerConfig` (`extra="forbid"`) | **DEFAULT** `schema_version: 2`; legacy version 1 payloads with `target` migrate to version 2 instead of being rejected |
| Final installer config | `XDG_CONFIG_HOME/ledgermind/config.json` | **DEFAULT** written without token values; provider tokens become `secret_ref` entries |
| Provider profiles | `XDG_CONFIG_HOME/ledgermind/profiles.json` | **DEFAULT** profiles carry `secret_ref`, not token values |
| Local service config, `config_version: 2` | `XDG_CONFIG_HOME/ledgermind/local-config.json` and `XDG_DATA_HOME/ledgermind/local/config.json` | **DEFAULT** generated from the installer config |
| Workspace memory model | `memory_mode` in the installer config; JSON Schema enum has **exactly two** values, `shared` and `per_agent` | **DEFAULT** `shared`, identical in CLI and Web; **ASK** only when the user wants `per_agent`. This is a workspace-level choice, not a per-agent toggle. Both modes use one `rounds.db` and one Core `knowledge.db`; separation is logical, via `memory_space_id` (`shared-default` or `<agent>-default`) |
| Semantic language | `semantic_language` in the installer config | **ASK** one BCP-47 tag; never inferred from user text or the host locale |
| Agent integrations | `integrations` in the installer config | **ASK** which installed agents to connect; independent of the memory model |
| Provider endpoints, generation model and route, embedding model and dimensions (2048), `resolution_decision.backend=jev`, `reranker=disabled`, `runtime.residency_mode=session`, timeouts/retry/concurrency, internally generated tokens | generation / embedding / resolution / runtime blocks | **DEFAULT** safe values; provider tokens themselves are **ASK** |
| `embedding.mode` (`api` or `local`), custom provider endpoint/model, primary route, reranker fields when enabled, Jev/OpenRouter decision key | provider blocks | **ASK** only when relevant to the chosen provider |
| `max_concurrency`, `batch_size`, `timeout_seconds`, custom model / sha256 / runtime compatibility, TTL / lease / heartbeat, explicit `memory_data_path` | `advanced` block, `runtime` block, `--config` | **ADVANCED**; `memory_data_path` defaults to the XDG data root |

> Cloud API key is **not** an `InstallerConfig` field. It is entered into the
> hidden prompt of `ledgermind-cloud connect` and stored only in the cloud
> connector credential file (mode `0600`). It is not a provider token and not
> a BCP-47 value.

### Secrets

| Format | Where it lives | DEFAULT / ASK / ADVANCED |
| --- | --- | --- |
| JSON object `{"secrets": {"<ref>": "<value>"}}`, mode `0600`, atomic replace | `XDG_CONFIG_HOME/ledgermind/secrets.json` (`FileSecretStore`) | **ASK** provider tokens are written here under `secret_ref` keys; the wizard uses this file store |
| Secret references instead of inline values | `config.json` / `profiles.json` | **DEFAULT** `secret_ref`; alternative input forms for non-interactive installs: `token_env`, `token_stdin`, `secret_ref` |
| `SecretServiceStore` | available in the code | **ADVANCED** present but not used by the wizard |

### Agent hooks and bridge config

| Format | Where it lives | DEFAULT / ASK / ADVANCED |
| --- | --- | --- |
| Codex lifecycle hooks | `hooks.json` in the Codex config home | **DEFAULT** events installed for the selected agent |
| Claude Code lifecycle hooks | `settings.json` in the Claude config directory | **DEFAULT** events installed for the selected agent |
| OpenCode / OpenClaw plugins | `opencode.json` / `openclaw.json` plus a signed plugin payload | **DEFAULT** signed plugin plus private bridge config |
| Hermes plugin | `ledgermind-hermes` plugin root with `plugin.yaml`, `config.json` and hooks | **DEFAULT** signed plugin |
| Shared bridge config | `data/integrations/<id>/config.json` (or the Hermes plugin config) | **DEFAULT** `endpoint`, `token_file`, `memory_space_id`, `spool_dir`, `retrieval_schema_version: 5`, heartbeat / residency / session TTL fields |

---

## Layer 2 — knowledge formats

### Capture receipt (RawRound, schema version 2)

`POST /rounds` answers with schema version **2** and the fields `accepted`,
`status`, `raw_round_id`, `core_command_id`, `duplicate`, `core_raw_round_id`.

| HTTP result | Meaning |
| --- | --- |
| `202` | New round accepted for capture. |
| `200` | Duplicate: the round was already captured; it is not a second knowledge item. |
| `4xx` permanent / `429` quota / `5xx` or network | Not admitted; the delivery copy stays in the local spool. |

`round_acceptance_confirmed()` in the integrations runtime client is the
authoritative check: `accepted: true` or `status: "accepted"`, otherwise — for
schema version 2 — a non-empty `raw_round_id` together with `status` in
`queued_for_core`, `retry_wait` or `rejected`. An HTTP 2xx alone never proves
durable capture, and capture never proves that Core finished processing.

### Language and retrieval

| Format | Where it lives | DEFAULT / ASK / ADVANCED |
| --- | --- | --- |
| Semantic language, BCP-47 tag | `semantic_language` in the installer config; validated and canonicalized | **ASK** |
| Retrieval schema version **5** | `retrieval_schema_version: 5` in the bridge config; context requests accept schema version 2, 4 or 5 | **DEFAULT** version 5 (`scoped_dependencies` and semantic delivery are available there) |

### Core knowledge

The Local side owns `rounds.db` and writes raw rounds plus a `core_commands`
outbox; it never opens the Core `knowledge.db`. The next hop is the stdio IPC
`ingest_raw_round`, which requires `accepted: true`. After success the local
delivery copy is removed and the raw body is erased from `rounds.db`; Core then
owns the SR1 → SR2 → OR → KR → KG pipeline. If Core rejects the round, only
`rounds.db` holds a `rejected` record.

### Unified status vocabulary

```
local_pending → admitted → core_ingested → knowledge_ready
                    └────────→ rejected(local | core | quota)
```

| Status | Evidence |
| --- | --- |
| `local_pending` | Payload on disk in `pending-capture`, `ready-delivery`, `inflight` (TTL 300 s) or `failed` with `retryable=True`; transient retries have no ceiling |
| `admitted` | `202 + round_id` plus a confirming body (`round_acceptance_confirmed`) |
| `core_ingested` | IPC `ingest_raw_round` returned `accepted: true` |
| `knowledge_ready` | Core finished SR1 → SR2 → OR → KR → KG and knowledge is available |
| `rejected(local)` | Permanent 4xx → `failed/`, payload kept on the device; after 5 attempts / 24 h `retryable=False` but the payload is still kept for manual recovery |
| `rejected(core)` | Core did not accept the RawRound; `rounds.db` status `rejected`, body erased after the IPC step |
| `rejected(quota)` | `429 quota_exhausted` / `queue_full` returned **before** admission; the round stays on the device |

Two limits of this vocabulary matter: a `200` duplicate or a `202` admission is
**not** "knowledge ready", and `quota_exhausted` is **not** "accepted despite
the limit". In Cloud, a permanent 4xx from the backend produces `rejected` with
`payload=NULL`; "the data is preserved locally" always refers to the device
spool, never to Cloud. A `SpoolFullError` in Hermes can lose the turn — this is
a known risk, not a guarantee of perfect preservation.
