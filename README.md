# Agent Memory System

A modular and auditable memory ecosystem for autonomous agents.

## 🏗 Architecture

The system is split into three distinct layers to ensure a clean boundary between domain logic and infrastructure:

1.  **[Core](./core)** (`agent-memory-core`): The heart of the system. Handles storage (Semantic, Episodic, Vector), Reasoning (Reflection, Distillation), and Invariants. No external LLM dependencies.
2.  **[MCP Server](./mcp_server)** (`agent-memory-server`): The primary enforcement layer and transport. Connects the Core to the world via the Model Context Protocol.
3.  **[Adapters](./adapters)** (`agent-memory-adapters`): LLM-specific clients (OpenAI, Anthropic, Gemini, etc.) that connect to the MCP Server and format tools for each model.

## 🚀 Quick Start

### Installation
```bash
pip install -e ./core -e ./mcp_server -e ./adapters
```

### Starting the Memory Server
```bash
agent-memory-mcp --path ./.agent_memory
```

### Connecting an Agent (OpenAI Example)
```python
from agent_memory_core.api.memory import Memory
from agent_memory_adapters.openai import OpenAIAdapter

# In-process usage (direct)
memory = Memory(storage_path="./mem")
adapter = OpenAIAdapter(memory)
openai_tools = adapter.get_tool_definitions()
```

## 🛡 Key Concepts
- **Git-Backed Semantic Memory**: Every decision is a versioned Markdown file.
- **Process Invariants**: Rules like "Review Window" and "Evidence Threshold" ensure memory stability.
- **Trajectory Distillation**: Learns from success by turning episodic sequences into procedural rules.
