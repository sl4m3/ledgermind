# API Reference

Complete reference for all public APIs in LedgerMind.

---

## Introduction

This document provides a complete API reference for:

- **Memory API** — Core memory system interface
- **IntegrationBridge API** — High-level integration layer
- **Data Models** — All Pydantic schemas
- **MCP Server API** — Model Context Protocol server interface

**Audience**: Developers integrating LedgerMind into applications or extensions.

---

## Memory API

**Module**: `ledgermind.core.api.memory`

**Class**: `Memory`

The `Memory` class is the main entry point for all LedgerMind operations. It coordinates storage, reasoning, and lifecycle management.

### Initialization

```python
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import LedgermindConfig, TrustBoundary

# Create with default configuration
memory = Memory()

# Create with custom configuration
config = LedgermindConfig(
    storage_path="../.ledgermind",
    ttl_days=30,
    trust_boundary=TrustBoundary.AGENT_WITH_INTENT,
    namespace="my_agent",
    vector_model="../.ledgermind/models/my-model.gguf",
    vector_workers=4
)

memory = Memory(config=config)

# Create with dependency injection
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.stores.semantic import SemanticStore

custom_episodic = EpisodicStore("/custom/episodic.db")
custom_semantic = SemanticStore(
    repo_path="/custom/semantic",
    trust_boundary=TrustBoundary.HUMAN_ONLY
)

memory = Memory(
    episodic_store=custom_episodic,
    semantic_store=custom_semantic
)
```

#### Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `storage_path` | str | `"../.ledgermind"` | Base directory for all memory files |
| `ttl_days` | int | `30` | Time-to-live for episodic events (days) |
| `trust_boundary` | TrustBoundary | `AGENT_WITH_INTENT` | Security boundary for operations |
| `namespace` | str | `"default"` | Logical partition for isolation |
| `vector_model` | str | `"../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf"` | Path to embedding model |
| `vector_workers` | int | `0` (auto-detect) | Number of workers for multi-process encoding |

### Core Operations

#### process_event()

Main entry point for all events. Routes to appropriate storage based on event kind and conflicts.

```python
def process_event(
    self,
    source: Literal["user", "agent", "system", "reflection_engine", "bridge"],
    kind: Literal["decision", "error", "config_change", "assumption", "constraint",
                "result", "proposal", "context_snapshot", "context_injection",
                "task", "call", "commit_change", "prompt", "intervention",
                "reflection_summary"],
    content: str,
    context: Union[DecisionContent, ProposalContent, DecisionStream, Dict],
    intent: Optional[ResolutionIntent] = None
) -> MemoryDecision:
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|-----------|-------------|
| `source` | str | Yes | Origin of the event |
| `kind` | str | Yes | Event type (determines storage) |
| `content` | str | Yes | Event payload |
| `context` | object | Yes | Structured metadata (varies by kind) |
| `intent` | ResolutionIntent | No | For supersede operations only |

**Returns**: `MemoryDecision` object with:
- `should_persist`: Whether event was stored
- `store_type`: `"episodic"`, `"semantic"`, or `"none"`
- `reason`: Explanation of routing decision

**Example**:

```python
from ledgermind.core.core.schemas import MemoryEvent, KIND_ERROR

# Record an error event
event = MemoryEvent(
    source="agent",
    kind=KIND_ERROR,
    content="Failed to connect to database",
    context={
        "error_code": "DB_CONNECTION_FAILED",
        "retry_count": 3
    }
)

result = memory.process_event(event)

if result.should_persist:
    print(f"Stored in {result.store_type}: {result.reason}")
else:
    print(f"Not stored: {result.reason}")
```

#### record_decision()

Records a strategic decision to semantic memory with conflict checking.

```python
def record_decision(
    self,
    title: str,
    target: str,
    rationale: str,
    consequences: Optional[List[str]] = None,
    evidence_ids: Optional[List[int]] = None,
    arbiter_callback: Optional[Callable] = None
) -> MemoryDecision:
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|-----------|-------------|
| `title` | str (min: 1) | Yes | Short title of the decision |
| `target` | str (min: 3) | Yes | The object or area this decision applies to |
| `rationale` | str (min: 10) | Yes | Detailed explanation of why this decision was made |
| `consequences` | List[str] | No | List of rules or effects resulting from this decision |
| `evidence_ids` | List[int] | No | IDs of episodic events supporting this decision |
| `arbiter_callback` | Callable | No | Custom function for conflict resolution |

**Returns**: `MemoryDecision` with `decision_id` if successful

**Conflict Handling**:

If an active decision exists for the same target and namespace:
- Without `arbiter_callback`: Rejects with reason about requiring `ResolutionIntent`
- With `arbiter_callback`: Calls the callback to determine resolution

**Example**:

