# Agent Memory Server v1.9.1

Dedicated MCP (Model Context Protocol) Server for the Agent Memory System. Acts as the primary enforcement layer and provides a structured API contract for memory operations.

**API Version:** 1.0.0

## 🔐 Security & Hardened Audit

The server implements mandatory token-based authentication and a **cryptographically-linked audit trail**. Every state-changing operation is recorded in `audit.log` alongside the resulting Git commit hash, ensuring absolute non-repudiation.

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

## 🛡 Security & Compliance

This server is designed for high-trust environments and implements a formal security model.
- **Threat Model**: Detailed analysis of attack vectors and mitigations in [THREAT_MODEL.md](./docs/THREAT_MODEL.md).
- **Security Contract**: Formal guarantees and shared responsibilities in [SECURITY_CONTRACT.md](./docs/SECURITY_CONTRACT.md).
- **Audit Logging**: All operations are recorded in `audit.log`. Git history provides cryptographically-signed-like non-repudiation.

## 🏃 Running

Start the server with a specific role:
```bash
export AGENT_MEMORY_SECRET="your-secure-token"
agent-memory-mcp run --path ./.agent_memory --role admin
```

## 🛠 API Specification

The server follows a strict formal contract. 
- **Specification**: See [MCP_SPECIFICATION.md](./docs/MCP_SPECIFICATION.md) for detailed tool schemas and data models.
- **JSON Schemas**: You can export the latest machine-readable schemas using the CLI:
  ```bash
  agent-memory-mcp export-schema > schema.json
  ```

## 🛠 Installation
```bash
pip install -e ./core -e ./mcp_server
```
