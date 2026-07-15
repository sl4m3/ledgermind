---
name: ledgermind
description: Autonomous memory for AI agents — long-term memory, knowledge base, context injection, and persistent learning. Use when user asks about memory, past decisions, context injection, persistent learning, knowledge management, semantic memory, episodic memory, vector search, memory setup, or "what did we do before". Also trigger on "remember this", "search my knowledge", "set up memory", "recall context", "memory system".
---

# LedgerMind

> Not a memory store — a living knowledge core that thinks, heals itself, and evolves.

LedgerMind is an autonomous knowledge lifecycle manager. It doesn't just store information — it reasons about it, detects conflicts, merges duplicates, and promotes knowledge through lifecycle phases without human intervention.

## Installation

### Step 1: Install the package

**Using uv** (recommended — auto-manages venv):
```bash
uv pip install ledgermind
```

**Using pip** (Linux requires venv due to PEP 668):
```bash
python3 -m venv ~/.ledgermind/venv
~/.ledgermind/venv/bin/pip install ledgermind
```

### Step 2: Install the plugin for Hermes

**Interactive mode** (asks questions):
```bash
ledgermind install hermes
```

**Non-interactive mode** (for agents — collect answers first, then run one command):
```bash
ledgermind install hermes --mode agent --enrichment openrouter --api-key <KEY> --language english --import-limit 1000
```

| Flag | Default | Options |
|------|---------|---------|
| `--mode` | `agent` | `agent` (structured summaries), `core` (full pipeline) |
| `--enrichment` | `openrouter` | `openrouter`, `nvidia`, `aistudio`, `custom` |
| `--api-key` | (prompts) | API key for the enrichment provider |
| `--base-url` | (auto) | Custom API endpoint URL |
| `--language` | `english` | `english`, `russian`, or any other language |
| `--import-limit` | **required** | `0` = skip import, `-1` = all events, `N` = last N events |
| `--gpu-layers` | `0` | `0` = CPU only, `99` = all layers on GPU (CUDA required) |

**Non-interactive mode requires `--import-limit`**. To determine the right value:
1. Check state.db: `sqlite3 ~/.hermes/state.db "SELECT COUNT(*) FROM messages"`
2. Ask the user how many recent events to import
3. Pass the answer as `--import-limit`

Example agent workflow:
```
Agent: "Your Hermes has 22,673 messages. How many recent events should I import?
        1. Last 1,000 (quick start)
        2. Last 5,000
        3. Last 10,000
        4. All"
User: "1,000"
Agent: ledgermind install hermes --mode agent --enrichment openrouter --api-key sk-... --import-limit 1000
```

The installer automatically:
- Creates a venv with matching Python version
- Installs ledgermind into the venv
- Copies the plugin to Hermes
- Enables the plugin in config
- Saves import_limit to config.json

### Step 3: Restart Hermes

After installation, restart Hermes to activate the plugin:
```
/restart
```

### Step 4: Import events

Trigger the import via API:
```bash
curl -X POST http://localhost:8000/import/state-db -H "Content-Type: application/json" -d '{"profile":"default"}'
```

The server imports events based on the `import_limit` from config.json (set during installation). You can override with `{"limit": 5000}` in the request body.

After import:
1. Events are stored in episodic memory
2. Enrichment worker processes them into structured knowledge
3. Sets `initial_import_done: true`

### Step 5: Use normally

That's it. LedgerMind now:
- Injects relevant context before every LLM turn
- Records every interaction for future learning
- Maintains knowledge in the background

## Architecture

```
Hermes / OpenClaw / any agent
  └── plugin (HTTP client, ~100 lines)
        ↓ HTTP localhost:8000
LedgerMind FastAPI server (separate process)
  ├── /memory/search
  ├── /memory/write
  ├── /worker/start
  └── /worker/stop

Storage:
  - Raw events: agent DB (state.db) — NOT copied
  - Knowledge items: semantic store (proposals with phases)
  - Embeddings: vector index
```

The plugin is a thin HTTP bridge. No direct imports of ledgermind. Works with any Python version.

## What Gets Installed

```
~/.hermes/plugins/ledgermind/
├── plugin.yaml      # Plugin manifest
├── __init__.py      # Plugin code (HTTP client)
└── .env             # API key (LEDGERMIND_API_KEY)

~/.ledgermind/
├── venv/            # Python venv with ledgermind
└── hermes/
    ├── config.json  # Mode, language, enrichment, import_limit
    └── <profile>/   # Per-profile memory storage
        ├── semantic/         # Knowledge items (Markdown + Git)
        │   └── semantic_meta.db  # Knowledge item metadata
        ├── vector_index/     # Vector index
        │   ├── vectors.npy   # Embeddings
        │   ├── vectors.ann   # Annoy index
        │   └── vector_meta.json
        └── models/
            └── v5-small-text-matching-Q4_K_M.gguf  # Embedding model (~379MB)
```

**Note:** Raw events stay in agent DB (state.db). No episodic store needed.

## What It Does