```python
# Basic decision
result = memory.record_decision(
    title="Use PostgreSQL for production",
    target="database",
    rationale="PostgreSQL provides ACID compliance, JSONB support, "
             "and proven reliability for our workload.",
    consequences=[
        "Install PostgreSQL 15+",
        "Configure connection pooling",
        "Migrate existing data schema"
    ]
)

if result.should_persist:
    decision_id = result.metadata.get("file_id")
    print(f"Decision recorded: {decision_id}")
```

**With Conflict Resolution**:

```python
def my_arbiter(new_decision, old_decisions):
    """
    Custom arbiter that uses an LLM to resolve conflicts.
    """
    # Your custom logic here
    # Return "supersede" to accept new decision
    # Return "deprecate" to keep old but mark deprecated
    # Return "abort" to reject new decision
    return "supersede"

result = memory.record_decision(
    title="Use MongoDB for production",
    target="database",
    rationale="MongoDB provides flexibility and horizontal scaling.",
    arbiter_callback=my_arbiter
)
```

#### supersede_decision()

Replaces existing decisions with a new one, maintaining graph integrity.

```python
def supersede_decision(
    self,
    title: str,
    target: str,
    rationale: str,
    old_decision_ids: List[str],
    consequences: Optional[List[str]] = None
) -> MemoryDecision:
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|-----------|-------------|
| `title` | str (min: 1) | Yes | Short title of the new decision |
| `target` | str (min: 3) | Yes | Target being updated |
| `rationale` | str (min: 15) | Yes | Detailed explanation of why old decisions are being superseded |
| `old_decision_ids` | List[str] (min: 1) | Yes | IDs of decisions to supersede |
| `consequences` | List[str] | No | List of rules or effects of the new decision |

**Process**:

1. Validates all `old_decision_ids` exist
2. Updates each old decision with `superseded_by` pointing to new decision
3. Records new decision with same target
4. Creates Git commit with all changes

**Example**:

```python
result = memory.supersede_decision(
    title="Use PostgreSQL instead of MySQL",
    target="database",
    rationale="PostgreSQL provides better performance and ACID compliance. "
             "Our benchmarks show 40% improvement over MySQL.",
    old_decision_ids=["mysql_production_decision_abc123"],
    consequences=[
        "Migrate existing data",
        "Update connection strings in all services"
    ]
)

print(f"Superseded old decisions with: {result.metadata.get('file_id')}")
```

#### accept_proposal()

Promotes a draft proposal to an active decision.

```python
def accept_proposal(self, proposal_id: str) -> MemoryDecision:
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|-----------|-------------|
| `proposal_id` | str | Yes | The filename of the proposal to accept |

**Process**:

1. Loads proposal from disk
2. Validates proposal status is `DRAFT`
3. Converts proposal to decision
4. Updates file with new metadata
5. Git commit

**Example**:

```python
result = memory.accept_proposal("use_postgresql_cache_abc123")

if result.should_persist:
    print(f"Proposal accepted and promoted to decision")
else:
    print(f"Failed to accept: {result.reason}")
```

#### reject_proposal()

Rejects a draft proposal with a reason.

```python
def reject_proposal(self, proposal_id: str, reason: str):
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|-----------|-------------|
| `proposal_id` | str | Yes | The filename of the proposal to reject |
| `reason` | str | Yes | Explanation of why the proposal was rejected |

**Process**:

1. Loads proposal from disk
2. Validates proposal exists and is draft
3. Updates proposal status to `REJECTED`
4. Updates `counter_evidence` (tracks failures)
5. Git commit

**Example**:

```python
memory.reject_proposal(
    proposal_id="use_mongodb_cache_abc123",
    reason="Testing showed MongoDB provides insufficient ACID guarantees for our transactional requirements."
)
```

#### search_decisions()

Hybrid search combining keyword and vector similarity with evidence boost.

```python
def search_decisions(
    self,
    query: str,
    limit: int = 5,
    mode: Literal["strict", "balanced", "audit"] = "balanced",
    namespace: str = "default"
) -> List[Dict[str, Any]]:
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `query` | str | — | Search query string |
| `limit` | int | `5` | Maximum number of results (1-50) |
| `mode` | str | `"balanced"` | Search mode |
| `namespace` | str | `"default"` | Logical partition to search within |

**Search Modes**:

| Mode | Returns | Description |
|-------|----------|-------------|
| `strict` | Only active decisions | Production queries, no history |
| `balanced` | Active first, then history | General purpose (default) |
| `audit` | All including superseded | Debugging, full history |

**Returns**: List of result dictionaries

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Decision ID |
| `title` | str | Decision title |
| `target` | str | Decision target |
| `score` | float | Relevance score (0.0-1.0) |
| `status` | str | Decision status |
| `kind` | str | Decision type |
| `preview` | str | First 200 chars of content |
| `content` | str | Full content (optional, only in audit mode) |

**Evidence Boost**: Decisions with linked events receive **+20% boost per link** to their final score.

