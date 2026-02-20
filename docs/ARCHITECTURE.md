# Architecture

This document describes the internal design of LedgerMind — how its components interact, how data flows through the system, and why it was built this way.

---

## Design Principles

**1. Separation of Reasoning from Storage.**
The reasoning layer (`core/reasoning/`) knows nothing about file formats or databases. The storage layer (`core/stores/`) knows nothing about conflict policies or decay logic. The `Memory` class is the only orchestrator that connects them.

**2. Active Core, not a Passive Store.**
Every entry point into the system passes through `process_event()`, which enforces invariants, checks duplicates, validates trust boundaries, and routes to the appropriate store — before any write happens.

**3. Immutability through Supersede.**
Knowledge is never overwritten. When a decision changes, the old record gets `status=superseded` and a forward link (`superseded_by`) to its replacement. The full graph of truth evolution is always preserved.

**4. Crash Safety.**
All semantic writes happen inside a `FileSystemLock` + `TransactionManager` block. On failure, Git `reset --hard HEAD` rolls the filesystem back. The SQLite meta-index is reconstructed from disk at startup via `sync_meta_index()`.

---

## Component Map

```
Memory (core/api/memory.py)
│
├── SemanticStore          Long-term structured knowledge (Markdown + Git)
│   ├── GitAuditProvider   Every write = a Git commit
│   ├── SemanticMetaStore  SQLite index for fast queries (no file reads)
│   ├── TransactionManager FileSystemLock + Git rollback on failure
│   ├── IntegrityChecker   Pre/post-write invariant validation
│   └── MemoryLoader       Frontmatter YAML + Markdown body parser
│
├── EpisodicStore          Append-only interaction journal (SQLite WAL)
│   └── Immortal Links     Events linked to semantic records are never deleted
│
├── VectorStore            Cosine similarity index (NumPy arrays on disk)
│   └── SentenceTransformer  Optional: all-MiniLM-L6-v2 embeddings
│
├── ConflictEngine         Detects active decisions with the same target
├── ResolutionEngine       Validates ResolutionIntent before supersede
├── ReflectionEngine       Analyzes episodic clusters → generates Proposals
├── DecayEngine            Manages TTL, confidence decay, and forgetting
├── MergeEngine            Scans for semantically identical active decisions
├── DistillationEngine     Distills successful trajectories → ProceduralProposals
├── GitIndexer             Imports Git commits into episodic memory
├── TargetRegistry         Canonical names + alias resolution (targets.json)
└── MemoryRouter           Routes MemoryEvent to the correct store
```

---

## Data Flow: Writing a Decision

```
record_decision(title, target, rationale)
        │
        ▼
1. TargetRegistry.normalize(target)         — resolve alias → canonical name
2. TargetRegistry.register(target)          — persist canonical name
3. semantic.list_active_conflicts(target)   — fast SQLite lookup
        │
        ├─ Conflicts found + vector available
        │       │
        │       ▼
        │  cosine_similarity(new_vec, old_vec)
        │       │
        │       ├─ similarity > 0.85 → supersede_decision() [auto-resolve]
        │       └─ similarity ≤ 0.85 → raise ConflictError
        │
        └─ No conflicts
                │
                ▼
4. process_event(source="agent", kind="decision", ...)
        │
        ▼
5. episodic.find_duplicate()                — idempotency guard
        │
        ▼
6. router.route(event)                      — route to "semantic"
        │
        ▼
7. conflict_engine.check_for_conflicts()    — pre-transaction check
        │
        ▼
8. semantic.transaction()                   — acquire FileSystemLock
        │
        ▼
9. [Inside lock] conflict check again       — race condition guard
        │
        ▼
10. semantic.save(event)                    — write .md + Git commit
        │
        ▼
11. vector.add_documents([{id, content}])   — index title + rationale
        │
        ▼
12. episodic.append(event, linked_id=fid)   — create immortal link
        │
        ▼
13. Return MemoryDecision(should_persist=True, metadata={file_id: ...})
```

---

## Data Flow: Searching

