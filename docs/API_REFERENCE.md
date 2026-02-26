# API Reference

Complete reference for all public classes and methods in LedgerMind.

---

## Bridge CLI (Lightweight Memory Access)

These commands are used by the **Hooks Pack** to interact with LedgerMind without starting a full MCP server.

#### `bridge-context`
Returns formatted context for a prompt.
```bash
ledgermind-mcp bridge-context --path ledgermind --prompt "User request"
```

#### `bridge-record`
Records interaction in the background.
```bash
ledgermind-mcp bridge-record --path ledgermind --prompt "t" --response "r" --success
```

---

## Memory

`ledgermind.core.api.memory.Memory`

The main entry point for LedgerMind. Initializes and orchestrates all subsystems.

### Constructor

```python
Memory(
    storage_path: str = "ledgermind",
    config: Optional[LedgermindConfig] = None,
    ttl_days: Optional[int] = None,
    trust_boundary: Optional[TrustBoundary] = None,
    namespace: Optional[str] = None,
    vector_model: Optional[str] = None,
    episodic_store: Optional[EpisodicStore] = None,
    semantic_store: Optional[SemanticStore] = None,
    meta_store_provider: Optional[MetadataStore] = None,
    audit_store_provider: Optional[AuditProvider] = None,
)
```

All parameters are optional. When `config` is provided, it takes precedence over individual keyword arguments. On initialization, `check_environment()` is called automatically.

**Raises:** `ValueError` if storage path cannot be created due to permissions. `RuntimeError` on critical initialization failures.

---

### Writing Decisions

#### `record_decision()`

```python
memory.record_decision(
    title: str,
    target: str,
    rationale: str,
    consequences: Optional[List[str]] = None,
    namespace: str = "default",
    evidence_ids: Optional[List[int]] = None,
    arbiter_callback: Optional[callable] = None
) -> MemoryDecision
```

Records a new structured decision into semantic memory. This is the primary write method for agents.

Before writing, the method:
1. Normalizes `target` through `TargetRegistry`
2. Checks for active conflicts on the target within the given `namespace`
3. If conflict found and vectors available: calculates cosine similarity. If similarity > 0.85, automatically calls `supersede_decision()` (Auto-Supersede)
4. If conflict found and similarity ≤ 0.85: raises `ConflictError` with suggestions (or uses `arbiter_callback` if provided)

**Raises:** `ConflictError` if target has active decisions and auto-resolution fails. `ValueError` if any field is empty. `InvariantViolation` on unexpected persistence failure.

---

#### `supersede_decision()`

```python
memory.supersede_decision(
    title: str,
    target: str,
    rationale: str,
    old_decision_ids: List[str],
    consequences: Optional[List[str]] = None,
    namespace: str = "default",
    evidence_ids: Optional[List[int]] = None
) -> MemoryDecision
```

Explicitly replaces one or more existing decisions with a new one. The old decisions get `status=superseded` and a `superseded_by` backlink. The new decision gets a `supersedes` list.

**Technical Note:** This method delegates the deactivation of old records to `process_event()`, ensuring that all status changes happen atomically within a single transaction.

**Raises:** `ConflictError` if any `old_decision_ids` is not currently active for the given `target`.

---

#### `process_event()`

```python
memory.process_event(
    source: str,
    kind: str,
    content: str,
    context: Optional[Union[DecisionContent, ProposalContent, Dict]] = None,
    intent: Optional[ResolutionIntent] = None,
    namespace: Optional[str] = None
) -> MemoryDecision
```

Low-level method that all write operations ultimately call. Enforces the full pipeline: trust boundary check → duplicate detection → routing → late-bind conflict detection → atomic write → vector indexing → episodic linking.

**Note:** Conflict detection is performed twice: once before starting the transaction and again inside the transaction block (late-bind) to prevent race conditions in highly concurrent environments.

**`source`** must be one of: `user`, `agent`, `system`, `reflection_engine`, `bridge`

**`kind`** must be one of: `decision`, `error`, `config_change`, `assumption`, `constraint`, `result`, `proposal`, `context_snapshot`, `context_injection`, `task`, `call`, `commit_change`, `prompt`

Semantic kinds (`decision`, `constraint`, `assumption`, `proposal`) are persisted to the `SemanticStore`. All others go to `EpisodicStore`.

---

#### `update_decision()`