**Example**:

```python
# Keyword-only search
results = memory.search_decisions("database", mode="strict")

# Hybrid search with vector (if available)
results = memory.search_decisions("database migrations", limit=10, mode="balanced")

# Namespace-specific search
results = memory.search_decisions("authentication", namespace="backend_agent")

for result in results:
    print(f"{result['title']} (score: {result['score']:.2f})")
```

#### get_decisions()

Returns all decision IDs in storage.

```python
def get_decisions(self) -> List[str]:
```

**Returns**: List of decision filenames (IDs)

**Example**:

```python
all_ids = memory.get_decisions()
print(f"Total decisions: {len(all_ids)}")
```

#### get_decision_history()

Retrieves complete supersede chain for a decision.

```python
def get_decision_history(self, decision_id: str) -> List[Dict[str, Any]]:
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|-----------|-------------|
| `decision_id` | str | Yes | Decision ID to trace |

**Returns**: List of history entries in chronological order (oldest first)

| Field | Type | Description |
|-------|------|-------------|
| `version` | int | Version number in chain (0 = oldest) |
| `decision_id` | str | Decision filename |
| `timestamp` | str | When this version was created |
| `changes` | List[str] | List of field changes |

**Example**:

```python
history = memory.get_decision_history("use_postgresql_cache_abc123")

for entry in history:
    print(f"v{entry['version']}: {entry['decision_id']} ({entry['timestamp']})")
    for change in entry.get('changes', []):
        print(f"  - {change}")
```

#### get_recent_events()

Retrieves recent episodic events with optional filtering.

```python
def get_recent_events(
    self,
    limit: int = 10,
    include_archived: bool = False
) -> List[Dict[str, Any]]:
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `limit` | int | `10` | Maximum number of events |
| `include_archived` | bool | `False` | Whether to include archived events |

**Returns**: List of event dictionaries

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Event ID |
| `source` | str | Origin: user, agent, system, reflection_engine, bridge |
| `kind` | str | Event type |
| `content` | str | Event payload |
| `context` | Dict | Structured metadata (JSON-parsed) |
| `timestamp` | str | ISO 8601 datetime |
| `status` | str | `"active"` or `"archived"` |
| `linked_id` | str or None | Link to semantic decision (if any) |
| `link_strength` | float | Evidence weight (0.0-1.0) |

**Example**:

```python
# Get last 20 active events
events = memory.get_recent_events(limit=20, include_archived=False)

# Get everything including archived
all_events = memory.get_recent_events(limit=100, include_archived=True)

for event in events:
    print(f"[{event['timestamp']}] {event['source']}: {event['content'][:50]}...")
```

#### link_evidence()

Links an episodic event to a semantic decision as supporting evidence.

```python
def link_evidence(self, event_id: int, semantic_id: str):
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|-----------|-------------|
| `event_id` | int | Yes | ID of episodic event from `get_recent_events()` |
| `semantic_id` | str | Yes | ID of semantic decision |

**Effect**: Linked events become "immortal" — they never decay.

**Example**:

```python
# First, record an interaction
event = MemoryEvent(
    source="agent",
    kind="result",
    content="Successfully deployed PostgreSQL migration v2",
    context={"success": True}
)

result = memory.process_event(event)
event_id = result.metadata.get("event_id")

# Then link it to a decision
memory.link_evidence(event_id, "use_postgresql_cache_abc123")
```

#### update_decision()

Updates metadata of an existing decision.

```python
def update_decision(
    self,
    decision_id: str,
    updates: Dict[str, Any],
    commit_msg: str
) -> bool:
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|-----------|-------------|
| `decision_id` | str | Yes | Decision ID to update |
| `updates` | Dict | Yes | Fields to update (subset of context) |
| `commit_msg` | str | Yes | Git commit message |

**Updateable Fields**: Any field within decision's `context` dictionary.

**Returns**: `True` if successful, raises exception on failure

**Example**:

```python
success = memory.update_decision(
    decision_id="use_postgresql_cache_abc123",
    updates={
        "confidence": 0.95,
        "vitality": "active",
        "consequences": ["Original consequence", "New consequence"]
    },
    commit_msg="Update confidence and mark as active"
)
```

#### sync_git()

Indexes recent Git commits into episodic memory.

```python
def sync_git(self, repo_path: str = ".", limit: int = 20) -> int:
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `repo_path` | str | `"."` | Path to Git repository (must be within CWD) |
| `limit` | int | `20` | Maximum number of commits to index |

**Process**:

1. Gets last indexed commit hash from config
2. Fetches new commits since that hash
3. Infers target from changed files or commit message
4. Records each commit as `MemoryEvent(kind="commit_change")`
5. Updates last indexed hash in config

**Returns**: Number of commits indexed

**Example**:

```python
# Sync from current directory
count = memory.sync_git(".", limit=50)