```
search_decisions(query, limit, mode)
        │
        ▼
1. vector.search(query, limit * 3)          — cosine similarity candidates
        │
        ▼
2. For each candidate:
   _resolve_to_truth(fid, mode)             — follow superseded_by chain (depth ≤ 5)
        │
        ▼
3. Filter by mode:
   strict   → only status="active"
   balanced → active + deprecated
   audit    → no filter (full history)
        │
        ▼
4. Evidence boost:
   episodic.count_links_for_semantic(fid)
   final_score = vector_score * (1.0 + min(1.0, link_count * 0.2))
        │
        ▼
5. Fallback: if len(candidates) < limit
   meta.keyword_search(query)               — full-text SQLite search
        │
        ▼
6. meta.increment_hit(fid)                  — track access frequency
        │
        ▼
7. Return deduplicated, ranked list
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
    ├── semantic_meta.db           ← SQLite: fast metadata index
    ├── targets.json               ← TargetRegistry: canonical names + aliases
    ├── .lock                      ← FileSystemLock (created/removed atomically)
    └── decisions/
        ├── 2024-01-15_database_abc123.md
        └── 2024-02-01_database_def456.md
```

### Markdown Record Format

Every semantic record is a Markdown file with YAML frontmatter:

```markdown
---
schema_version: 1
kind: decision
content: "Use Aurora PostgreSQL"
timestamp: "2024-02-01T14:22:00"
context:
  title: "Use Aurora PostgreSQL"
  target: "database"
  status: "active"
  rationale: "Aurora provides auto-scaling and built-in replication."
  consequences:
    - "Update connection strings in all services"
  supersedes:
    - "decisions/2024-01-15_database_abc123.md"
  superseded_by: null
---

Use Aurora PostgreSQL

Additional notes or agent-generated content goes here.
```

---

## The Reasoning Layer

### ConflictEngine
Detects whether an incoming `decision` event has a collision with an existing active decision on the same `target`. Uses the SQLite meta-index (`get_active_fid(target, namespace)`) for O(1) lookup — no file reads involved.

### ReflectionEngine v4.2
Operates in four phases per cycle:

1. **Distillation (MemP)** — `DistillationEngine` scans episodic trajectories for successful action chains and generates `ProceduralProposals`.
2. **Evidence Aggregation** — events are clustered by `target` extracted from their context or commit message (e.g. `fix(redis):` → target = `redis`).
3. **Hypothesis Update** — existing draft proposals are updated via Bayesian-style confidence scoring. Contradictory evidence (successes in an error cluster) triggers falsification.
4. **Knowledge Discovery** — new competing hypotheses are generated for error clusters not yet covered by proposals.

**Competing Hypotheses:** For every new error cluster, the engine generates at least two proposals — a "Structural Flaw" hypothesis (confidence 0.5) and an "Environmental Noise" hypothesis (confidence 0.4). They are cross-linked via `alternative_ids`.

**Auto-Acceptance:** After each cycle, proposals where `confidence ≥ 0.9` AND `ready_for_review = true` AND `objections = []` are automatically converted to active decisions via `accept_proposal()`.

### DecayEngine

| Memory Type | Rate | Trigger |
|---|---|---|
| Episodic events | TTL (default 30 days) | Age-based |
| Proposals | −5% confidence / week | 7-day inactivity |
| Decisions & Constraints | −1.67% confidence / week | 7-day inactivity |
| Forget (all types) | Hard delete | confidence < 0.1 |
| Deprecate (decisions) | status → deprecated | confidence < 0.5 |

**Immortal Links (I1):** Episodic events with `linked_id IS NOT NULL` are never archived or pruned, regardless of age. They are the evidentiary foundation of semantic decisions.

---

## Trust Boundaries

| Mode | Effect |
|---|---|
| `AGENT_WITH_INTENT` (default) | Agents can read and write freely. Conflict resolution applies. |
| `HUMAN_ONLY` | Agent-sourced `decision` events are silently rejected at the router level. Only human sources can write to semantic memory. |

In MCP mode, an additional isolation layer protects human-created records: records without the `[via MCP]` marker in their rationale cannot be superseded by an agent (unless the server role is `ADMIN`).

---

## Background Worker Schedule

The `BackgroundWorker` runs as a daemon thread started by `MCPServer.__init__()`. It is not started in library mode — call `run_maintenance()` manually or schedule it yourself.

```
On every cycle (default: 300 seconds):
  1. _run_health_check()         Always
  2. _run_git_sync()             Always (if Git available), indexes last 5 commits
  3. _run_reflection()           Every 4 hours (14400 seconds)
  4. _run_decay()                Every 1 hour (3600 seconds)

On startup (first cycle only):
  - is_startup = True forces reflection to run immediately
  - Persists last_reflection_time in SQLite config table
```

On crash, the worker backs off for 60 seconds before retrying. SQLite "no such table" errors during startup are handled gracefully with a 5-second retry.
