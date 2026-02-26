# MCP Tools Reference

LedgerMind exposes 15 tools via the Model Context Protocol. All tools are available to any compatible MCP client (Claude Desktop, Gemini CLI, custom agents).

---

## Starting the Server

```bash
# Minimal
ledgermind-mcp run --path ./memory

# Secure with API Key and Webhooks
export LEDGERMIND_API_KEY="your-secure-key"
ledgermind-mcp run \
  --path ./memory \
  --webhooks http://api.com/hook \
  --rest-port 8080
```

---

## Roles and Capabilities

The server has three roles, controlled by the `default_role` parameter in `MCPServer.__init__()`:

| Role | Default | Capabilities |
|---|---|---|
| `viewer` | — | `read` only |
| `agent` | ✓ | `read`, `propose`, `supersede`, `accept`, `sync` |
| `admin` | — | All capabilities + bypasses human-record isolation |

**Authentication:** If `LEDGERMIND_API_KEY` is set, all MCP transport metadata and REST requests must include the `X-API-Key` header.

Each capability maps to one or more tools. If a tool's required capability is disabled, it returns an error response.

**Human Record Isolation:** In `agent` role, records created outside MCP (without `[via MCP]` in their rationale) cannot be superseded. This protects human-authored decisions from agent modification.

---

## Installation & Setup

Before using tools, you can automate the integration using the LedgerMind CLI:

```bash
ledgermind install vscode --path .
```

Supported clients: `vscode` (Hardcore Mode), `claude` (CLI), `cursor`, `gemini`.

---

## Tools

### `bootstrap_project_context`

Analyzes the project structure and key files to initialize base knowledge in the agent's memory.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `path` | string | `.` | Absolute path to the project directory |

**Returns:** A structured report containing:
- **Directory Structure:** A tree-like representation of the project (depth 7, up to 1000 entries).
- **MEMORY STORAGE POLICY:** Critical instructions on how to record decisions (Flat Structure rule).
- **Key Files Content:** The content of identified configuration and documentation files (README, ARCHITECTURE, Makefile, etc.).

**Capability required:** `read`

**Behavior:** This is the recommended entry point for an agent entering a new project. It performs a **Deep Scan** of all `.md` files and configuration files. It also provides a specific prompt to the agent on how to correctly use `record_decision` to maintain a flat memory structure in `ledgermind/semantic/`.

**Example:**
```json
{
  "tool": "bootstrap_project_context",
  "path": "."
}
```

---

### `install` (CLI only)

Installs hooks and extensions for a specific client to enable Zero-Touch operations.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `client` | string | ✓ | `claude` (CLI), `cursor`, `gemini`, `vscode` |
| `path` | string | ✓ | Project path for memory synchronization |

**Behavior per client:**
- **`vscode`**: Performs a **Hardcore** installation. It installs the LedgerMind VS Code extension, configures Roo Code (Cline) to use the MCP server, and injects a policy to always read the `ledgermind_context.md` shadow file for proactive knowledge injection.
- **`claude`**: Injects shell hooks into `~/.claude/settings.json` for prompt enrichment and interaction logging in the Claude CLI.
- **`cursor`**: Configures `hooks.json` to call LedgerMind before and after agent actions.
- **`gemini`**: Injects Python hooks for the Gemini CLI.

Records a strategic decision into semantic memory.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | string | ✓ | Short, descriptive title |
| `target` | string | ✓ | The system/area this decision applies to |
| `rationale` | string | ✓ | Why this decision was made (min 10 chars) |
| `consequences` | string[] | — | Rules or effects resulting from this decision |
| `namespace` | string | — | Logical partition (default: `default`) |

**Returns:** `{"status": "success", "decision_id": "decisions/..."}`

**Capability required:** `propose`

**Behavior:** Automatically normalizes `target` via TargetRegistry. If an active decision exists for the same `target` and vector similarity > 85%, auto-supersedes it. Otherwise raises a conflict error.

**Example:**
```json
{
  "tool": "record_decision",
  "title": "Use Redis for session caching",
  "target": "session_storage",
  "rationale": "Redis provides sub-millisecond latency and native TTL support for session data.",
  "consequences": ["Install redis-py", "Configure REDIS_URL environment variable"]
}
```

---

### `supersede_decision`

Explicitly replaces one or more existing decisions with a new one.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `title` | string | ✓ | Title of the new decision |
| `target` | string | ✓ | Target area |
| `rationale` | string | ✓ | Why old decisions are replaced (min 15 chars) |
| `old_decision_ids` | string[] | ✓ | File IDs of decisions to supersede |
| `consequences` | string[] | — | Effects of the new decision |
| `namespace` | string | — | Logical partition (default: `default`) |

**Returns:** `{"status": "success", "decision_id": "decisions/..."}`

**Capability required:** `supersede`

**Example:**
```json
{
  "tool": "supersede_decision",
  "title": "Migrate session storage to Valkey",
  "target": "session_storage",
  "rationale": "Valkey is the open-source Redis fork with a more permissive license, needed for compliance.",
  "old_decision_ids": ["decisions/2024-01-15_session_storage_abc.md"]
}
```

---

### `search_decisions`

Searches semantic memory using hybrid vector + keyword matching.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | string | — | Natural language search query |
| `limit` | integer | 5 | Max results to return (1–50) |
| `offset` | integer | 0 | Pagination offset |
| `namespace` | string | `default`| Partition to search within |
| `mode` | string | `balanced` | `strict`, `balanced`, or `audit` |

