# Agent Memory Server v1.5.0

Dedicated MCP (Model Context Protocol) Server for the Agent Memory System. Acts as the primary enforcement layer and provides a structured API contract for memory operations.

**API Version:** 1.0.0

## 🔐 Security & Authentication

The server implements mandatory token-based authentication for privileged operations.

### Mandatory Environment Variable
To use `agent` or `admin` roles, you MUST set the following variable in your environment:
- `AGENT_MEMORY_SECRET`: A secure string known to the authorized client.

If this variable is missing, the server will automatically downgrade the session to the `viewer` role (read-only) for safety.

## 📜 Authority Model (RBAC)

| Role | Permissions | Description | Requirements |
| :--- | :--- | :--- | :--- |
| `viewer` | Read-only | Can search and list decisions. | None |
| `agent` | Restricted Write | Can record decisions and create proposals. | `AGENT_MEMORY_SECRET` |
| `admin` | Full Access | Complete control, including `accept_proposal`. | `AGENT_MEMORY_SECRET` |

## 🛡 Hardening & Telemetry

- **Audit Logging**: Every access attempt (Success/Denied) is recorded in `audit.log` within the storage directory.
- **Isolation Rule**: Agents cannot supersede decisions created by humans.
- **Rate Limiting**: Integrated cooldown mechanism (2s) between write operations.
- **Contract-First Validation**: All data validated against strict Pydantic schemas.

## 🏃 Running

Start the server with a specific role:
```bash
export AGENT_MEMORY_SECRET="your-secure-token"
agent-memory-mcp --path ./.agent_memory --role admin
```

## 🛠 Installation
```bash
pip install -e ./core -e ./mcp_server
```