# Sync from specific directory
count = memory.sync_git("./backend", limit=100)
```

#### forget()

Hard-deletes a decision from filesystem and metadata.

```python
def forget(self, decision_id: str):
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|-----------|-------------|
| `decision_id` | str | Yes | Decision ID to delete |

**Process**:

1. Deletes Markdown file from `semantic/` directory
2. Removes entry from metadata index
3. Unlinks all associated episodic events
4. Creates Git commit with deletion message

**Use Case**: GDPR compliance, removing incorrect decisions.

**Example**:

```python
memory.forget("deprecated_decision_abc123")
print("Decision permanently deleted")
```

#### generate_knowledge_graph()

Generates a Mermaid diagram of knowledge evolution.

```python
def generate_knowledge_graph(self, target: Optional[str] = None) -> str:
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `target` | str | `None` | Optional filter for specific target |

**Returns**: Mermaid diagram string

**Example**:

```python
# Graph for all decisions
graph = memory.generate_knowledge_graph()

# Graph for specific target
graph = memory.generate_knowledge_graph(target="database")

print(graph)
```

#### run_reflection()

Triggers reflection cycle to generate proposals.

```python
def run_reflection(self) -> List[str]:
```

**Process**:

1. Runs distillation to extract procedural patterns
2. Clusters evidence by target
3. Updates existing DecisionStream objects
4. Applies vitality decay to unused streams
5. Generates new proposals if patterns detected

**Returns**: List of proposal IDs created/updated

**Example**:

```python
proposal_ids = memory.run_reflection()
print(f"Generated/Updated {len(proposal_ids)} proposals")
```

#### run_decay()

Triggers decay cycle to prune old data.

```python
def run_decay(self) -> DecayReport:
```

**Process**:

1. Evaluates episodic events for age
2. Archives events older than TTL
3. Prunes archived events older than TTL
4. Evaluates semantic decisions for confidence decay
5. Forgets semantic decisions with confidence < threshold

**Returns**: `DecayReport` object

| Field | Type | Description |
|-------|------|-------------|
| `archived` | int | Number of events archived |
| `pruned` | int | Number of events permanently deleted |
| `retained` | int | Number of events kept (linked or decisions) |
| `semantic_forgotten` | int | Number of semantic decisions deleted |

**Example**:

```python
report = memory.run_decay()
print(f"Archived: {report.archived}, Pruned: {report.pruned}, Retained: {report.retained}")
```

#### check_environment()

Performs pre-flight check of the environment.

```python
def check_environment(self) -> Dict[str, Any]:
```

**Returns**: Dictionary with health status

| Field | Type | Description |
|-------|------|-------------|
| `git_available` | bool | Whether Git is installed and in PATH |
| `git_configured` | bool | Whether Git has user.name and user.email configured |
| `storage_writable` | bool | Whether storage path is writable |
| `disk_space_ok` | bool | Whether sufficient disk space available |
| `repo_healthy` | bool | Whether Git repository is healthy |
| `vector_available` | bool | Whether vector search is enabled |
| `storage_locked` | bool | Whether storage is locked by another process |
| `lock_owner` | str or None | PID of lock owner if locked |
| `errors` | List[str] | List of error messages |
| `warnings` | List[str] | List of warning messages |

**Example**:

```python
health = memory.check_environment()

print(f"Git Available: {'✓' if health['git_available'] else '✗'}")
print(f"Storage Writable: {'✓' if health['storage_writable'] else '✗'}")

if health['errors']:
    print("Errors:")
    for error in health['errors']:
        print(f"  - {error}")
```

#### get_stats()

Returns memory usage statistics.

```python
def get_stats(self) -> Dict[str, int]:
```

**Returns**: Dictionary with counts

| Field | Type | Description |
|-------|------|-------------|
| `episodic_count` | int | Total episodic events |
| `semantic_count` | int | Total semantic decisions |
| `vector_count` | int | Total vector embeddings |

**Example**:

```python
stats = memory.get_stats()
print(f"Episodic Events: {stats['episodic_count']}")
print(f"Semantic Decisions: {stats['semantic_count']}")
print(f"Vector Embeddings: {stats['vector_count']}")
```

---

## IntegrationBridge API

**Module**: `ledgermind.core.api.bridge`

**Class**: `IntegrationBridge`

High-level bridge for integrating LedgerMind into CLI tools and applications. Provides streamlined context injection and interaction recording.

### Initialization

```python
from ledgermind.core.api.bridge import IntegrationBridge

