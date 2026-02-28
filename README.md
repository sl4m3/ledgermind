# LedgerMind

**v3.0.4** · Autonomous Memory Management System for AI Agents


![Banner](assets/banner.png)

> *LedgerMind is not a memory store — it is a living knowledge core that thinks,
> heals itself, and evolves without human intervention.*

[![License: NCSA](https://img.shields.io/badge/License-NCSA-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green)](https://modelcontextprotocol.io)
[![PyPI](https://img.shields.io/pypi/v/ledgermind)](https://pypi.org/project/ledgermind/)
[![Stars](https://img.shields.io/github/stars/sl4m3/ledgermind)](https://github.com/sl4m3/ledgermind/stargazers)

---

## Featured On

<p align="center">
  <a href="https://aiagentsdirectory.com/agent/ledgermind?utm_source=badge&utm_medium=referral&utm_campaign=free_listing&utm_content=ledgermind" target="_blank" rel="noopener noreferrer">
    <img src="https://aiagentsdirectory.com/featured-badge.svg?v=2024" height="57" alt="LedgerMind - Featured on AI Agents Directory">
  </a>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <a href="https://www.agenthunter.io?utm_source=badge&utm_medium=embed&utm_campaign=LedgerMind" target="_blank" rel="noopener noreferrer">
    <img src="./assets/agent.svg" height="52" alt="LedgerMind - Featured on AgentHunter">
  </a>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <a href="https://www.producthunt.com/products/ledgermind?embed=true&amp;utm_source=badge-featured&amp;utm_medium=badge&amp;utm_campaign=badge-ledgermind" target="_blank" rel="noopener noreferrer"><img alt="LedgerMind - True zero-touch autonomous memory for AI agents | Product Hunt" width="250" height="54" src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1086469&amp;theme=dark&amp;t=1772124580144">
  </a>
</p>

---

## 📈 Recent Activity

**Last 14 days:**
- **3,751 Git clones** (950 unique cloners)
- Strong PyPI growth (hundreds of downloads in recent days)

**Installed & used in:**
- Gemini CLI (100% fully stable)
- Claude Code
- Cursor
- VS Code

**Published on Dev.to:**
- ["True Zero-Touch Autonomus Memory for AI Agents"](https://dev.to/sl4m3/ledgermind-zero-touch-memory-that-survives-real-agent-work-46lh)
- ["LedgerMind v3.0: Knowledge That Lives, Breathes, and Dies on Purpose"](https://dev.to/sl4m3/ledgermind-v30-knowledge-that-lives-breathes-and-dies-on-purpose-5c6)

---

## ✨ Why LedgerMind?

| Feature                 | Mem0 / LangGraph | LedgerMind          |
|-------------------------|------------------|---------------------|
| Autonomous healing      | ❌               | ✅ (every 5 min)    |
| Git-audit + versioning  | ❌               | ✅                  |
| 4-bit on-device         | ❌               | ✅                  |
| Multi-agent namespacing | Partial          | ✅ Full             |

---

## What is LedgerMind?

Most AI memory systems are passive stores: you write, you read, and if the
information becomes stale or contradictory — that is your problem. LedgerMind
takes a fundamentally different approach.

LedgerMind is an **autonomous knowledge lifecycle manager**. It combines a
hybrid storage engine (SQLite + Git) with a built-in reasoning layer that
continuously monitors knowledge health, detects conflicts, distills raw
experience into structured rules, and repairs itself — all in the background,
without any intervention from the developer or the agent.

### Core Capabilities

| Capability | Description |
|---|---|
| **Zero-Touch Automation** | `ledgermind install <client>` automatically injects hooks into Claude Code, Cursor, or Gemini CLI for 100% transparent memory operations without MCP tool calls. |
| **VS Code Hardcore Mode** | Dedicated VS Code extension for proactive context injection, terminal monitoring, and automated conversation logging without manual tool calls. |
| **Project Bootstrapping** | `bootstrap_project_context` tool for deep analysis of project structure and automatic initialization of the agent's knowledge base. |
| **Autonomous Heartbeat** | A background worker runs every 5 minutes: Git sync, reflection, decay, self-healing. |
| **Git Evolution** | Automatically tracks code changes to build evolving `DecisionStream` patterns over time. |
| **Deep Truth Resolution** | Improved recursive resolution of superseded chains to ensure only the latest active truth is returned. |
| **Self-Healing Index** | Automatically rebuilds the SQLite metadata index from Markdown source files if corruption or desync is detected. |
| **Lifecycle & Vitality Engine** | Replaces manual decisions with autonomous `DecisionStream` lifecycle phases (`PATTERN` -> `EMERGENT` -> `CANONICAL`) incorporating temporal signal analysis (burst protection, reinforcement density, and vitality decay). |
| **Procedural Distillation** | Automatically converts successful trajectories into step-by-step instructions (`procedural.steps`). |
| **Intelligent Conflict Resolution** | Vector similarity analysis automatically supersedes outdated decisions (threshold: 70%) or triggers LLM arbitration (50-70%). |
| **Multi-agent Namespacing** | Logical partitioning of memory for multiple agents within a single project. |
| **4-bit GGUF Integration** | Optimized for Termux/Android with embedding caching for maximum stability. |
| **Hybrid Storage** | SQLite for fast queries + Git for cryptographic audit and version history. |
| **MCP Server** | 15 tools with namespacing and pagination support for any compatible client. |

---

## Architecture at a Glance

![Architecture](assets/core-arc.svg)

---

## Installation

```bash
# Install LedgerMind (includes Jina v5 4-bit vector support by default)
pip install ledgermind

# Note for Termux/Mobile users: 
# You may need to install build tools first for llama-cpp-python:
# pkg install clang cmake ninja
```

**Requirements:** Python 3.10+, Git installed and configured in PATH.

---

## Quick Start

### 1. Initialization

After installation, run the interactive setup to configure your memory storage, vector models, and client hooks:

```bash
ledgermind init
```

This will guide you interactively through:
1. **Project Location:** Setting the current codebase path.
2. **Memory Path:** Configuring isolated memory storage (default: `../.ledgermind`).
3. **Embedding Model:** Choosing between `jina-v5-4bit` (default) or a custom GGUF/HF model.
4. **Client Hooks:** Installing automatic context hooks for your preferred client directly into the project directory.
5. **Arbitration Mode:** Selecting a conflict resolution and hypothesis enrichment strategy:
   - `lite`: Fast, purely algorithmic.
   - `optimal`: Uses local LLMs (e.g., Ollama) to translate raw execution logs into human-readable architecture hypotheses.
   - `rich`: Uses cloud LLMs (OpenAI, Anthropic) for maximum insight generation.

### 2. Zero-Touch Automation (Recommended)

The easiest way to use LedgerMind is to install the **LedgerMind Hooks Pack**. This automatically configures your LLM client to retrieve context before every prompt and record every interaction without the agent needing to manually call MCP tools.

#### Client Compatibility Matrix

| Client | Event Hooks | Status | Zero-Touch Level |
| :--- | :--- | :---: | :--- |
| **VS Code** | `onDidSave`, `ChatParticipant`, `TerminalData` | ✅ | **Hardcore** (Shadow Context) |
| **Claude Code** | `UserPromptSubmit`, `PostToolUse` | ✅ | **Full** (Auto-record + RAG) |
| **Cursor** | `beforeSubmitPrompt`, `afterAgentResponse` | ✅ | **Full** (Auto-record + RAG) |
| **Gemini CLI** | `BeforeAgent`, `AfterAgent` | ✅ | **Full** (Auto-record + RAG) |
| **Claude Desktop** | *Zero-Touch not available* | ⏳ | Manual MCP tools only |

```bash
# Install hooks for your preferred client (vscode, claude, cursor, or gemini)
# Memory is installed in the parent directory (../.ledgermind) by default for best isolation.
ledgermind install gemini
```
*Now, simply use your client as usual. LedgerMind operates entirely in the background.*

### Option B: Library (Direct Integration)

```python
from ledgermind.core.api.bridge import IntegrationBridge

# NOTE: Using '.ledgermind' in the parent directory (outside the project root) 
# is the recommended standard. This keeps memory isolated from project code,
# prevents context pollution in analysis tools (like 'read_file'), and ensures
# memory is not accidentally committed to source control.
bridge = IntegrationBridge(
    memory_path="../.ledgermind", 
    vector_model="../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf"
)

# Inject relevant context into your agent's prompt
context = bridge.memory.search_decisions("database migrations", namespace="prod_agent")

# Record a structured decision with namespacing
bridge.memory.record_decision(
    title="Use Alembic for all database migrations",
    target="database_migrations",
    rationale="Alembic provides version-controlled, reversible migrations.",
    namespace="prod_agent"
)
```

### Option B: MCP Server (Secure)

```bash
# Set your API key for security
export LEDGERMIND_API_KEY="your-secure-key"

# Start the MCP server
ledgermind-mcp run --path ledgermind
```

---

## Key Workflows

### Workflow 1: Multi-agent Namespacing — Isolation Within One Core

```python
# Agent A decision
memory.record_decision(title="Use PostgreSQL", target="db", namespace="agent_a")

# Agent B decision (same target, different namespace)
memory.record_decision(title="Use MongoDB", target="db", namespace="agent_b")

# Search only returns what belongs to the agent
memory.search_decisions("db", namespace="agent_a") # -> Returns PostgreSQL
```

### Workflow 2: Hybrid Search & Evidence Boost

LedgerMind uses Reciprocal Rank Fusion (RRF) to combine Keyword and Vector
search. Decisions with more "Evidence Links" (episodic events) receive a
**+20% boost per link** to their final relevance score.

---

## Documentation

| Document | Description |
|---|---|
| [API Reference](docs/API_REFERENCE.md) | Complete reference for all public methods |
| [Integration Guide](docs/INTEGRATION_GUIDE.md) | Library and MCP integration patterns |
| [MCP Tools Reference](docs/MCP_TOOLS.md) | All 15 MCP tools with namespacing and offset |
| [Architecture](docs/ARCHITECTURE.md) | Deep dive into internals and design decisions |
| [Configuration](docs/CONFIGURATION.md) | API keys, Webhooks, and tuning |
| [Changelog](docs/changelogs/latest.md) | Recent releases and critical fixes |

---

## Benchmarks (February 28, 2Y, v3.0.4)

LedgerMind is optimized for high-speed operation on **Android/Termux**
as well as containerized environments. It includes built-in security for MCP and
REST endpoints.

- ["STATISTICS"](https://sl4m3.github.io/ledgermind/dev/bench/)

### Performance Benchmarks (v3.0.4)

#### Throughput (Ops/sec)
| Metric | Mobile (GGUF) | Server (MiniLM) | Note |
| :--- | :---: | :---: | :--- |
| **Search OPS** | **2,471** | **17,160** | Hybrid RRF (Vector + Keyword) |
| **Write OPS**  | **6.5** | **39.9** | Full RAG indexing + Git commit |

#### Latency (Mean)
| Metric | Mobile (GGUF) | Server (MiniLM) | Note |
| :--- | :---: | :---: | :--- |
| **Search Latency** | **0.40 ms** | **0.06 ms** | Real-time context retrieval |
| **Write Latency** | **153.8 ms** | **25.0 ms** | Coordinated atomic commit |

---

## License

LedgerMind is distributed under the **Non-Commercial Source Available License
(NCSA)**.

---

*LedgerMind — the foundation of AI autonomy.*
