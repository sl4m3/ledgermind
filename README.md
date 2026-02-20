# LedgerMind

**v2.6.0** · Autonomous Memory Management System for AI Agents

> *LedgerMind is not a memory store — it is a living knowledge core that thinks, heals itself, and evolves without human intervention.*

[![License: NCSA](https://img.shields.io/badge/License-NCSA-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green)](https://modelcontextprotocol.io)

---

## What is LedgerMind?

Most AI memory systems are passive stores: you write, you read, and if the information becomes stale or contradictory — that is your problem. LedgerMind takes a fundamentally different approach.

LedgerMind is an **autonomous knowledge lifecycle manager**. It combines a hybrid storage engine (SQLite + Git) with a built-in reasoning layer that continuously monitors knowledge health, detects conflicts, distills raw experience into structured rules, and repairs itself — all in the background, without any intervention from the developer or the agent.

### Core Capabilities

| Capability | Description |
|---|---|
| **Autonomous Heartbeat** | A background worker runs every 5 minutes: Git sync, reflection, decay, self-healing. |
| **Intelligent Conflict Resolution** | Vector similarity analysis automatically supersedes outdated decisions (threshold: 85%). |
| **Canonical Target Registry** | Auto-normalizes target names and resolves aliases to prevent memory fragmentation. |
| **Autonomous Reflection** | Proposals with confidence ≥ 0.9 are automatically promoted to active decisions. |
| **Hybrid Storage** | SQLite for fast queries + Git for cryptographic audit and version history. |
| **MCP Server** | 15 tools for any compatible client (Claude, Gemini CLI, custom agents). |
| **REST Gateway** | FastAPI endpoints + Server-Sent Events + WebSocket for real-time updates. |
| **Epistemic Safety** | The Reflection Engine distinguishes facts from hypotheses using scientific falsification. |

---

## Architecture at a Glance

```text
+-------------------------------------------------------------+
|                       LedgerMind Core                       |
|                                                             |
|  +---------------+    +---------------+    +---------------+ |
|  │  Integration  │    │    Memory     │    │  MCP / REST   │ |
|  │    Bridge     │--->│  (main API)   │<---│    Server     │ |
|  +---------------+    +-------+-------+    +---------------+ |
|                               |                              |
|           +-------------------+-------------------+          |
|           |                   |                   |          |
|           v                   v                   v          |
|  +---------------+    +---------------+    +---------------+ |
|  │   Semantic    │    │   Episodic    │    │ Vector Index  │ |
|  │     Store     │    │     Store     │    │ (NumPy/FAISS) │ |
|  │  (Git + MD)   │    │   (SQLite)    │    │               │ |
|  +---------------+    +---------------+    +---------------+ |
|                                                             |
|  +--------------------- Reasoning Layer ------------------+  |
|  │  ConflictEngine * ResolutionEngine * ReflectionEngine  │  │
|  │  DecayEngine * MergeEngine * DistillationEngine        │  │
|  +---------------------------------------------------------+  |
|                                                             |
|  +------------------ Background Worker ------------------+   |
|  │     Health Check * Git Sync * Reflection * Decay       │   │
|  +--------------------------------------------------------+   |
+-------------------------------------------------------------+
```

---

## Installation

```bash
# Basic install
pip install ledgermind

# With vector search (recommended — enables semantic conflict resolution)
pip install ledgermind[vector]

# Development setup
pip install -e .[dev]
```

**Requirements:** Python 3.10+, Git installed and configured in PATH.

---

## Quick Start

### Option A: Library (Direct Integration)

```python
from ledgermind.core.api.bridge import IntegrationBridge

bridge = IntegrationBridge(memory_path="./memory")

# Inject relevant context into your agent's prompt
context = bridge.get_context_for_prompt("How should we handle database migrations?")

# Record the interaction for future reflection
bridge.record_interaction(
    prompt="How should we handle database migrations?",
    response="Use Alembic with a dedicated migrations/ folder...",
    success=True
)

# Record a structured decision
bridge.memory.record_decision(
    title="Use Alembic for all database migrations",
    target="database_migrations",
    rationale="Alembic provides version-controlled, reversible migrations compatible with SQLAlchemy."
)
```

### Option B: MCP Server

```bash
# Initialize a new memory project
ledgermind-mcp init --path ./memory

# Start the MCP server
ledgermind-mcp run --path ./memory
```

Then add to your Claude Desktop / Gemini CLI MCP configuration:

```json
{
  "mcpServers": {
    "ledgermind": {
      "command": "ledgermind-mcp",
      "args": ["run", "--path", "./memory"]
    }
  }
}
```

---

## Key Workflows

### Workflow 1: Auto-Supersede — Update Without Knowing the Old ID

```python
# First decision
memory.record_decision(
    title="Use PostgreSQL",
    target="database",
    rationale="PostgreSQL provides ACID transactions and JSON support."
)

# Later — just record the updated decision for the same target.
# If vector similarity > 85%, LedgerMind automatically supersedes the old one.
memory.record_decision(
    title="Use Aurora PostgreSQL",
    target="database",
    rationale="Aurora PostgreSQL adds auto-scaling and built-in replication."
)
# ✓ Old decision is now status=superseded, linked to the new one.
```

### Workflow 2: Self-Evolution — From Raw Experience to Rules

```
1. [Background Worker] Indexes your Git commits into episodic memory every 5 min
2. [Reflection Engine]  Detects recurring errors in a target area → creates a Proposal
3. [Auto-Acceptance]    If confidence ≥ 0.9 and no objections → Proposal becomes active Decision
```

### Workflow 3: Self-Healing — Automatic Recovery

```
1. Process crashes → leaves .lock file in semantic store
2. [Background Worker] Detects lock age > 10 minutes
3. [Self-Healing]       Automatically removes stale lock and runs sync_meta_index()
```

---

## Project Structure

```
src/ledgermind/
├── core/
│   ├── api/
│   │   ├── bridge.py         # IntegrationBridge — high-level facade
│   │   ├── memory.py         # Memory — main orchestrator
│   │   └── transfer.py       # MemoryTransferManager — export/import
│   ├── core/
│   │   ├── exceptions.py     # ConflictError, InvariantViolation
│   │   ├── migration.py      # Schema migration engine
│   │   ├── router.py         # MemoryRouter
│   │   ├── schemas.py        # All Pydantic data models
│   │   └── targets.py        # TargetRegistry
│   ├── reasoning/
│   │   ├── conflict.py       # ConflictEngine
│   │   ├── decay.py          # DecayEngine
│   │   ├── distillation.py   # DistillationEngine (MemP principle)
│   │   ├── git_indexer.py    # GitIndexer
│   │   ├── merging.py        # MergeEngine
│   │   ├── reflection.py     # ReflectionEngine v4.2
│   │   ├── resolution.py     # ResolutionEngine
│   │   └── ranking/graph.py  # KnowledgeGraphGenerator (Mermaid)
│   └── stores/
│       ├── episodic.py       # EpisodicStore (SQLite)
│       ├── semantic.py       # SemanticStore (Git + Markdown)
│       ├── vector.py         # VectorStore (NumPy)
│       └── semantic_store/   # Internal semantic store components
└── server/
    ├── background.py         # BackgroundWorker (the Heartbeat)
    ├── cli.py                # CLI entry point
    ├── gateway.py            # FastAPI REST + SSE + WebSocket
    ├── server.py             # MCPServer with 15 tools
    └── ...
```

---

## Documentation

| Document | Description |
|---|---|
| [API Reference](docs/API_REFERENCE.md) | Complete reference for all public methods |
| [Integration Guide](docs/INTEGRATION_GUIDE.md) | Library and MCP integration patterns |
| [MCP Tools Reference](docs/MCP_TOOLS.md) | All 15 MCP tools with parameters and examples |
| [Data Schemas](docs/DATA_SCHEMAS.md) | All Pydantic models and their fields |
| [Workflows](docs/WORKFLOWS.md) | Step-by-step guides for common patterns |
| [Architecture](docs/ARCHITECTURE.md) | Deep dive into internals and design decisions |
| [Configuration](docs/CONFIGURATION.md) | All configuration parameters and tuning |
| [Quick Start Tutorial](docs/tutorials/QUICKSTART.md) | Your first autonomous agent in 5 minutes |
| [Comparison](docs/COMPARISON.md) | LedgerMind vs LangChain Memory, Mem0, Zep |

---

## CLI Reference

```bash
ledgermind-mcp init --path ./memory                    # Initialize project
ledgermind-mcp run  --path ./memory                    # Start MCP server
ledgermind-mcp run  --path ./memory \
                    --metrics-port 9090 \               # Prometheus metrics
                    --rest-port 8080                    # REST API gateway
ledgermind-mcp check --path ./memory                   # Run diagnostics
ledgermind-mcp stats --path ./memory                   # Show statistics
ledgermind-mcp export-schema                           # Print JSON API spec
```

---

## License

LedgerMind is distributed under the **Non-Commercial Source Available License (NCSA)**.

- **Individuals:** Free for personal, educational, and experimental use.
- **Commercial use:** Strictly prohibited without written permission from the author.
- **NGOs & Academia:** Permitted for academic and non-profit purposes.

For commercial licensing, contact the author: **Stanislav Zotov**.

---

*LedgerMind — the foundation of AI autonomy.*