bridge = IntegrationBridge(
    memory_path="../.ledgermind",
    relevance_threshold=0.7,    # Only return results with 70%+ relevance
    retention_turns=10,          # Remember context for N turns
    vector_model="../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf",
    default_cli=["gemini"],      # Default LLMs for arbitration
    memory_instance=None           # Optional: reuse existing Memory instance
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `memory_path` | str | `"../.ledgermind"` | Path to memory storage |
| `relevance_threshold` | float | `0.7` | Minimum relevance score for context (0.0-1.0) |
| `retention_turns` | int | `10` | How many turns to remember context |
| `vector_model` | str | Default model path | Path to GGUF model |
| `default_cli` | List[str] | `["gemini"]` | Default LLMs for arbitration |
| `memory_instance` | Memory | `None` | Optional existing Memory instance |

### Context & Recording

#### get_context_for_prompt()

Retrieves and formats relevant context for a given user prompt.

```python
def get_context_for_prompt(self, prompt: str, limit: int = 3) -> str:
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `prompt` | str | — | User's prompt |
| `limit` | int | `3` | Maximum number of memories to retrieve |

**Returns**: Formatted JSON string with prefix

**Output Format**:

```json
{
  "source": "ledgermind",
  "memories": [
    {
      "id": "decision_id",
      "title": "Decision Title",
      "target": "target",
      "score": 0.85,
      "status": "active",
      "kind": "decision",
      "path": "/absolute/path/to/decision_id.md",
      "content": "Decision content...",
      "rationale": "Why this decision was made...",
      "instruction": "Key fields are injected. Use 'cat /path/to/file.md' if you need full history.",
      "procedural_guide": [
        "1. Step one",
        "2. Step two"
      ]
    }
  ]
}
```

**Example**:

```python
context = bridge.get_context_for_prompt(
    "How should I handle database migrations?",
    limit=3
)

print(context)
```

#### record_interaction()

Records a completed interaction (prompt and response) into episodic memory.

```python
def record_interaction(
    self,
    prompt: str,
    response: str,
    success: bool = True,
    metadata: Dict[str, Any] = None
):
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `prompt` | str | — | User's original prompt |
| `response` | str | — | Agent's response |
| `success` | bool | `True` | Whether the interaction was successful |
| `metadata` | Dict | `None` | Optional additional metadata |

**Process**:

1. Strips LedgerMind context from prompt (to avoid recursive storage)
2. Records as `MemoryEvent(source="bridge", kind="prompt")`
3. Records response as `MemoryEvent(source="agent", kind="result")`
4. Links to relevant semantic decisions if detected

**Example**:

```python
bridge.record_interaction(
    prompt="Fix authentication bug",
    response="Updated JWT validation in middleware",
    success=True,
    metadata={
        "tool_used": "edit_file",
        "duration_seconds": 45
    }
)
```

#### reset_session()

Clears session context cache (prevents repeating same context).

```python
def reset_session(self):
```

**Effect**: Resets `_active_context_ids` cache and `_turn_counter`.

**Use Case**: Starting a new conversation session.

---

### Memory Operations (Proxies)

The following methods proxy to the underlying `Memory` instance. See the [Memory API](#memory-api-coreapimemorypy) section for detailed behavior.

#### record_decision()

```python
def record_decision(
    self,
    title: str,
    target: str,
    rationale: str,
    consequences: Optional[List[str]] = None,
    evidence_ids: Optional[List[int]] = None
) -> MemoryDecision:
```

**Difference from Memory API**: Uses `arbitrate_with_cli()` for automatic LLM arbitration.

#### supersede_decision()

```python
def supersede_decision(
    self,
    title: str,
    target: str,
    rationale: str,
    old_decision_ids: List[str],
    consequences: Optional[List[str]] = None
) -> MemoryDecision:
```

**Difference from Memory API**: Automatically uses `arbitrate_with_cli()`.

#### accept_proposal()

```python
def accept_proposal(self, proposal_id: str) -> MemoryDecision:
```

**Difference from Memory API**: Proxies to `Memory.accept_proposal()`.

#### reject_proposal()

```python
def reject_proposal(self, proposal_id: str, reason: str):
```

**Difference from Memory API**: Proxies to `Memory.reject_proposal()`.

#### search_decisions()

```python
def search_decisions(
    self,
    query: str,
    limit: int = 5,
    mode: str = "balanced"
) -> List[Dict[str, Any]]:
```

**Difference from Memory API**: Proxies to `Memory.search_decisions()`.

#### get_decisions()

```python
def get_decisions(self) -> List[str]:
```

**Difference from Memory API**: Proxies to `Memory.get_decisions()`.

#### get_decision_history()

```python
def get_decision_history(self, decision_id: str) -> List[Dict[str, Any]]:
```

**Difference from Memory API**: Proxies to `Memory.get_decision_history()`.

#### get_recent_events()

```python
def get_recent_events(
    self,
    limit: int = 10,
    include_archived: bool = False
) -> List[Dict[str, Any]]:
```

**Difference from Memory API**: Proxies to `Memory.get_recent_events()`.

#### link_evidence()

```python
def link_evidence(self, event_id: int, semantic_id: str):
```

**Difference from Memory API**: Proxies to `Memory.link_evidence()`.

#### update_decision()

```python
def update_decision(self, decision_id: str, updates: Dict[str, Any], commit_msg: str) -> bool:
```

**Difference from Memory API**: Proxies to `Memory.update_decision()`.

#### sync_git()

```python
def sync_git(self, repo_path: str = ".", limit: int = 20) -> int:
```

**Difference from Memory API**: Proxies to `Memory.sync_git()`.

#### forget()

```python
def forget(self, decision_id: str):
```

**Difference from Memory API**: Proxies to `Memory.forget()`.

#### generate_knowledge_graph()

```python
def generate_knowledge_graph(self, target: Optional[str] = None) -> str:
```

**Difference from Memory API**: Proxies to `Memory.generate_knowledge_graph()`.

### Diagnostics

#### check_health()

```python
def check_health(self) -> Dict[str, Any]:
```

Proxies to `Memory.check_environment()`.

#### arbitrate_with_cli()

Internal method for automatic LLM arbitration.

```python
def arbitrate_with_cli(self, cli_list: List[str], new_decision: Any, old_decisions: Any) -> str:
    """
    Uses configured LLM (from arbitration_mode setting) to resolve conflicts.

    Returns "supersede", "deprecate", or "abort" based on LLM decision.
    """
```

---

## Data Models Reference

### MemoryEvent

**Location**: `core/core/schemas.py`

Base model for all events processed by the memory system.

```python
class MemoryEvent(BaseModel):
    schema_version: int = Field(default=1)
    source: Literal["user", "agent", "system", "reflection_engine", "bridge"]
    kind: Literal["decision", "error", "config_change", "assumption", "constraint",
                "result", "proposal", "context_snapshot", "context_injection",
                "task", "call", "commit_change", "prompt", "intervention",
                "reflection_summary"]
    content: StrictStr
    context: Union[DecisionContent, ProposalContent, DecisionStream, Dict]
    timestamp: datetime = Field(default_factory=datetime.now)
```

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Data format version for migrations |
| `source` | str | Who created the event |
| `kind` | str | Event type determining storage location |
| `content` | str | Event payload (min 1 char) |
| `context` | object | Structured metadata (varies by kind) |
| `timestamp` | datetime | When the event occurred |

**Event Kinds**:

| Kind | Storage | Description |
|------|----------|-------------|
| `decision` | Semantic | Long-term strategic decisions |
| `proposal` | Semantic | Draft hypotheses for evaluation |
| `intervention` | Semantic | Normative acts by system |
| `constraint` | Semantic | System limitations or rules |
| `assumption` | Semantic | Beliefs without full evidence |
| `error` | Episodic | Error events |
| `result` | Episodic | Execution results |
| `config_change` | Episodic | Configuration updates |
| `task` | Episodic | Task descriptions |
| `call` | Episodic | Tool/Function calls |
| `commit_change` | Episodic | Git commits |
| `prompt` | Episodic | User inputs |
| `context_snapshot` | Episodic | Environment state |
| `context_injection` | Episodic | Injected memory into agent context |
| `reflection_summary` | Episodic | Reflection cycle results |

---

### DecisionContent

```python
class DecisionContent(BaseModel):
    title: StrictStr
    target: TargetStr
    status: Literal["active", "deprecated", "superseded"]
    rationale: RationaleStr
    namespace: str = "default"
    keywords: List[str]
    evidence_event_ids: List[int]
    consequences: List[str]
    superseded_by: Optional[str]
    attachments: List[Dict[str, str]]
    procedural: Optional[ProceduralContent]
```

**Validation Rules**:

- `title`: Minimum 1 character
- `target`: Minimum 3 characters
- `rationale`: Minimum 10 characters
- `namespace`: Default "default", can be set to isolate agents

---

### ProposalContent

```python
class ProposalContent(BaseModel):
    title: StrictStr
    target: TargetStr
    status: ProposalStatus = Field(default=ProposalStatus.DRAFT)
    rationale: RationaleStr
    namespace: str = "default"
    confidence: float = Field(ge=0.0, le=1.0)

    # Epistemic Model Fields
    keywords: List[str]
    strengths: List[str]              # Arguments in favor
    objections: List[str]           # Active counter-arguments
    counter_patterns: List[str]        # Scenarios where prediction failed
    alternative_ids: List[str]        # Competing proposal IDs
    evidence_event_ids: List[int]
    counter_evidence_event_ids: List[int]

    # Additional Fields
    suggested_consequences: List[str]
    suggested_supersedes: List[str]

    # MemP Extension: Procedural Data
    procedural: Optional[ProceduralContent]

    # Tracking
    first_observed_at: datetime
    last_observed_at: datetime
    hit_count: int = 0
    miss_count: int = 0
    ready_for_review: bool = False
```

**Proposal Status Values**:

| Status | Description |
|--------|-------------|
| `DRAFT` | Initial hypothesis |
| `ACCEPTED` | Promoted to decision |
| `REJECTED` | Disproven by evidence |
| `FALSIFIED` | Contradicted by new data |

---

### DecisionStream

```python
class DecisionStream(BaseModel):
    decision_id: StrictStr
    target: TargetStr
    title: StrictStr
    rationale: RationaleStr
    namespace: str = "default"
    scope: PatternScope = Field(default=PatternScope.LOCAL)
    status: Literal["active", "deprecated", "superseded"]

    # Lifecycle Fields
    phase: DecisionPhase = Field(default=DecisionPhase.PATTERN)
    vitality: DecisionVitality = Field(default=DecisionVitality.ACTIVE)
    provenance: Literal["internal", "external"]

    # Context & Links
    keywords: List[str]
    evidence_event_ids: List[int]
    consequences: List[str]
    supersedes: List[str]
    superseded_by: Optional[str]
    attachments: List[Dict[str, str]]

    # MemP Linking
    procedural: Optional[ProceduralContent]
    procedural_ids: List[str]

    # Tracking
    frequency: int = 0
    unique_contexts: int = 0
    hit_count: int = 0
    confidence: float = 1.0

    # Metrics
    stability_score: float = 0.0
    reinforcement_density: float = 0.0
    coverage: float = 0.0
    lifetime_days: float = 0.0

    # Utility
    estimated_removal_cost: float = 0.0
    estimated_utility: float = 0.0

    # Metadata
    first_seen: datetime
    last_seen: datetime
    schema_version: int = 1
```

**Decision Phase Values**:

| Phase | Description |
|--------|-------------|
| `PATTERN` | Initial observation (freq < 3, conf < 0.5) |
| `EMERGENT` | Reinforced pattern (freq >= 3 or conf >= 0.5) |
| `CANONICAL` | Stable knowledge (high coverage, stability) |

**Vitality Values**:

| Vitality | Description | Decay Rate |
|-----------|-------------|-----------|
| `ACTIVE` | Used in last 7 days | None |
| `DECAYING` | Used 7-30 days ago | -0.05 per week |
| `DORMANT` | Used > 30 days ago | -0.2 per week |

---

### ProceduralContent & ProceduralStep

```python
class ProceduralContent(BaseModel):
    steps: List[ProceduralStep]
    target_task: str
    success_evidence_ids: List[int]

class ProceduralStep(BaseModel):
    action: str
    rationale: Optional[str]
    expected_outcome: Optional[str]
```

**Purpose**: Stores distilled procedural knowledge from successful trajectories.

**Usage**: Automatically populated by `DistillationEngine` during reflection cycles.

---

### ResolutionIntent

```python
class ResolutionIntent(BaseModel):
    resolution_type: Literal["supersede", "deprecate", "abort"]
    rationale: str
    target_decision_ids: List[str]
```

**Purpose**: Specifies how to handle conflicts when recording a new decision.

**Resolution Types**:

| Type | Action | When to Use |
|------|--------|-------------|
| `supersede` | Replace old with new | Old decisions are wrong |
| `deprecate` | Mark old as outdated | Old decisions are now obsolete |
| `abort` | Cancel operation | Conflict resolution failed |

---

### MemoryDecision

```python
class MemoryDecision(BaseModel):
    should_persist: bool
    store_type: Literal["episodic", "semantic", "none"]
    reason: str
    priority: int = Field(default=0, ge=0, le=10)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

**Purpose**: Return type for all memory operations indicating success/failure and reasoning.

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `should_persist` | bool | Whether the event was stored |
| `store_type` | str | Where it was stored (or why not) |
| `reason` | str | Explanation of routing decision |
| `priority` | int | 0-10 importance level |
| `metadata` | dict | Additional data (file_id, event_id, etc.) |

---

### LedgermindConfig

```python
class LedgermindConfig(BaseModel):
    storage_path: str = Field(default="../.ledgermind")
    ttl_days: int = Field(default=30, ge=1)
    trust_boundary: TrustBoundary = Field(default=TrustBoundary.AGENT_WITH_INTENT)
    namespace: str = Field(default="default")
    vector_model: str = Field(default="../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf")
    vector_workers: int = Field(default=0, ge=0)
    enable_git: bool = Field(default=True)
    relevance_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
```

**Purpose**: Configuration model for memory initialization.

---

## MCP Server API

**Module**: `ledgermind.server.server`

**Class**: `MCPServer`

Model Context Protocol server with 15 tools, role-based access control, and security features.

### MCPServer Class

```python
class MCPServer:
    def __init__(
        self,
        memory: Memory,
        server_name: str = "Ledgermind",
        storage_path: str = "ledgermind",
        capabilities: Optional[Dict[str, bool]] = None,
        metrics_port: Optional[int] = None,
        rest_port: Optional[int] = None,
        default_role: MCPRole = MCPRole.AGENT,
        start_worker: bool = True,
        webhooks: Optional[List[str]] = None
    ):
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `memory` | Memory | — | Memory instance to use |
| `server_name` | str | `"Ledgermind"` | Server display name |
| `storage_path` | str | `"ledgermind"` | Path to memory storage |
| `capabilities` | Dict | `None` | Feature flags for enabling/disabling |
| `metrics_port` | int | `None` | Prometheus metrics port |
| `rest_port` | int | `None` | REST API gateway port |
| `default_role` | MCPRole | `AGENT` | Default access role |
| `start_worker` | bool | `True` | Start background worker |
| `webhooks` | List[str] | `None` | URLs for event notifications |

**MCPRole Values**:

| Role | Permissions |
|-------|--------------|
| `VIEWER` | Read only |
| `AGENT` | Read, propose, supersede, sync |
| `ADMIN` | All operations including purge |

---

### MCP Tools

For detailed documentation of all 15 MCP tools, see [MCP Tools](mcp-tools.md).

---

## Error Handling

### MemoryDecision Responses

All operations return `MemoryDecision` objects. Check `should_persist` and `reason` fields.

### Common Error Scenarios

**Conflict Without Resolution**:

```python
# Returns:
MemoryDecision(
    should_persist=False,
    store_type="none",
    reason="CONFLICT: Active decisions for target 'database' exist: [abc123]. "
          "ResolutionIntent required."
)
```

**Storage Write Failure**:

```python
# Raises exception with message explaining to failure
try:
    memory.record_decision(...)
except PermissionError as e:
    print(f"Failed: {e}")
```

**Vector Search Disabled**:

```python
# Operations still work, but without vector similarity
# Check health for warnings
health = memory.check_environment()
if not health['vector_available']:
    print("Warning: Vector search disabled. Results will be keyword-only.")
```

---

## Examples

### Complete Usage Example

```python
from ledgermind.core.api.bridge import IntegrationBridge

# Initialize bridge
bridge = IntegrationBridge(
    memory_path="../.ledgermind",
    vector_model="../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf"
)

# Get context for a prompt
context = bridge.get_context_for_prompt("How do I handle API errors?")
print(context)

# Record a decision
bridge.record_decision(
    title="Use exponential backoff for retries",
    target="api_client",
    rationale="Prevents overwhelming the server during outages. "
             "Start with 1s delay, double up to 10s max.",
    consequences=[
        "Implement jitter",
        "Circuit breaker pattern"
    ]
)

# Record an interaction
bridge.record_interaction(
    prompt="Test API endpoint",
    response="200 OK",
    success=True
)

# Search for relevant decisions
results = bridge.search_decisions("API error handling", limit=3)
for result in results:
    print(f"{result['title']} (relevance: {result['score']:.2f})")
```

### Multi-Agent Namespacing Example

```python
# Frontend agent decisions
bridge_front = IntegrationBridge(
    memory_path="../.ledgermind",
    namespace="frontend_agent"
)

bridge_front.record_decision(
    title="Use React with TypeScript",
    target="framework",
    rationale="TypeScript provides type safety and better DX.",
    namespace="frontend_agent"
)

# Backend agent decisions (separate namespace)
bridge_back = IntegrationBridge(
    memory_path="../.ledgermind",
    namespace="backend_agent"
)

bridge_back.record_decision(
    title="Use Python with FastAPI",
    target="framework",
    rationale="FastAPI provides async support and automatic docs.",
    namespace="backend_agent"
)

# Each agent sees only their own decisions
front_results = bridge_front.search_decisions("framework", namespace="frontend_agent")
# Returns React/TypeScript

back_results = bridge_back.search_decisions("framework", namespace="backend_agent")
# Returns Python/FastAPI
```

### Reflection Workflow Example

```python
# Record interactions that will be distilled
bridge.record_interaction(
    prompt="Implement user authentication",
    response="JWT-based auth with refresh tokens",
    success=True,
    metadata={"component": "backend"}
)

bridge.record_interaction(
    prompt="Implement user profile",
    response="GraphQL API with user data",
    success=True,
    metadata={"component": "backend"}
)

# Trigger reflection (manually)
proposal_ids = bridge._memory.run_reflection()
print(f"Generated proposals: {len(proposal_ids)}")

# Proposals are now available for review
# They will appear in search results
```

---

## Next Steps

For implementation details:
- [Quick Start](quickstart.md) — Step-by-step setup guide
- [Integration Guide](integration-guide.md) — Client integration patterns
- [Workflows](workflow.md) — Common operational patterns

For architectural details:
- [Architecture](architecture.md) — Deep dive into system internals
- [Data Schemas](data-schemas.md) — Complete model definitions
- [Configuration](configuration.md) — Environment variables and options

For MCP tool details:
- [MCP Tools](mcp-tools.md) — Detailed documentation of all 15 tools