```python
memory.update_decision(
    decision_id: str,
    updates: Dict[str, Any],
    commit_msg: str,
) -> bool
```

Updates fields of an existing semantic record. Propagates changes to: filesystem + Git, SQLite meta-index, vector index (if `content` or `rationale` changed), episodic journal (creates a log event).

---

#### `forget()`

```python
memory.forget(decision_id: str)
```

Hard-deletes a record from all stores: filesystem, Git (by removing file and committing), SQLite meta-index, vector index. Intended for GDPR compliance or removing hallucinated/incorrect records.

---

### Proposals

#### `accept_proposal()`

```python
memory.accept_proposal(proposal_id: str) -> MemoryDecision
```

Converts a `draft` proposal into an active decision. If the proposal contains `suggested_supersedes`, calls `supersede_decision()` for those IDs automatically.

**Raises:** `FileNotFoundError`, `ValueError` if file is not a proposal or status is not `draft`.

---

#### `reject_proposal()`

```python
memory.reject_proposal(proposal_id: str, reason: str)
```

Marks a proposal as `rejected` with a reason. The record is preserved for audit purposes.

---

#### `run_reflection()`

```python
memory.run_reflection() -> List[str]
```

Manually triggers a full `ReflectionEngine` cycle. Returns a list of created/updated proposal file IDs. In MCP mode, this runs automatically in the background every 4 hours.

**Git Evolution:** When `enable_git` is active, the reflection engine analyzes recent commits indexed into episodic memory. If it detects a pattern of changes (minimum 2 commits) related to a specific target, it automatically generates an "Evolving Pattern" proposal to capture the emerging knowledge.

---

### Searching

#### `search_decisions()`

```python
memory.search_decisions(
    query: str,
    limit: int = 5,
    offset: int = 0,
    namespace: Optional[str] = None,
    mode: str = "balanced",
) -> List[Dict[str, Any]]
```

Hybrid search: vector similarity first, keyword fallback. Results are boosted by their episodic evidence count (up to 2x multiplier).

**`mode`** options:
- `strict` — only `status=active` records
- `balanced` — active preferred, follows `superseded_by` chain to truth
- `audit` — all records regardless of status, no chain following

Each result dict contains: `id`, `score`, `status`, `title`, `target`, `preview`, `kind`, `is_active`, `evidence_count`.

---

#### `get_decisions()`

```python
memory.get_decisions() -> List[str]
```

Returns file IDs of all active semantic records.

---

#### `get_decision_history()`

```python
memory.get_decision_history(decision_id: str) -> List[Dict[str, Any]]
```

Returns the full Git commit history for a specific record. Each entry contains `timestamp`, `message`, `author`, `hash`.

---

#### `get_recent_events()`

```python
memory.get_recent_events(
    limit: int = 10,
    include_archived: bool = False,
) -> List[Dict[str, Any]]
```

Returns recent events from the episodic journal, ordered newest first.

---

#### `generate_knowledge_graph()`

```python
memory.generate_knowledge_graph(target: Optional[str] = None) -> str
```

Generates a Mermaid diagram string showing the knowledge evolution graph (supersede chains + episodic evidence links). Pass `target` to filter to a specific area.

---

## Lifecycle

#### `events` (EventEmitter)

`memory.events`

An internal event bus for real-time notifications.

| Event Type | Data Payload | Description |
|---|---|---|
| `episodic_added` | `{"id": int, "kind": str}` | Triggered when a new episodic event is persisted. |
| `semantic_added` | `{"id": str, "kind": str, "namespace": str}` | Triggered when a new semantic record is created. |

---

#### `run_decay()`

```python
memory.run_decay(dry_run: bool = False) -> DecayReport
```

Executes decay logic for both episodic and semantic memory. Pass `dry_run=True` to see what would be affected without making changes.

Returns `DecayReport` with fields: `archived`, `pruned`, `retained_by_link`, `semantic_forgotten`.

---

#### `run_maintenance()`

```python
memory.run_maintenance() -> Dict[str, Any]
```

Full maintenance pass: `sync_meta_index()`, `IntegrityChecker.validate()`, `run_decay()`, `MergeEngine.scan_for_duplicates()`.

Returns a report dict with keys `decay`, `merging`, `integrity`.

---

#### `sync_git()`

```python
memory.sync_git(repo_path: str = ".", limit: int = 20) -> int
```

Imports the last `limit` Git commits from `repo_path` into episodic memory as `commit_change` events. Returns number of commits indexed.

