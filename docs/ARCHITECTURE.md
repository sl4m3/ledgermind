# Architecture

This document describes the internal design of LedgerMind — how its components 
interact, how data flows through the system, and why it was built this way.

---

## Design Principles

**1. Separation of Reasoning from Storage.**
The reasoning layer (`core/reasoning/`) knows nothing about file formats or 
databases. The storage layer (`core/stores/`) knows nothing about conflict 
policies or decay logic. The `Memory` class is the only orchestrator that 
connects them.

**2. Active Core, not a Passive Store.**
Every entry point into the system passes through `process_event()`, which 
enforces invariants, checks duplicates, validates trust boundaries, and routes 
to the appropriate store — before any write happens.

**3. Immutability through Supersede.**
Knowledge is never overwritten. When a decision changes, the old record gets 
`status=superseded` and a forward link (`superseded_by`) to its replacement. 
The full graph of truth evolution is always preserved.

**4. Crash Safety & Thread-Local Isolation.**
All semantic writes happen inside a `FileSystemLock` + `TransactionManager` 
block. LedgerMind uses `threading.local()` to isolate transaction state 
between threads, ensuring that concurrent operations within the same process 
don't interfere with each other's SAVEPOINTS. The lock uses `threading.RLock` 
for thread-safety and `fcntl` for process-safety. If a process crashes, the 
next operation verifies the PID; if the owner is dead, the stale lock is 
automatically cleared.

---

## Component Map

```
Memory (core/api/memory.py)
│
├── Bridge API             Lightweight access for Hooks Pack (Zero-Touch)
│   ├── bridge-context     Sub-millisecond prompt enrichment
│   └── bridge-record      Asynchronous interaction logging
│
├── SemanticStore          Long-term structured knowledge (Markdown + Git)
│   ├── GitAuditProvider   Every write = a Git commit
│   ├── SemanticMetaStore  SQLite index with FTS5 and namespace support (Idempotent initialization)
│   ├── TransactionManager ACID isolation using SAVEPOINT and threading.local()
│   ├── IntegrityChecker   Pre/post-write ns-resolution invariant validation
│   └── MemoryLoader       Frontmatter YAML + Markdown body parser
│
├── EpisodicStore          Append-only interaction journal (SQLite WAL)
│   └── Immortal Links     Events linked to semantic records are never deleted
│
├── VectorStore            Cosine similarity index (NumPy matrix)
│   ├── GGUF Support       4-bit quantization via llama-cpp-python
│   ├── Embedding Cache    Lru-style cache prevents redundant llama.cpp calls
│   ├── Model Caching      Singleton pattern avoids redundant RAM usage
│   └── Auto-Dimension     Dynamic detection (e.g. 1024 for Jina v5 Small)
│
├── ConflictEngine         Detects collisions within specific namespaces
├── Webhook Dispatcher     Async HTTP POST notifications for memory events
├── ResolutionEngine       Validates ResolutionIntent before supersede
├── ReflectionEngine       Incremental Knowledge Discovery (Probabilistic)
├── DecayEngine            Manages TTL, confidence decay, and forgetting
├── MergeEngine            Scans for semantically identical active decisions
├── DistillationEngine     Distills successful trajectories → ProceduralProposals
├── GitIndexer             Imports Git commits into episodic memory
├── TargetRegistry         Canonical names + alias resolution (targets.json)
└── MemoryRouter           Routes MemoryEvent to the correct store
```

---

## Reflection and Knowledge Synthesis

The `ReflectionEngine` moved from binary success/failure tracking to a **Probabilistic Model**:

*   **Float Success Weights:** Interactions are scored from `0.0` (Hard Error) to `1.0` (Verified Success).
*   **Target Inheritance:** `prompt` and `result` events automatically inherit the `target` from the preceding actions in a session, enabling better clustering.
*   **Procedural Distillation:** Successful "trajectories" are automatically converted into пошаговые инструкции (`procedural.steps`) inside proposals.

---

## Data Flow: Writing a Decision

