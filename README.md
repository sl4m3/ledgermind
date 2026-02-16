# Agent Memory System

A modular, secure, and auditable memory ecosystem for autonomous agents. Designed for professional environments where explainability, performance, and knowledge governance are mandatory.

## 🏗 Tiered Architecture

The system is split into three distinct layers to ensure a clean boundary between domain logic and infrastructure:

1.  **[Core](./core)** (`agent-memory-core` v2.0.0): The domain heart. Handles storage (Hybrid Semantic Store: SQLite/PostgreSQL + Git, Episodic, Vector), Epistemic Reasoning, and Transactional Integrity. **Features high-performance indexing and Zstandard compression.**
2.  **[MCP Server](./mcp_server)** (`agent-memory-server` v2.0.2): The enforcement layer and transport. Implements RBAC, Capabilities, and REST/WebSocket Gateway. **Now with dynamic embedding provider selection.**
3.  **[Adapters](./adapters)** (`agent-memory-adapters` v2.0.2): LLM-specific clients (OpenAI, Anthropic, Gemini, LangChain, etc.) that connect to the MCP Server.

## 🌟 Major Features (v2.0+)

- **Enterprise Scalability**: Full support for **PostgreSQL** and **pgvector**, enabling sub-second semantic search across millions of records.
- **Epistemic Reasoning**: Active Knowledge Reflection, Distillation, and Recursive Truth Resolution.
- **Distributed Sync**: Real-time multi-instance synchronization via **Redis Pub/Sub**.
- **Privacy & Compliance**: Automated PII masking, Encryption at Rest (Fernet), and GDPR-compliant "Hard Forget" (purge from files, Git, and vectors).
- **Advanced Search**: Hybrid search engine with support for Google (Gemini), OpenAI, and Ollama embeddings.
- **Optimization**: Integrated Zstandard compression and intelligent mtime-based integrity caching.

## 🛡 Security & Governance

- **Process Invariants**: Protects against panic-decisions via Review Windows and Evidence Thresholds.
- **Authority Model**: RBAC (viewer/agent/admin) or granular **Capabilities** (read/propose/supersede/accept/sync/purge).
- **Hardened Audit**: Every change is cryptographically linked to a Git commit hash in a dedicated `audit.log`.
- **Hybrid Semantic Store**: High-performance metadata indexing in SQLite/Postgres combined with Git-backed cold storage for immutable audit logs.

## 🧪 Testing & Reliability

- **Property-Based Testing**: Validates system invariants using `Hypothesis`.
- **Performance Benchmarked**: Optimized conflict detection ($O(1)$ via database indices) and transaction handling.
- **Stress-Tested Concurrency**: Proven stability for multi-process environments with atomic commit guards.

## 🚀 Quick Start

### Installation
```bash
pip install -e ./core -e ./mcp_server -e ./adapters
```

### Starting the Secure Memory Server
```bash
# Set your API key for semantic search
export GOOGLE_API_KEY="your-key-here"

# Start the MCP server
agent-memory-mcp --path ./.agent_memory --role agent
```

### Learning Resources
- **[Quickstart Tutorial](./docs/tutorials/QUICKSTART.md)**: Build a Code Analysis Agent with memory in 5 minutes.
- **[Comparison Guide](./docs/COMPARISON.md)**: How we differ from LangChain, Mem0, and Zep.
- **[Interactive Notebooks](./notebooks/01_introduction.ipynb)**: Explore features in Jupyter.

---
*Agent Memory System - Scalable, Auditable, and Intelligent.*
