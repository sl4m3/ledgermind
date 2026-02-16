# Agent Memory Server v2.0.0

Dedicated MCP (Model Context Protocol) Server for the Agent Memory System. Acts as the primary enforcement layer and provides a structured API contract for memory operations.

**API Version:** 2.0.0

## 🚀 New in v2.0.0

- **REST Gateway**: Parallel access to memory via standard HTTP POST/GET endpoints.
- **SSE & WebSockets**: Real-time memory change notifications and bi-directional communication.
- **Granular Purge**: GDPR-compliant data forgetting via the `purge` capability.

## 🔐 Security & Hardened Audit

The server implements mandatory token-based authentication (legacy) or **Capability-based access control (modern)**. Every state-changing operation is recorded in `audit.log`.

### Authentication Options
- **Capability Mode (Recommended)**: Pass `--capabilities` JSON to explicitly define what the server can do. No secret required.
- **Legacy Role Mode**: Requires `AGENT_MEMORY_SECRET` environment variable for `agent` or `admin` roles.

## 📜 Authority Model (Capabilities)

| Capability | Tool Impact | Description |
| :--- | :--- | :--- |
| `read` | `search_decisions` | Allows semantic search and retrieval. |
| `propose` | `record_decision` | Allows recording new decisions/hypotheses. |
| `supersede` | `supersede_decision` | Allows replacing existing decisions. |
| `accept` | `accept_proposal` | Allows promoting drafts to active decisions. |
| `sync` | `sync_git_history` | Allows indexing external Git history. |

### Legacy Roles Mapping
| Role | Permissions | Requirements |
| :--- | :--- | :--- |
| `viewer` | `read` | None |
| `agent` | `read`, `propose`, `supersede`, `sync` | `AGENT_MEMORY_SECRET` |
| `admin` | `read`, `propose`, `supersede`, `sync`, `accept` | `AGENT_MEMORY_SECRET` |

## 🏃 Running

### Option A: Capability Mode (No secret required)
```bash
agent-memory-mcp run --capabilities '{"read": true, "propose": true}'
```

### Option B: Legacy Role Mode
```bash
export AGENT_MEMORY_SECRET="your-secure-token"
agent-memory-mcp run --role admin
```

## 🛠 Configuration (IDE / Claude Desktop)

To use this server with an MCP-compatible client (like Claude Desktop or VS Code), add the following to your configuration file (e.g., `claude_desktop_config.json`):

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

## 🛠 API Specification

The server follows a strict formal contract defined by `mcp_server/schema/mcp_api_v1.json`. 
- **Formal Contract**: [mcp_api_v1.json](./schema/mcp_api_v1.json) is the single source of truth for all clients.
- **Specification**: See [MCP_SPECIFICATION.md](./docs/MCP_SPECIFICATION.md) for detailed explanations.
- **JSON Schemas**: You can also export the latest schema using the CLI:
  ```bash
  agent-memory-mcp export-schema > schema.json
  ```

## 🛠 Installation
```bash
pip install -e ./core -e ./mcp_server
```