```
record_decision(title, target, rationale)
        │
        ▼
1. TargetRegistry.normalize(target)         — resolve alias → canonical name
2. semantic.list_active_conflicts(target)   — fast SQLite lookup
        │
        ├─ Conflicts found + vector available
        │       │
        │       ▼
        │  cosine_similarity(new_vec, old_vec)
        │       │
        │       ├─ similarity > 0.70 → supersede_decision() [auto-resolve]
        │       ├─ 0.50 < sim ≤ 0.70 → call arbiter_callback
        │       └─ similarity ≤ 0.50 → raise ConflictError
        │
        └─ No conflicts
                │
                ▼
3. semantic.transaction()                   — acquire RLock + start SAVEPOINT
        │
        ▼
4. [Inside lock] deactivation               — soft-deactivate old versions
5. process_event(source="agent")            — route to "semantic"
        │
        ▼
6. Late-bind Conflict Detection             — final check for race conditions
        │
        ▼
7. [Inside transaction] save()              — write .md + SQLite upsert
        │
        ▼
8. vector.add_documents()                   — index title + rationale
        │
        ▼
9. Git commit                               — coordinated atomic commit
        │
        ▼
10. Return MemoryDecision(should_persist=True)
```

---

## Data Flow: Searching

```
search_decisions(query, limit, mode)
        │
        ▼
1. vector.search(query, limit * 3)          — 4-bit GGUF cosine candidates
        │
        ▼
2. meta.keyword_search(query)               — FTS5 SQLite candidates
        │
        ▼
3. Reciprocal Rank Fusion (RRF)             — merge search engine results
        │
        ▼
4. Resolve to Truth                         — follow superseded_by chains
        │
        ▼
5. Evidence boost                           — +20% score per episodic link
        │
        ▼
6. Truncate & Paginate                      — apply final ranking and limit
```

---

## Storage Layout

```
./memory/                          ← storage_path
├── episodic.db                    ← SQLite: interaction journal
├── vector_index/
│   ├── vectors.npy                ← NumPy float32 embeddings matrix
│   └── vector_meta.npy            ← Parallel array of document IDs
└── semantic/                      ← Git repository root
    ├── .git/                      ← Full Git history = audit log
    ├── semantic_meta.db           ← SQLite: metadata index
    ├── .lock                      ← Thread-safe lock file
    └── default/                   ← Default namespace directory
```

---

## Integrity and Invariants

The `IntegrityChecker` enforces several core architectural invariants:

*   **I4: Single Active Decision.** Only one record for a given `(target, 
    namespace)` pair can have `status=active` at any time.
*   **I3: Bidirectional Links.** Every `superseded_by` link must have a 
    matching `supersedes` entry in the target file.
*   **I5: Acyclicity.** The evolution graph must not contain loops.

To support high-speed parallel operations, the checker uses **nanosecond 
resolution** for file modification times to prevent cache collisions.

---

## Autonomous Maintenance & Self-Healing

LedgerMind is designed to survive in unpredictable environments (like Termux 
or intermittent CI runners).

**1. Self-Healing Index**
If the SQLite metadata index (`semantic_meta.db`) is deleted or becomes 
corrupted, the system automatically triggers a `sync_meta_index()` during 
initialization. It crawls the filesystem, parses all `.md` files, and 
reconstructs the relational index and FTS5 search tables from the 
ground truth on disk.

**2. Deep Truth Resolution**
When searching in `balanced` mode, LedgerMind doesn't just return the 
most relevant record. It recursively follows the `superseded_by` chain for 
every candidate to ensure that if a newer "truth" exists, it is the one 
provided as context to the agent.

**3. Multiprocess Safety**
The `FileSystemLock` combines `threading.RLock` with Unix `fcntl` advisory 
locking. This ensures that a background worker and an active agent process 
can safely share the same memory directory without corrupting the Git 
repository or SQLite databases.

---

## Trust Boundaries

| Mode | Effect |
|---|---|
| `AGENT_WITH_INTENT` | Default. Agents can read and write decisions freely. |
| `HUMAN_ONLY` | Agent-sourced writes are blocked. Only `user` can write. |

---

## Background Worker Schedule

The `BackgroundWorker` runs a heartbeat every 300 seconds (default). It 
coordinates:
1.  **Reflection** (4h): Distills raw events into proposals.
2.  **Decay** (1h): Reduces confidence of inactive memories.
3.  **Git Sync** (cycle): Indexes human-made commits.
4.  **Health Check** (cycle): Verifies storage and locks.
