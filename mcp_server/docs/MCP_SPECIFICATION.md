# Agent Memory MCP Interface Definition (v1.0.0)

This is the **formal API contract** for the Agent Memory Ecosystem. It follows the Model Context Protocol (MCP) and provides strict structural guarantees.

## 🏗 Industrial Design Goals
1.  **Contract-First**: The API is defined via JSON Schemas, not dynamic implementation.
2.  **Versioning**: API version `1.0.0` is immutable. Breaking changes will result in `v2.0.0`.
3.  **Cross-Client Stability**: Any MCP-compliant client (Node.js, Go, Rust) can interact with this server using the exported spec.

## 📂 Machine-Readable Specification
The full specification, including all Request/Response models, can be exported as a single JSON file:
```bash
agent-memory-mcp export-schema > mcp_api_v1.json
```

## 🛠 Tool Definitions

### `record_decision`
**Purpose**: Immutable recording of a strategic rule or fact.
- **Constraints**: Rationale must be ≥ 10 characters.
- **Side Effects**: Atomic Git commit, Vector index update.

### `supersede_decision`
**Purpose**: Evolves knowledge by replacing old active decisions.
- **Constraints**: Rationale must be ≥ 15 characters. Must target at least one existing ID.
- **Isolation**: Agents cannot supersede Human-authored decisions.

### `search_decisions`
**Purpose**: Hybrid search (Vector + Semantic Graph).
- **Modes**:
    - `strict`: Guaranteed only `active` decisions.
    - `balanced`: Active prioritized, deduplicated by target.
    - `audit`: Full history, no filtering.

### `accept_proposal`
**Purpose**: Promotion of Agent-generated hypotheses to Truth.
- **Security**: Requires `ADMIN` role and `AGENT_MEMORY_SECRET`.
- **Constraint**: Must be outside the 1-hour Review Window (PI1).

## 🛑 Error Handling (JSON-RPC Codes)
The server uses standard MCP error patterns:
- `-32602`: Invalid params (Validation error).
- `-32000`: Execution error (Integrity violation or Git failure).
- `403`: Permission Denied (Auth failure).