**Mode behavior:**
- `strict` — returns only `status=active` records
- `balanced` — returns active records, follows supersede chain to truth
- `audit` — returns all records regardless of status (for finding old IDs)

**Returns:** `{"status": "success", "results": [{id, score, status, preview, kind}, ...]}`

**Capability required:** `read`

---

### `accept_proposal`

Promotes a draft proposal to an active decision.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `proposal_id` | string | ✓ | File ID of the proposal (e.g. `decisions/proposal_abc.md`) |

**Returns:** `{"status": "success", "message": "Accepted"}`

**Capability required:** `accept`

**Behavior:** If the proposal contains `suggested_supersedes`, those decisions are superseded automatically. The proposal's status is updated to `accepted` with a `converted_to` backlink.

---

### `sync_git_history`

Imports recent Git commits into episodic memory for reflection analysis.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `repo_path` | string | `.` | Path to the Git repository |
| `limit` | integer | 20 | Number of recent commits to index |

**Returns:** `{"status": "success", "indexed_commits": 12}`

**Capability required:** `sync`

---

### `forget_memory`

Hard-deletes a memory record from all stores.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `decision_id` | string | ✓ | File ID of the record to delete |

**Returns:** `{"status": "success", "message": "Forgotten decisions/..."}`

**Capability required:** `purge`

> ⚠️ This operation is irreversible. The record is removed from the filesystem, Git history (via new commit), SQLite index, and vector index.

---

### `visualize_graph`

Generates a Mermaid diagram of knowledge evolution.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `target` | string | `null` | Filter graph to a specific target area |

**Returns:** `{"status": "success", "mermaid": "graph LR\n  A[...] -->|superseded_by| B[...]"}`

**Capability required:** `read`

The diagram shows supersede chains and episodic evidence links. Paste the `mermaid` value into any Mermaid renderer to visualize your knowledge graph.

---

### `get_memory_stats`

Returns usage statistics.

**Returns:**
```json
{
  "status": "success",
  "stats": {
    "semantic_decisions": 42,
    "namespace": "default",
    "storage_path": "/path/to/memory"
  }
}
```

**Capability required:** `read`

---

### `get_environment_health`

Returns diagnostic information about the runtime environment.

**Returns:**
```json
{
  "status": "success",
  "health": {
    "git_available": true,
    "git_configured": true,
    "storage_writable": true,
    "disk_space_ok": true,
    "repo_healthy": true,
    "vector_available": true,
    "storage_locked": false,
    "errors": [],
    "warnings": []
  }
}
```

**Capability required:** `read`

---

### `get_audit_logs`

Returns recent MCP call audit log entries.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | integer | 20 | Number of log lines to return |

**Returns:** `{"status": "success", "logs": ["2024-02-01T14:22:00 | agent | record_decision | ..."]}`

**Capability required:** `read`

---

### `export_memory_bundle`

Creates a full backup of the memory storage.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `output_filename` | string | `memory_export.tar.gz` | Path for the output archive |

**Returns:** `{"status": "success", "export_path": "/absolute/path/memory_export.tar.gz"}`

**Capability required:** `purge`

---

### `get_api_specification`

Returns the full OpenRPC-like JSON specification of the LedgerMind API.

**Returns:** Full JSON specification object.

**Capability required:** `read`

---

### `get_relevant_context`

Retrieves and formats memory context for injection into an LLM prompt (Bridge Tool).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `prompt` | string | — | The user's or agent's input prompt |
| `limit` | integer | 3 | Max number of memories to include |

**Returns:** Formatted string beginning with `[LEDGERMIND KNOWLEDGE BASE ACTIVE]` followed by a JSON block, or empty string if nothing is relevant.

**Capability required:** `read`

---

### `record_interaction`

Records a prompt/response pair into episodic memory (Bridge Tool).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `prompt` | string | — | The input prompt |
| `response` | string | — | The agent's response |
| `success` | boolean | `true` | Whether the interaction was successful |

**Returns:** `{"status": "success"}`

**Capability required:** `propose`

---

### `link_interaction_to_decision`

Creates a manual evidence link between an episodic event and a semantic decision.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `event_id` | integer | ✓ | The episodic event ID |
| `decision_id` | string | ✓ | The semantic decision file ID |

**Returns:** `{"status": "success", "message": "Linked event 42 to decisions/..."}`

**Capability required:** `supersede`

---

## Monitoring

When `--metrics-port` is set, Prometheus metrics are available at `http://localhost:<port>/metrics`:

| Metric | Type | Labels |
|---|---|---|
| `agent_memory_tool_calls_total` | Counter | `tool`, `status` (success/error) |
| `agent_memory_tool_latency_seconds` | Histogram | `tool` |

### Rate Limiting

A 1-second cooldown is enforced between write operations (`record_decision`, `supersede_decision`). Rapid writes return a `PermissionError` response.

---

## Error Responses

All tools return consistent error envelopes:

```json
{
  "status": "error",
  "message": "CONFLICT: Target 'database' already has active decisions: [decisions/abc.md]. Did you mean: database_config?"
}
```

Common error messages:

| Message | Cause |
|---|---|
| `CONFLICT: Target '...' already has active decisions` | Use `supersede_decision` or a different target name |
| `Isolation Violation: Decision ... was created by a human` | Cannot modify human records without `ADMIN` role |
| `Capability 'purge' is required` | Operation needs elevated capabilities |
| `Proposal ... is not a proposal` | Wrong file type passed to `accept_proposal` |
