# Configuration Reference

All configuration parameters for LedgerMind, with defaults and guidance on 
tuning.

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
    vector_model=".ledgermind/models/2.7.9-small-text-matching-Q4_K_M.gguf",
    vector_workers=0, # Auto-detect for multiprocessing
    relevance_threshold=0.35,
)
memory = Memory(config=config)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `storage_path` | `str` | `./memory` | Root directory for all storage. |
| `ttl_days` | `int ≥ 1` | `30` | Days before episodic events are archived. |
| `trust_boundary` | `Enum` | `AGENT_WITH_INTENT` | Who can write to semantic memory. |
| `namespace` | `str` | `default` | Logical partition for multi-tenant isolation. |
| `vector_model` | `str` | *path* | Local path to `.gguf` file or HF model ID. |
| `vector_workers` | `int` | `0` | Workers for multi-process encoding (0=auto). |
| `relevance_threshold` | `float` | `0.35` | Minimum score for RAG context injection. |

---

## GGUF / 4-bit Quantization

LedgerMind is optimized for constrained environments like **Termux/Android**. 
It supports 4-bit quantization via `llama-cpp-python`.

**To use 4-bit mode:**
1.  Install the requirement: `pip install llama-cpp-python`
2.  Set `vector_model` to a local path ending in `.gguf`.
3.  The system automatically switches to the high-efficiency engine.

---

## Arbitration (Gray Zone)

When recording a decision that is similar to an existing one, LedgerMind uses 
a threshold-based policy:

| Similarity | Action |
|---|---|
| **> 0.70** | **Auto-Supersede:** The old record is replaced automatically. |
| **0.50 – 0.70** | **Gray Zone:** Calls `arbiter_callback` (your LLM logic). |
| **< 0.50** | **Conflict:** Raises `ConflictError` (different topics). |

---

## Environment Variables

| Variable | Description |
|---|---|
| `LEDGERMIND_API_KEY` | Enables API-key authentication for MCP and REST. |

---

## MCPServer Capabilities

Control which operations MCP clients can perform.

```bash
ledgermind-mcp run --capabilities '{"read":true,"propose":true,"supersede":true}'
```

| Capability | Default | Description |
|---|---|---|
| `read` | `true` | Search, stats, graph, api-spec. |
| `propose` | `true` | Record new decisions. |
| `supersede` | `true` | Replace old decisions. |
| `sync` | `true` | Sync git history. |
| `purge` | `false` | Forget memories (hard delete). |

---

## Vector Search Models

| Model | Dimensions | Size | Notes |
|---|---|---|---|
| **Jina 2.7.9 Small GGUF** | **1024** | **~400MB** | **Recommended.** Best CPU performance. |
| `all-MiniLM-L6-2.7.9` | 384 | 80MB | Legacy default. Very fast. |
| `all-mpnet-base-2.7.9` | 768 | 420MB | Higher quality, slower. |

---

## Git Configuration

Ensure your Git identity is set up before using audit features:

```bash
git config --global user.name "LedgerMind Agent"
git config --global user.email "agent@example.com"
```

---

## Client Hooks Configuration

LedgerMind supports Zero-Touch Automation through client-side hooks. These hooks automatically manage context injection (RAG) and episodic memory recording.

### Automatic Installation

Use the CLI to install hooks for supported clients:

```bash
ledgermind-mcp install [claude|cursor|gemini] --path /path/to/memory
```

### Manual Configuration (Gemini CLI)

If you need to manually configure hooks for Gemini CLI (v0.29.7+), add the following to your `~/.gemini/settings.json`:

```json
{
  "hooksConfig": {
    "enabled": true,
    "notifications": true
  },
  "hooks": {
    "BeforeAgent": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "name": "ledgermind-context",
            "type": "command",
            "command": "python3 /path/to/ledgermind/hooks/ledgermind_hook.py before"
          }
        ]
      }
    ],
    "AfterAgent": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "name": "ledgermind-record",
            "type": "command",
            "command": "python3 /path/to/ledgermind/hooks/ledgermind_hook.py after"
          }
        ]
      }
    ]
  }
}
```

> **Note:** The hook script must be able to import `ledgermind`. Ensure the project's `src` directory is in your `PYTHONPATH` or the package is installed in your environment.
