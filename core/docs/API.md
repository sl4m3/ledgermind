# API Reference - agent-memory-core

## `Memory` Class

The primary interface for the memory system.

### Initialization

```python
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.schemas import TrustBoundary

memory = Memory(
    storage_path="./memory", 
    ttl_days=30, 
    trust_boundary=TrustBoundary.AGENT_WITH_INTENT
)
```

- `storage_path`: Directory for episodic (SQLite) and semantic (Git) stores.
- `ttl_days`: Time-to-live for episodic memories before decay.
- `trust_boundary`: Security level (`HUMAN_ONLY` or `AGENT_WITH_INTENT`).

---

### Core Methods

#### `record_decision(title, target, rationale, consequences=None)`
Records a new decision in the semantic store.
- **Returns:** `MemoryDecision` object.
- **Invariant:** Ensures only one `active` decision exists for the given `target`.

#### `supersede_decision(title, target, rationale, old_decision_ids, consequences=None)`
Evolves knowledge by replacing old decisions with a new one.
- **old_decision_ids**: List of file IDs to be superseded.
- **Invariant:** Maintains bidirectional links and DAG structure.

#### `process_event(source, kind, content, context=None, intent=None)`
Low-level entry point for all events.
- **source**: "human" or "agent".
- **kind**: "decision", "observation", "task", etc.

#### `get_decisions()`
Returns a list of all file identifiers in the semantic store.

#### `get_recent_events(limit=10, include_archived=False)`
Retrieves events from the episodic store.

#### `run_decay(dry_run=False)`
Manages episodic memory lifecycle (archiving and pruning).
- **Returns:** `DecayReport`.

---

### Exceptions

- `IntegrityViolation`: Raised when architectural invariants (I1-I6) are broken.
- `ConflictError`: Raised when multiple active realities are detected for a target.
- `PermissionError`: Raised when the Trust Boundary is violated.