### 1. Context Injection (pre_llm_call)
Before every LLM turn, LedgerMind searches your knowledge base and injects relevant context into the prompt. The agent sees:
```
[LEDGERMIND KNOWLEDGE BASE ACTIVE]
- Use PostgreSQL for main DB (database): ACID compliance, JSONB support [score: 0.92]
- API rate limiting at 100 req/min (api): Set in v2.3, never exceeded [score: 0.87]
```

### 2. Interaction Recording (post_llm_call)
After every LLM turn, the interaction is recorded. In `agent` mode, the model produces a structured JSON summary. In `core` mode, raw data goes through the full pipeline.

### 3. Autonomous Lifecycle
Knowledge evolves through three phases:
- **PATTERN**: Initial observation from interactions (easy merge)
- **EMERGENT**: Reinforced pattern with growing confidence (medium merge)
- **CANONICAL**: Stable, proven knowledge (hard merge)

The `LifecyclePipeline` manages transitions: Merge → Decay → Promote.

### 4. Self-Healing
- Profile gate: different profiles don't merge (hermes/openclaw isolation)
- Session boost: same session items get merge priority
- Phase-aware merge: PATTERN easy (0.5), CANONICAL hard (0.7)
- Decay: confidence-based removal with superseded protection
- Integrity rules: I1-I5 prevent data corruption

## Performance

| Metric | LedgerMind | Zep | Mem0 |
|--------|------------|-----|------|
| Recall@5 | **100%** | ~85% | ~80% |
| Search latency | **0.33ms** | ~100ms | ~50ms |
| Write throughput | **141 ops/s** | ~10-50 | ~5-20 |

Tested on LoCoMo (1000 dialogues) and LongMemEval (500 sessions).

## How It Works

```
User message → pre_llm_call → HTTP /memory/search → Inject context → LLM responds
                                                               ↓
                                              post_llm_call → HTTP /memory/write → Background worker processes
```

**Background worker** (runs every 5 minutes):
- Merge: finds similar knowledge items, claims candidates, executes supersede
- Decay: confidence-based removal, vitality transitions
- Promote: advances knowledge through phases (PATTERN → EMERGENT → CANONICAL)

## Configuration

| File | Purpose |
|------|---------|
| `~/.hermes/plugins/ledgermind/.env` | API key (`LEDGERMIND_API_KEY`) |
| `~/.ledgermind/hermes/config.json` | Mode, language, enrichment, import_limit |
| `~/.ledgermind/hermes/<profile>/models/` | Embedding model (auto-downloaded) |

### config.json

```json
{
  "default_mode": "agent",
  "language": "english",
  "import_limit": 1000,
  "gpu_layers": 0,
  "enrichment": {
    "provider": "openrouter",
    "model": "nvidia/nemotron-3-super-120b-a12b:free",
    "base_url": "https://openrouter.ai/api/v1"
  }
}
```

- `gpu_layers: 0` — CPU only (default)
- `gpu_layers: 99` — all layers on GPU (requires CUDA)

## Profiles

Each Hermes profile (`hermes -p <name>`) gets isolated memory. The plugin detects the active profile automatically via `ctx.profile_name`. Your work memory doesn't mix with personal memory.

## First Run

After installation:
1. Start the LedgerMind server (plugin does this automatically)
2. Trigger import: `POST /import/state-db` (uses `import_limit` from config)
3. Raw events stay in agent DB (state.db)
4. Enrichment creates knowledge items (proposals with phases)
5. Lifecycle pipeline: Merge → Decay → Promote
6. Knowledge evolves through PATTERN → EMERGENT → CANONICAL

## Requirements

### System Requirements

- **OS**: Linux or macOS (Windows untested)
- **Python**: 3.10 or higher
- **Hermes Agent**: v0.18+ (with plugin system support)
- **Git**: Required for semantic memory audit trail
- **RAM**: ~1 GB (embedding model Jina v5 small Q4_K_M loads into memory on first use)
- **CPU**: No special requirements — runs on any modern processor
- **Disk space**: ~50 MB for dependencies + growing memory storage (~1 MB per 1000 conversations)

### Required

| Requirement | Why | How to get |
|-------------|-----|------------|
| **Enrichment API key** | LLM summarizes and structures your knowledge | Free tier on [OpenRouter](https://openrouter.ai/keys) |
| **Hermes Agent** | Plugin system, state.db for import | `pip install hermes-agent` or [GitHub](https://github.com/NousResearch/hermes-agent) |
| **Python 3.10+** | Core runtime | `python3 --version` to check |

### Optional

| Requirement | Why |
|-------------|-----|
| **NVIDIA API key** | Alternative enrichment provider (free tier) |
| **Google AI Studio key** | Alternative enrichment provider (free tier) |
| **Custom LLM endpoint** | Self-hosted or proxied models via `--base-url` |

## Links

- GitHub: https://github.com/sl4m3/ledgermind
- PyPI: https://pypi.org/project/ledgermind/
- Docs: https://github.com/sl4m3/ledgermind/tree/main/docs

## Pre-flight Check

Before installing, verify your system is ready:

```bash
# Check Python version (need 3.10+)
python3 --version

# Check Hermes is installed
hermes --version

# Check Git is available
git --version

# Check state.db exists (for import)
ls -la ~/.hermes/state.db
```

If any check fails, install the missing component before proceeding.
