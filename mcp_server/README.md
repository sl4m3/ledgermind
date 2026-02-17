# Agent Memory Server v2.0.5

Dedicated MCP (Model Context Protocol) Server for the Agent Memory System. Acts as the primary enforcement layer and provides a structured API contract for memory operations.

**API Version:** 2.0.5

## 🚀 Key Features

- **Zero-Config Embeddings**: Automatically detects and uses Google (Gemini) or OpenAI embeddings if keys are present, with a built-in fallback for local semantic search without API keys.
- **REST Gateway**: Parallel access to memory via standard HTTP POST/GET endpoints (Port 8000 by default).
- **Observability**: Exposes Prometheus metrics (Port 9090) for monitoring system health and memory usage.
- **SSE & WebSockets**: Real-time memory change notifications and bi-directional communication.
- **Granular Purge**: GDPR-compliant data forgetting via the `purge` capability.

## 🔐 Security & Hardened Audit

The server implements **Capability-based access control**. This ensures that the agent has only the specific permissions it needs (Principle of Least Privilege). Every state-changing operation is recorded in `audit.log`.

### 📜 Authority Model (Capabilities)

| Capability | Tool Impact | Description |
| :--- | :--- | :--- |
| `read` | `search_decisions`, `visualize_graph` | Allows semantic search, retrieval, and visualization. |
| `propose` | `record_decision` | Allows recording new decisions/hypotheses. |
| `supersede` | `supersede_decision` | Allows replacing existing decisions. |
| `accept` | `accept_proposal` | Allows promoting drafts to active decisions. |
| `sync` | `sync_git_history` | Allows indexing external Git history. |
| `purge` | `forget_memory` | Allows permanent deletion for GDPR compliance. |

## 🏃 Running the Server

### Standard Execution
```bash
agent-memory-mcp run --path ./.agent_memory --capabilities '{"read": true, "propose": true}'
```

### Full Configuration Example
```bash
agent-memory-mcp run \
  --path ./.agent_memory \
  --metrics-port 9090 \
  --rest-port 8000 \
  --capabilities '{"read": true, "propose": true, "sync": true}'
```

## 🛠 Configuration (IDE / Claude Desktop)

Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "agent-memory": {
      "command": "agent-memory-mcp",
      "args": [
        "run",
        "--path",
        ".agent_memory",
        "--name",
        "AgentMemory",
        "--capabilities",
        "{\"read\": true, \"propose\": true, \"supersede\": true, \"accept\": true, \"sync\": true}"
      ]
    }
  }
}
```

## 🛠 Installation
```bash
pip install -e ./core -e ./mcp_server
```