---

#### `link_evidence()`

```python
memory.link_evidence(event_id: int, semantic_id: str)
```

Manually creates an immortal link from an episodic event to a semantic record. This prevents the episodic event from ever being archived or pruned, and boosts the semantic record's search score.

---

#### `check_environment()`

```python
memory.check_environment() -> Dict[str, Any]
```

Pre-flight system check. Returns a dict with keys: `git_available`, `git_configured`, `storage_writable`, `disk_space_ok`, `repo_healthy`, `vector_available`, `storage_locked`, `lock_owner`, `errors`, `warnings`.

---

#### `get_stats()`

```python
memory.get_stats() -> Dict[str, Any]
```

Returns `semantic_decisions` (count), `namespace`, `storage_path`.

---

#### `bootstrap_project_context()`

```python
memory.bootstrap_project_context(path: str = ".") -> str
```

(Available via MCP) Performs a deep scan of the project at the given `path`. It analyzes the directory tree (up to 7 levels), identifies key configuration files, and reads all `.md` files. 

Returns a formatted Markdown report designed to be consumed by an AI agent, including a specific **Memory Storage Policy** for maintaining a flat memory structure.

---

---

## IntegrationBridge

`ledgermind.core.api.bridge.IntegrationBridge`

High-level facade designed for embedding LedgerMind into CLI tools and agents. Wraps `Memory` with simplified methods and handles errors gracefully.

### Constructor

```python
IntegrationBridge(
    memory_path: str = "../.ledgermind",
    relevance_threshold: float = 0.7,
)
```

### Methods

#### `get_context_for_prompt()`

```python
bridge.get_context_for_prompt(prompt: str, limit: int = 3) -> str
```

Searches memory for records relevant to `prompt`. Returns a formatted JSON string prefixed with `[LEDGERMIND KNOWLEDGE BASE ACTIVE]` for direct inclusion in an LLM prompt. Returns empty string if no results above `relevance_threshold`.

Each item includes: `id`, `title`, `target`, `kind`, `score`, `recency`, `content` (full formatted text with rationale).

---

#### `record_interaction()`

```python
bridge.record_interaction(prompt: str, response: str, success: bool = True)
```

Records a prompt/response pair into episodic memory. Automatically detects errors in the response by scanning for keywords (`error`, `failed`, `exception`, `traceback`, `fatal`).

---

#### `trigger_reflection()`

```python
bridge.trigger_reflection()
```

Manually triggers a reflection cycle.

---

#### `run_maintenance()`

```python
bridge.run_maintenance() -> Dict[str, Any]
```

Runs full system maintenance. Returns a maintenance report.

---

#### `check_health()`

```python
bridge.check_health() -> Dict[str, Any]
```

Runs `memory.check_environment()` and returns the result.

---

#### `get_stats()`

```python
bridge.get_stats() -> Dict[str, Any]
```

Returns extended statistics: `episodic_count`, `semantic_count`, `vector_count`, `health`.

---

#### `.memory` property

```python
bridge.memory  # -> Memory instance
```

Direct access to the underlying `Memory` object for advanced operations.

---

---

## MemoryTransferManager

`ledgermind.core.api.transfer.MemoryTransferManager`

Handles backup and restore of the entire memory storage.

### Constructor

```python
MemoryTransferManager(storage_path: str)
```

### Methods

#### `export_to_tar()`

```python
manager.export_to_tar(output_path: str) -> str
```

Creates a `.tar.gz` archive of the entire storage directory. Returns the final path (adds `.tar.gz` suffix if missing).

---

#### `import_from_tar()`

```python
manager.import_from_tar(tar_path: str, restore_path: str)
```

Extracts a memory archive to `restore_path`. Uses Python 3.12+ safe extraction filter when available.

---

---

## TargetRegistry

`ledgermind.core.core.targets.TargetRegistry`

Manages canonical target names to prevent memory fragmentation. Persists to `targets.json`.

### Methods

| Method | Signature | Description |
|---|---|---|
| `normalize()` | `(name: str) -> str` | Returns canonical name via exact match → alias → case-insensitive lookup. |
| `register()` | `(name, description="", aliases=None)` | Registers a new canonical target with optional aliases. |
| `suggest()` | `(query, limit=3) -> List[str]` | Returns close matches using `difflib.get_close_matches` (cutoff 0.6). |
