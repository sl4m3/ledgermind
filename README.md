# Agent Memory System

A modular, secure, and auditable memory ecosystem for autonomous agents. Designed for professional environments where explainability and knowledge governance are mandatory.

## 🏗 Tiered Architecture

The system is split into three distinct layers to ensure a clean boundary between domain logic and infrastructure:

1.  **[Core](./core)** (`agent-memory-core` v2.0.0): The domain heart. Handles storage (Hybrid Semantic Store: SQLite + Git, Episodic, Vector), Epistemic Reasoning, and Transactional Integrity. **Now with Auto-Migration and Privacy Controls.**
2.  **[MCP Server](./mcp_server)** (`agent-memory-server` v2.0.0): The enforcement layer and transport. Implements RBAC, Capabilities, and REST/WebSocket Gateway.
3.  **[Adapters](./adapters)** (`agent-memory-adapters` v2.0.0): LLM-specific clients (OpenAI, Anthropic, Gemini, etc.) that connect to the MCP Server.

## 🌟 New in v2.0.0

- **Privacy & Compliance**: Automated PII masking and Encryption at Rest (Fernet) for sensitive memory content.
- **Auto-Migration Engine**: Seamlessly upgrades legacy data formats to modern standards on startup.
- **REST & Real-time Gateway**: Parallel access via REST API, SSE events, and WebSockets.
- **Vector Optimization**: Integrated Zstandard compression for high-dimensional vectors and embedding caching.
- **Scaling**: Multi-instance synchronization via Redis Pub/Sub.

## 🛡 Decoupled Architecture

As of v1.12.0, the system enforces a strict separation between transport and logic:
- **Zero-Dependency Adapters**: Adapters no longer require the `core` library. They communicate with the memory exclusively via the MCP protocol.
- **Client-Side Proxy**: The `MCPMemoryProxy` provides a seamless interface for adapters to perform RPC calls to the remote memory server.
- **Transport Agnostic**: The system supports any MCP-compatible transport (stdio, SSE, etc.), enabling distributed memory setups.

## 🛡 Security & Governance

Unlike traditional "store-all" memories, this system enforces strict rules:
- **Process Invariants**: Protects against panic-decisions via Review Windows and Evidence Thresholds.
- **Authority Model**: RBAC (viewer/agent/admin) or granular **Capabilities** (read/propose/supersede/accept/sync).
  - **Legacy Mode**: Requires `AGENT_MEMORY_SECRET` for `agent`/`admin` roles.
  - **Modern Capability Mode**: Explicitly define permissions without secrets for internal/trusted boundaries.
- **Hardened Audit**: Every change is cryptographically linked to a Git commit hash in a dedicated `audit.log`.
- **Hybrid Semantic Store**: High-performance metadata indexing in SQLite combined with Git-backed cold storage for immutable audit logs.
- **Recursive Truth Resolution**: Hybrid search automatically follows the knowledge evolution graph to return the latest active version of any decision.
- **High-Concurrency Support**: Git-backed storage with OS-level locking, atomic commit guards, and intelligent conflict resolution (supporting 15+ retries with exponential backoff).
- **Falsifiable Reflection**: Prevents self-confirmation loops by penalizing hypotheses with negative evidence.

## 🧪 Testing & Reliability (New in v1.11.0)

The system is built with professional-grade reliability in mind:
- **Property-Based Testing**: Validates system invariants (like target uniqueness) under thousands of random operation sequences using `Hypothesis`.
- **Semantic Drift Protection**: Verified stability of search results under embedding noise and provider migrations.
- **Stress-Tested Concurrency**: Proven stability for multi-process environments (verified 100+ parallel transactions without data loss).
- **Audit Integration**: Every write operation is recorded and verifiable via the Git-backed Semantic Store.

## 🚀 Quick Start

### Installation
```bash
pip install -e ./core -e ./mcp_server -e ./adapters
```

### Learning Resources
- **[Quickstart Tutorial](./docs/tutorials/QUICKSTART.md)**: Build a Code Analysis Agent with memory in 5 minutes.
- **[Comparison Guide](./docs/COMPARISON.md)**: How we differ from LangChain, Mem0, and Zep.
- **[Interactive Notebooks](./notebooks/01_introduction.ipynb)**: Explore features in Jupyter.

### Starting the Secure Memory Server
```bash
agent-memory-mcp --path ./.agent_memory --role agent
```

### Connecting an Agent (OpenAI Example)
```python
from agent_memory_adapters.mcp_client import MCPMemoryProxy, SyncMCPMemoryProxy
from agent_memory_adapters.openai import OpenAIAdapter
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Connect to memory via MCP transport
async def main():
    server_params = StdioServerParameters(command="agent-memory-mcp", args=["--path", "./mem"])
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Use Proxy to talk to the server
            memory_proxy = MCPMemoryProxy(session)
            adapter = OpenAIAdapter(memory_provider=memory_proxy)
            
            # Now adapter uses MCP RPC calls instead of direct library calls
            # ...
```

## 📜 Key Features
- **Git History Indexing**: Learns from human code commits.
- **Trajectory Distillation**: Turns successful episode sequences into SOPs (Standard Operating Procedures).
- **Graph-First Hybrid Search**: Cross-references vector similarity with Graph truth. Guaranteed to prioritize active decisions and deduplicate by target.
