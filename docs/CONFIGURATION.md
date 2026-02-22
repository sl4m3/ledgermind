# Configuration Reference

All configuration parameters for LedgerMind, with defaults and guidance on tuning.

---

## LedgermindConfig

The primary configuration object. Pass it to `Memory(config=...)`.

```python
from ledgermind.core.core.schemas import LedgermindConfig, TrustBoundary

config = LedgermindConfig(
    storage_path="./memory",
    ttl_days=30,
    trust_boundary=TrustBoundary.AGENT_WITH_INTENT,
    namespace="default",
    vector_model="jinaai/jina-embeddings-v5-text-nano",
    enable_git=True,
    relevance_threshold=0.35,
)
memory = Memory(config=config)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `storage_path` | `str` | `./memory` | Root directory for all storage. Must be writable. |
| `ttl_days` | `int ≥ 1` | `30` | Days before episodic events (without immortal links) are archived. |
| `trust_boundary` | `TrustBoundary` | `AGENT_WITH_INTENT` | Controls who can write to semantic memory. See Trust Boundaries. |
| `namespace` | `str` | `default` | Logical namespace for multi-tenant isolation. |
| `vector_model` | `str` | `jinaai/jina-embeddings-v5-text-nano` | Any `sentence-transformers` model name. |
| `enable_git` | `bool` | `True` | Whether to use Git for audit. Falls back to `NoAuditProvider`. |
| `relevance_threshold` | `float [0..1]` | `0.35` | Minimum search score for `IntegrationBridge.get_context_for_prompt()`. |

---

## Trust Boundaries

| Value | Effect |
|---|---|
| `AGENT_WITH_INTENT` | Default. Agents can read and write decisions freely. |
| `HUMAN_ONLY` | Agent-sourced `decision` writes are silently blocked at the router. Only `user` and `system` sources can write to semantic memory. |

---

## ReflectionPolicy

Controls how the `ReflectionEngine` generates and evaluates proposals. Pass to `ReflectionEngine(policy=...)` or use defaults.

```python
from ledgermind.core.reasoning.reflection import ReflectionEngine, ReflectionPolicy

policy = ReflectionPolicy(
    error_threshold=1,
    success_threshold=2,
    min_confidence=0.3,
    observation_window_hours=1,
    decay_rate=0.05,
    ready_threshold=0.6,
    auto_accept_threshold=0.9,
)
```

| Parameter | Default | Description |
|---|---|---|
| `error_threshold` | `1` | Minimum number of errors on a target to trigger hypothesis generation. Lower = more proposals. |
| `success_threshold` | `2` | Number of successes required to generate a Best Practice proposal. |
| `min_confidence` | `0.3` | Below this, proposals are auto-rejected during decay. |
| `observation_window_hours` | `1` | Minimum time window before a proposal can become `ready_for_review`. |
| `decay_rate` | `0.05` | Confidence reduction per cycle (5%) when no new evidence arrives. |
| `ready_threshold` | `0.6` | Confidence required to mark a proposal `ready_for_review=True`. |
| `auto_accept_threshold` | `0.9` | Confidence at which a `ready_for_review` proposal is auto-accepted (if `objections=[]`). |

**Tuning guidance:**
- Set `error_threshold=3` for noisy environments where individual errors are not significant
- Increase `observation_window_hours=24` for slower-moving codebases
- Set `auto_accept_threshold=1.1` (impossible) to disable auto-acceptance and always require human review

---

## DecayEngine

Controls memory forgetting behavior.

```python
from ledgermind.core.reasoning.decay import DecayEngine

