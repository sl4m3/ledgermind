# Agent Memory System (OSS Edition)

> **OSS = Standard + Correctness + Autonomy**

A modular, autonomous, and auditable memory ecosystem for AI agents. Focused on engineering correctness, epistemic reasoning, and local-first persistence.

## 🏗 Reference Architecture

1.  **[Core](./core)** (`agent-memory-core`): The domain heart. Handles storage (Hybrid Semantic Store: SQLite + Git), Epistemic Reasoning, and Transactional Integrity.
2.  **[MCP Server](./mcp_server)** (`agent-memory-server`): The standard transport layer. Implements a unified interface for agents.
3.  **[Adapters](./adapters)** (`agent-memory-adapters`): Lightweight clients for LLM providers (OpenAI, Anthropic, Gemini, etc.) that connect via MCP.
4.  **[Runner](./runner)** (`agent-memory-runner`): **(New)** A PTY-based wrapper to inject memory into ANY CLI agent (Gemini, aichat, interpreter) with zero code changes.

## 🌟 Core Features

- **PTY Injection**: Transparently attach memory to any terminal process (Zero Fork).
- **Epistemic Reasoning**: Active Knowledge Reflection, Distillation, and Recursive Truth Resolution.
- **Hybrid Semantic Store**: High-performance metadata indexing in SQLite combined with Git-backed cold storage.
- **Conflict Resolution**: Built-in detection of contradictory decisions with mandatory resolution paths.
- **Knowledge Evolution**: Native support for superseding and deprecating facts.
- **Transactional Integrity**: ACID-compliant operations ensure memory never becomes corrupted.

## 🚀 Quick Start

### Installation
```bash
pip install -e ./core -e ./mcp_server -e ./adapters -e ./runner
```

### Running ANY Agent with Memory (Runner)
```bash
# Wrap gemini-cli
am-run gemini

# Wrap aichat
am-run aichat

# Wrap your own script
am-run python3 my_agent.py
```

### Starting the Dedicated MCP Server
```bash
# Start the standalone server
agent-memory-mcp run --path ./.agent_memory
```

---
*Agent Memory System - Engineering the foundation of AI autonomy.*
