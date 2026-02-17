# Agent Memory System (OSS Edition)

> **OSS = Standard + Correctness + Autonomy**

A modular, autonomous, and auditable memory ecosystem for AI agents. Focused on engineering correctness, epistemic reasoning, and local-first persistence.

## 🏗 Reference Architecture

1.  **[Core](./core)** (`agent-memory-core`): The domain heart. Handles storage (Hybrid Semantic Store: SQLite + Git), Epistemic Reasoning, and Transactional Integrity.
2.  **[MCP Server](./mcp_server)** (`agent-memory-server`): The standard transport layer. Implements a unified interface for agents to record and evolve knowledge.
3.  **[Adapters](./adapters)** (`agent-memory-adapters`): Lightweight clients for LLM providers (OpenAI, Anthropic, Gemini, etc.) that connect via MCP.

## 🌟 Core Features

- **Epistemic Reasoning**: Active Knowledge Reflection, Distillation, and Recursive Truth Resolution.
- **Hybrid Semantic Store**: High-performance metadata indexing in SQLite combined with Git-backed cold storage for immutable audit logs.
- **Conflict Resolution**: Built-in detection of contradictory decisions with mandatory resolution paths.
- **Knowledge Evolution**: Native support for superseding and deprecating facts with full lineage tracking.
- **Local-First & Portable**: No heavy database dependencies; runs anywhere with Python, SQLite, and Git.
- **Transactional Integrity**: ACID-compliant operations ensure memory never becomes corrupted.

## 🛡 Engineering Guarantees

- **Process Invariants**: Protects against logic errors via evidence thresholds and deterministic ranking.
- **Hardened Audit**: Every change is cryptographically linked to a Git commit hash, ensuring perfect traceability.
- **Reference Implementation**: Designed to prove the "Agent Memory Model" as a foundation for intelligent systems.

## 🚀 Quick Start

### Installation
```bash
pip install -e ./core -e ./mcp_server -e ./adapters
```

### Starting the Memory Server
```bash
# Start the MCP server using local storage
agent-memory-mcp --path ./.agent_memory
```

## ⚖️ Comparison: OSS vs Enterprise

| Feature | OSS | Enterprise |
| :--- | :--- | :--- |
| **Backend** | SQLite + Git | PostgreSQL + pgvector |
| **Search** | Keyword + Metadata | Semantic + ANN + Hybrid |
| **Governance** | Single-user | RBAC + Organizations + Teams |
| **Scale** | Single-node | Multi-tenant + Sharding |
| **Compliance** | Raw logs | PII Masking + GDPR Presets |
| **UI** | CLI | Web Dashboard + Graph Editor |

---
*Agent Memory System - Engineering the foundation of AI autonomy.*
