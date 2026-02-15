# Agent Memory System

A modular, secure, and auditable memory ecosystem for autonomous agents. Designed for professional environments where explainability and knowledge governance are mandatory.

## 🏗 Tiered Architecture

The system is split into three distinct layers to ensure a clean boundary between domain logic and infrastructure:

1.  **[Core](./core)** (`agent-memory-core` v1.8.0): The domain heart. Handles storage (Semantic, Episodic, Vector), Competitive Reasoning (Reflection v3, Distillation), and Transactional Integrity.
2.  **[MCP Server](./mcp_server)** (`agent-memory-server` v1.3.0): The enforcement layer and transport. Implements RBAC, Isolation Rules, and strict API contracts.
3.  **[Adapters](./adapters)** (`agent-memory-adapters` v1.0.0): LLM-specific clients (OpenAI, Anthropic, Gemini, etc.) that connect to the MCP Server.

## 🛡 Security & Governance

Unlike traditional "store-all" memories, this system enforces strict rules:
- **Process Invariants**: Protects against panic-decisions via Review Windows and Evidence Thresholds.
- **Authority Model**: RBAC (viewer/agent/admin) ensures only authorized entities can promote hypotheses to truths.
- **Transactional Semantic Store**: Git-backed storage with OS-level locking and atomic commit guards.
- **Falsifiable Reflection**: Prevents self-confirmation loops by penalizing hypotheses with negative evidence.

## 🚀 Quick Start

### Installation
```bash
pip install -e ./core -e ./mcp_server -e ./adapters
```

### Starting the Secure Memory Server
```bash
agent-memory-mcp --path ./.agent_memory --role agent
```

### Connecting an Agent (OpenAI Example)
```python
from agent_memory_core.api.memory import Memory
from agent_memory_adapters.openai import OpenAIAdapter

# Direct usage (Admin context)
memory = Memory(storage_path="./mem")
adapter = OpenAIAdapter(memory)
openai_tools = adapter.get_tool_definitions()
```

## 📜 Key Features
- **Git History Indexing**: Learns from human code commits.
- **Trajectory Distillation**: Turns successful episode sequences into SOPs (Standard Operating Procedures).
- **Hybrid Search**: Cross-references vector similarity with Graph truth (hides superseded knowledge).
