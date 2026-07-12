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
ledgermind install hermes --mode agent --enrichment openrouter --api-key <KEY> --language english
```

| Flag | Default | Options |
|------|---------|---------|
| `--mode` | `agent` | `agent` (structured summaries), `core` (full pipeline) |
| `--enrichment` | `openrouter` | `openrouter`, `nvidia`, `aistudio`, `custom` |
| `--api-key` | (prompts) | API key for the enrichment provider |
| `--base-url` | (auto) | Custom API endpoint URL |
| `--language` | `english` | `english`, `russian`, or any other language |

The installer automatically:
- Creates a venv with matching Python version
- Installs ledgermind into the venv
- Copies the plugin to Hermes
- Enables the plugin in config

### Step 3: Restart Hermes

After installation, restart Hermes to activate the plugin:
```
/restart
```

### Step 4: First session — automatic import

On the first conversation after installation, LedgerMind automatically:
1. Starts the HTTP server (`localhost:8000`)
2. Imports all existing Hermes sessions from `~/.hermes/state.db`
3. Each session is summarized by the enrichment model and stored
4. Sets `initial_import_done: true` — this runs only once

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
```

The plugin is a thin HTTP bridge. No direct imports of ledgermind. Works with any Python version.

## What Gets Installed

```
~/.hermes/plugins/ledgermind/
├── plugin.yaml      # Plugin manifest
├── __init__.py      # Plugin code (HTTP client)
├── config.json      # Provider, model, base_url
└── .env             # API key (LEDGERMIND_API_KEY)

~/.ledgermind/
├── venv/            # Python venv with ledgermind
└── hermes/
    ├── config.json  # Mode, language, enrichment settings
    └── <profile>/   # Per-profile memory storage
        ├── episodic.db  # Events (SQLite WAL)
        ├── semantic/    # Decisions (Markdown + Git)
        └── vectors.db   # Vector index
```

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
- **PATTERN**: Initial observation from interactions
- **EMERGENT**: Reinforced pattern with growing confidence
- **CANONICAL**: Stable, proven knowledge

The `LifecycleEngine` manages transitions based on temporal signals — no manual cleanup needed.

### 4. Self-Healing
- Conflict detection: finds contradictory decisions automatically
- Resolution: vector similarity supersedes outdated knowledge (>70% threshold)
- Decay: old, unused knowledge is archived and pruned
- Index rebuild: SQLite metadata reconstructed from source files if corrupted

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

**Background worker** (runs during session):
- Enrichment: LLM processes pending knowledge items (every 60s)
- Reflection: analyzes patterns, generates proposals (every 5min)
- Lifecycle: promotes knowledge through phases

## Configuration

| File | Purpose |
|------|---------|
| `~/.hermes/plugins/ledgermind/config.json` | Provider, model, base_url |
| `~/.hermes/plugins/ledgermind/.env` | API key (`LEDGERMIND_API_KEY`) |
| `~/.ledgermind/hermes/config.json` | Mode, language, enrichment settings |

## Profiles

Each Hermes profile (`hermes -p <name>`) gets isolated memory. The plugin detects the active profile automatically via `ctx.profile_name`. Your work memory doesn't mix with personal memory.

## First Run

On first session start, LedgerMind imports your existing Hermes sessions from `~/.hermes/state.db`:
1. Reads all past sessions and messages
2. Sends each to the enrichment model for structured summarization
3. Writes summaries to the knowledge base
4. Sets `initial_import_done: true` — runs only once

## Requirements

### System Requirements

- **OS**: Linux or macOS (Windows untested)
- **Python**: 3.10 or higher
- **Hermes Agent**: v0.18+ (with plugin system support)
- **Git**: Required for semantic memory audit trail
- **RAM**: ~600 MB (embedding model Jina v5 small Q4_K_M loads into memory on first use)
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
