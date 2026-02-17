# Agent Memory System (v2.4.2)

> **OSS = Standard + Correctness + Autonomy**

A modular, autonomous, and auditable memory ecosystem for AI agents.

## 🌟 New in v2.4.2 (Input Safety & Interaction Stability)
- **Interactive Safety:** Increased input threshold to 20 characters and added space requirement to prevent context injection from interfering with interactive shell prompts and selections.
- **De-noising:** Removed aggressive "record_decision" nudges to reduce system spam.
- **Maintenance:** Cleaned up project metadata and updated all component versions.

## 🌟 New in v2.4.1 (Anti-Spam & Proactive Reflection)
- **Knowledge Cooldown:** Context injection now tracks recent usage to prevent repeating the same facts in every prompt.
- **Proactive Reflection:** The engine now suggests "Best Practice" proposals based on recurring success patterns, not just errors.
- **Nudge Mechanism:** Occasionally prompts the agent to record new decisions when no relevant context is found.

## 🌟 New in v2.4.0 (The UX & Trust Update)
- **Auto-Enter Injection:** The PTY driver now automatically submits the query after injecting context, eliminating the need for a second "Enter" press.
- **Verified Knowledge Base:** Memory blocks are now marked as "Verified" to encourage agents to trust the injected context without unnecessary file lookups.
- **Full Content Injection:** Instead of just paths, the runner injects the full content of relevant decisions (Rationale + Consequences) directly into the prompt.
- **Visual Cleanup:** Complete removal of "black square" artifacts and flickering during memory injection.

## 🌟 New in v2.3.0
- **Local Vector Search:** Instant semantic retrieval using NumPy and Sentence-Transformers (all-MiniLM-L6-v2).

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
