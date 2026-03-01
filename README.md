# LedgerMind

**v3.1.0** · Autonomous Memory Management System for AI Agents


![Banner](assets/banner.png)

> *LedgerMind is not a memory store — it is a living knowledge core that thinks,
> heals itself, and evolves without human intervention.*

[![License: NCSA](https://img.shields.io/badge/License-NCSA-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green)](https://modelcontextprotocol.io)
[![PyPI](https://img.shields.io/pypi/v/ledgermind)](https://pypi.org/project/ledgermind/)
[![Stars](https://img.shields.io/github/stars/sl4m3/ledgermind)](https://github.com/sl4m3/ledgermind/stargazers)

---

## ✨ Why LedgerMind?

| Feature                 | Mem0 / LangGraph | LedgerMind          |
|-------------------------|------------------|---------------------|
| Autonomous healing      | ❌               | ✅ (every 5 min)    |
| Knowledge Enrichment    | ❌               | ✅ (v3.1.0+)        |
| Git-audit + versioning  | ❌               | ✅                  |
| 4-bit on-device         | ❌               | ✅                  |
| Security SAST           | ❌               | ✅ (Bandit)         |

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
| **Knowledge Enrichment** | **[NEW v3.1.0]** The `LLMEnricher` automatically summarizes raw event clusters into human-readable architectural insights using local (Ollama) or remote LLMs. It runs asynchronously to ensure zero latency during active agent sessions. |
| **Search Fast-Path** | **[NEW v3.1.0]** Optimized SQLite FTS5 path for simple keyword queries, completely bypassing heavy vector processing. Reaches speeds over **18,000 ops/sec**. |
| **Lazy Component Loading** | **[NEW v3.1.0]** Vector stores and heavy ML libraries are loaded only when necessary, drastically reducing startup times. |
| **Batch Metadata Fetching** | **[NEW v3.1.0]** Batched resolution of superseded documents inside the Search pipeline eliminates N+1 query patterns. |
| **Zero-Touch Automation** | `ledgermind install <client>` automatically injects hooks into Claude Code, Cursor, or Gemini CLI for 100% transparent memory operations. |
| **Hardened Security** | Integrated **Bandit SAST** into the testing lifecycle and CI pipeline for guaranteed memory integrity and robust multi-process transactions. |
| **Autonomous Heartbeat** | A background worker runs every 5 minutes: Git sync, reflection, decay, self-healing. |
| **Lifecycle Engine** | Autonomous `DecisionStream` phases (`PATTERN` -> `EMERGENT` -> `CANONICAL`) with temporal signal analysis. |
| **Procedural Distillation** | Automatically converts successful trajectories into step-by-step instructions (`procedural.steps`). |
| **Multi-agent Namespacing** | Logical partitioning of memory for multiple agents within a single project. |
| **4-bit GGUF Integration** | Optimized for Termux/Android with embedding caching for maximum stability. |

---

## Architecture at a Glance

![Architecture](assets/core-arc.svg)

LedgerMind enforces a clean separation of concerns: The reasoning layer (`core/reasoning/`) is agnostic to file formats, and the storage layer (`core/stores/`) knows nothing of conflict policies. All interactions pass through `process_event()`, ensuring invariants and trust boundaries are strictly respected before any transaction occurs.

---

## Installation

```bash
# Install LedgerMind
pip install ledgermind

# Note for Termux/Mobile users: 
# You may need to install build tools first for llama-cpp-python:
# pkg install clang cmake ninja
```

---

## Quick Start

### 1. Initialization

After installation, run the interactive setup with arrow-key navigation:

```bash
ledgermind init
```

### 2. Zero-Touch Automation (Recommended)

LedgerMind operates invisibly alongside your chosen AI workflows.

```bash
# Install hooks for your preferred client (vscode, claude, cursor, or gemini)
ledgermind install gemini
```

---

## Benchmarks (March 01, 2026, v3.1.0)

LedgerMind is optimized for extreme responsiveness. Version 3.1.0 introduces
a dedicated Fast-Path for simple queries.

- ["STATISTICS"](https://sl4m3.github.io/ledgermind/dev/bench/)

### Search Performance (Mobile ARM - Android/Termux)

| Mode | Throughput (Ops/sec) | Latency (Mean) | Note |
| :--- | :---: | :---: | :--- |
| **Fast-Path** | **18,106** | **0.05 ms** | SQLite FTS5 Keyword Match (v3.1.0 optimization) |
| **Hybrid RRF** | **706** | **1.41 ms** | Vector + Keyword + Ranking |

### Write Performance (Full Audit Trail)

| Environment | Throughput (Ops/sec) | Latency (Mean) |
| :--- | :---: | :---: |
| **Mobile (Termux)** | **7.8** | **127 ms** |
| **Server (Linux)** | **70.6** | **14 ms** |

---

## License

LedgerMind is distributed under the **Non-Commercial Source Available License
(NCSA)**.

---

*LedgerMind — the foundation of AI autonomy.*