# Agent Memory Server v1.1.0

Dedicated MCP (Model Context Protocol) Server for the Agent Memory System. Acts as the primary enforcement layer for memory operations.

## 🔐 Authority Model (RBAC)

The server implements Role-Based Access Control to ensure memory integrity:

| Role | Permissions | Description |
| :--- | :--- | :--- |
| `viewer` | Read-only | Can search and list decisions. Cannot write anything. |
| `agent` | Restricted Write | Can record decisions and create proposals. Cannot accept proposals or override Admin decisions. |
| `admin` | Full Access | Complete control, including `accept_proposal` and configuration changes. |

## 🚀 Features
- **Security First**: Every request is validated against the assigned role.
- **Traceability**: All writes via MCP are tagged with the role (e.g., `[via MCP:agent]`).
- **Domain Decoupling**: Pure transport layer, no LLM-specific logic.

## 🛠 Installation
```bash
pip install -e ./core -e ./mcp_server
```

## 🏃 Running

Start the server with a specific role:
```bash
agent-memory-mcp --path ./.agent_memory --role agent
```

### Options:
- `--path`: Path to the memory storage directory.
- `--name`: Custom name for the MCP server (default: AgentMemory).
- `--role`: `viewer`, `agent`, or `admin` (default: agent).