decay = DecayEngine(
    ttl_days=30,
    semantic_decay_rate=0.05,
    forget_threshold=0.1,
)
```

| Parameter | Default | Description |
|---|---|---|
| `ttl_days` | `30` | Days until episodic events (without immortal links) are archived. |
| `semantic_decay_rate` | `0.05` | Weekly confidence reduction for inactive semantic records. Proposals: full rate. Decisions/Constraints: rate÷3. |
| `forget_threshold` | `0.1` | Records with `confidence < forget_threshold` are hard-deleted via `forget()`. |

**Tuning guidance:**
- Set `ttl_days=90` for long-running projects where historical context is valuable
- Set `forget_threshold=0.05` to be more conservative about deleting knowledge
- Set `semantic_decay_rate=0.0` to disable semantic decay entirely

---

## BackgroundWorker

Controls the autonomous heartbeat in MCP mode.

```python
from ledgermind.server.background import BackgroundWorker

worker = BackgroundWorker(
    memory=memory,
    interval_seconds=300,  # Main loop interval (5 minutes)
)
worker.start()
```

| Parameter | Default | Description |
|---|---|---|
| `interval_seconds` | `300` | Main heartbeat interval in seconds. |

**Internal sub-intervals (hardcoded):**
- Reflection cycle: every `14400` seconds (4 hours)
- Decay cycle: every `3600` seconds (1 hour)
- Git sync: every main cycle
- Health check: every main cycle
- Stale lock threshold: `600` seconds (10 minutes)

---

## MCPServer Capabilities

Control which operations MCP clients can perform.

```bash
ledgermind-mcp run --capabilities '{"read":true,"propose":true,"supersede":true,"accept":true,"sync":true,"purge":false}'
```

| Capability | Default | Controls |
|---|---|---|
| `read` | `true` | `search_decisions`, `get_memory_stats`, `get_environment_health`, `get_audit_logs`, `visualize_graph`, `get_api_specification`, `get_relevant_context` |
| `propose` | `true` | `record_decision`, `record_interaction` |
| `supersede` | `true` | `supersede_decision`, `link_interaction_to_decision` |
| `accept` | `true` | `accept_proposal` |
| `sync` | `true` | `sync_git_history` |
| `purge` | `false` | `forget_memory`, `export_memory_bundle` |

---

## Vector Search

Vector search is optional. It is enabled when `sentence-transformers` is installed:

```bash
pip install ledgermind[vector]
```

Without vector search:
- `search_decisions()` falls back to keyword-only search
- Auto-Supersede similarity check is skipped (conflicts always raise `ConflictError`)
- Reflection Engine still works, but without vector-based clustering

**Choosing a vector model:**

| Model | Dimensions | Size | Notes |
|---|---|---|---|
| `jinaai/jina-embeddings-v5-text-nano` | 512 | ~150MB | **Standard.** Best precision for research/mobile. |
| `all-MiniLM-L6-v2` | 384 | 80MB | Legacy default. Fast and reliable. |
| `all-mpnet-base-v2` | 768 | 420MB | Higher quality, slower. |
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | 120MB | Multi-language support. |

---

## Git Configuration

LedgerMind uses your system Git configuration. Ensure it is set up before starting:

```bash
git config --global user.name "LedgerMind Agent"
git config --global user.email "agent@example.com"
```

If Git is not installed, LedgerMind falls back to `NoAuditProvider`: files are still written to disk, but there is no version history. All other functionality works normally.

---

## Environment Health Thresholds

`check_environment()` checks these conditions automatically on startup:

| Check | Threshold | Effect on failure |
|---|---|---|
| Disk space | < 50 MB free | Warning (not an error) |
| Git availability | `git --version` fails | Error |
| Git user config | Missing name or email | Warning |
| Storage permissions | Not writable | Error |
| Lock file | Exists | Warning with owner PID |

---

## Multi-Tenant Namespaces

Use `namespace` to isolate memory between different agents or projects sharing the same storage path:

```python
agent_a = Memory(storage_path="./shared_memory", namespace="agent_a")
agent_b = Memory(storage_path="./shared_memory", namespace="agent_b")

# Decisions are stored in different namespace directories
# Conflict checks are scoped per namespace
# Search returns results from the current namespace only
```
