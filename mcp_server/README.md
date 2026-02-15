# Agent Memory Server v1.2.0

Dedicated MCP (Model Context Protocol) Server for the Agent Memory System. Acts as the primary enforcement layer and provides a structured API contract for memory operations.

**API Version:** 1.0.0

## 🔐 Authority Model (RBAC)

The server implements Role-Based Access Control to ensure memory integrity:

| Role | Permissions | Description |
| :--- | :--- | :--- |
| `viewer` | Read-only | Can search and list decisions. Cannot write anything. |
| `agent` | Restricted Write | Can record decisions and create proposals. Cannot accept proposals or override Admin decisions. |
| `admin` | Full Access | Complete control, including `accept_proposal` and configuration changes. |

## 📜 API Contract (v1.0.0)

Every tool call is validated against strict Pydantic schemas. Responses are always structured JSON.

### Tools

#### 1. `record_decision`
- **Request:** `RecordDecisionRequest` (title, target, rationale, consequences)
- **Validation:** `rationale` must be at least 10 characters.
- **Response:** `DecisionResponse` (status, decision_id, message)

#### 2. `supersede_decision`
- **Request:** `SupersedeDecisionRequest` (title, target, rationale, old_decision_ids, consequences)
- **Validation:** `rationale` must be at least 15 characters.
- **Response:** `DecisionResponse`

#### 3. `search_decisions`
- **Request:** `SearchDecisionsRequest` (query, limit)
- **Response:** `SearchResponse` (list of `SearchResultItem`)

#### 4. `accept_proposal`
- **Request:** `AcceptProposalRequest` (proposal_id)
- **Enforcement:** Requires `admin` role.
- **Response:** `BaseResponse`

## 🚀 Features
- **Strict Validation**: Contract-first design using Pydantic.
- **Security First**: Every request is validated against the assigned role.
- **Traceability**: All writes via MCP are tagged with the role (e.g., `[via MCP:agent]`).

## 🛠 Installation
```bash
pip install -e ./core -e ./mcp_server
```

## 🏃 Running

Start the server with a specific role:
```bash
agent-memory-mcp --path ./.agent_memory --role agent
```
