# Agent Memory Server v1.4.0

Dedicated MCP (Model Context Protocol) Server for the Agent Memory System. Acts as the primary enforcement layer and provides a structured API contract for memory operations.

**API Version:** 1.0.0

## 🔍 Hybrid Search Modes

The server supports three search modes to balance between discovery and reliability:

- `strict`: Only returns **active** decisions. Safest mode for real-time agent operation.
- `balanced` (default): Returns history but applies heavy penalties to superseded/deprecated records.
- `audit`: Full historical search with no penalties.

## 🔐 Authority Model (RBAC)

The server implements Role-Based Access Control to ensure memory integrity:

| Role | Permissions | Description |
| :--- | :--- | :--- |
| `viewer` | Read-only | Can search and list decisions. Cannot write anything. |
| `agent` | Restricted Write | Can record decisions and create proposals. **Cannot** accept proposals or override Admin/Human decisions. |
| `admin` | Full Access | Complete control, including `accept_proposal` and configuration changes. |

## 🛡 Security & Hardening (Threat Model)

The server is designed to withstand malicious or erroneous client behavior:

- **Isolation Rule**: Clients with the `agent` role are strictly forbidden from superseding decisions created by humans.
- **Rate Limiting**: Integrated cooldown mechanism (2s) to prevent resource exhaustion and Git index flooding.
- **Contract-First Validation**: All incoming data is validated against strict Pydantic schemas.
- **Traceability**: Every record is tagged with the source role (e.g., `[via MCP:agent]`).

## 📜 API Contract (v1.0.0)

Every tool call is validated against strict Pydantic schemas. Responses are always structured JSON.

### Tools

#### 1. `record_decision`
- **Request:** `RecordDecisionRequest` (title, target, rationale, consequences)
- **Validation:** `rationale` must be at least 10 characters.
- **Enforcement**: Role `agent` or `admin`.

#### 2. `supersede_decision`
- **Request:** `SupersedeDecisionRequest` (title, target, rationale, old_decision_ids, consequences)
- **Enforcement**: Role `agent` (restricted by Isolation Rule) or `admin`.

#### 3. `search_decisions`
- **Request:** `SearchDecisionsRequest` (query, limit)
- **Response:** `SearchResponse` (validated by Semantic Store truth).

#### 4. `accept_proposal`
- **Request:** `AcceptProposalRequest` (proposal_id)
- **Enforcement:** Requires `admin` role and fulfillment of the **Review Window** (PI1).

## 🛠 Installation
```bash
pip install -e ./core -e ./mcp_server
```

## 🏃 Running

Start the server with a specific role:
```bash
agent-memory-mcp --path ./.agent_memory --role agent
```
