# Architecture

Comprehensive guide to LedgerMind's internal architecture, component interactions, and design principles.

---

## Introduction

This document provides a deep dive into LedgerMind's architecture for:
- **Developers** who want to extend or customize LedgerMind
- **System architects** evaluating LedgerMind for their systems
- **Contributors** working on the codebase

### Design Principles

LedgerMind is built around these core principles:

1. **Autonomy First** — The system should operate without manual intervention
2. **Dual Storage** — Short-term ephemeral storage + long-term persistent storage
3. **Git-Audit** — All significant changes must be cryptographically audited
4. **Reasoning Layer** — Knowledge should evolve through autonomous analysis
5. **Multi-Agent** — Support for multiple isolated knowledge bases
6. **Mobile-Optimized** — Efficient operation on resource-constrained environments

---

## System Overview

LedgerMind consists of several interconnected layers:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Application Layer                        │
│                    (MCP Server / CLI / Bridge)                 │
└────────────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
┌────────────────────┐ ┌──────────────┐ ┌─────────────────┐
│   Memory Core    │ │   Storage     │ │   Reasoning    │
│  (Coordinator)   │ │    Layer      │ │    Engines     │
└─────────┬────────┘ └───┬───────────┘ └───────┬────────┘
          │              │                    │
          │              │                    │
          ▼              ▼                    ▼
┌─────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
│  Episodic Store  │ │  Semantic Store    │ │  Vector Store     │
│   (Events)       │ │  (Decisions)      │ │  (Embeddings)      │
│                  │ │                   │ │                    │
└────────────────────┘ └────────────────────┘ └────────────────────┘
          │                    │
          │                    │
          ▼                    ▼
┌────────────────────────────────────────────────────┐
│         Git Audit Trail (Version Control)       │
└────────────────────────────────────────────────┘
```

---

## Core Components

### 3.1 Memory Core

**Location**: `src/ledgermind/core/api/memory.py`

The `Memory` class is the main entry point for all LedgerMind operations. It coordinates storage, reasoning, and lifecycle management.

#### Class Definition

```python
class Memory:
    def __init__(
        self,
        storage_path: Optional[str] = None,
        ttl_days: Optional[int] = None,
        trust_boundary: Optional[TrustBoundary] = None,
        config: Optional[LedgermindConfig] = None,
        episodic_store: Optional[Union[EpisodicStore, EpisodicProvider]] = None,
        semantic_store: Optional[SemanticStore] = None,
        namespace: Optional[str] = None,
        meta_store_provider: Optional[MetadataStore] = None,
        audit_store_provider: Optional[AuditProvider] = None,
        vector_model: Optional[str] = None,
        vector_workers: Optional[int] = None
    ):
```

#### Initialization Sequence

When `Memory()` is instantiated:

1. **Load or create configuration** from `LedgermindConfig` or parameters
2. **Initialize semantic store** with Git audit and SQLite metadata
3. **Initialize episodic store** (SQLite WAL mode)
4. **Initialize vector store** (lazy loading on first use)
5. **Create reasoning engines**:
   - `ConflictEngine` for conflict detection
   - `ResolutionEngine` for validation
   - `DecayEngine` for lifecycle
   - `ReflectionEngine` for pattern discovery
   - `LifecycleEngine` for phase management
6. **Initialize supporting systems**:
   - `MemoryRouter` for event routing
   - `TargetRegistry` for name normalization
   - `GitIndexer` for commit tracking
7. **Run migrations** via `MigrationEngine` to ensure data format compatibility

#### Key Methods

```python
def process_event(
    self,
    source: Literal["user", "agent", "system", "reflection_engine", "bridge"],
    kind: Literal["decision", "error", "config_change", "assumption", ...],
    content: str,
    context: Union[DecisionContent, ProposalContent, DecisionStream, Dict],
    intent: Optional[ResolutionIntent] = None
) -> MemoryDecision:
    """Main entry point for all events. Routes to appropriate storage."""

def record_decision(
    self,
    title: str,
    target: str,
    rationale: str,
    consequences: Optional[List[str]] = None,
    evidence_ids: Optional[List[int]] = None,
    arbiter_callback: Optional[Callable] = None
) -> MemoryDecision:
    """Records a long-term decision with conflict checking."""

def search_decisions(
    self,
    query: str,
    limit: int = 5,
    mode: Literal["strict", "balanced", "audit"] = "balanced",
    namespace: str = "default"
) -> List[Dict[str, Any]]:
    """Hybrid search combining keyword and vector similarity."""

def run_reflection(self) -> List[str]:
    """Triggers the reflection cycle to generate proposals."""

def run_decay(self) -> DecayReport:
    """Triggers the decay cycle to prune old data."""

def sync_git(self, repo_path: str = ".", limit: int = 20) -> int:
    """Indexes recent Git commits into episodic memory."""
```

---

### 3.2 Storage Layer

LedgerMind uses a dual-storage architecture optimized for different use cases.

#### 3.2.1 EpisodicStore

**Location**: `src/ledgermind/core/stores/episodic.py`

**Purpose**: Short-term storage for ephemeral events (prompts, responses, errors, tool calls, Git changes).

**Database Schema**:

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,                    -- "user", "agent", "system", "reflection_engine", "bridge"
    kind TEXT,                      -- "decision", "error", "prompt", "task", "call", "commit_change", etc.
    content TEXT,                    -- Event payload
    context TEXT,                    -- JSON-serialized context object
    timestamp TEXT,                   -- ISO 8601 datetime
    status TEXT DEFAULT 'active',        -- "active" or "archived"
    linked_id TEXT,                    -- Links to semantic decision ID (immortal if set)
    link_strength REAL DEFAULT 1.0      -- Evidence weight (0.0-1.0)
    UNIQUE(source, kind, content)       -- Duplicate prevention
)
```

**Key Features**:

- **WAL Mode**: Write-Ahead Logging for concurrent reads
- **Duplicate Detection**: Unique constraint on `(source, kind, content)`
- **Evidence Linking**: `linked_id` field connects events to decisions
- **Batch Operations**: `count_links_for_semantic_batch()` for multiple IDs
- **Archive/Prune**: `mark_archived()` and physical deletion via `physical_prune()`

#### 3.2.2 SemanticStore

**Location**: `src/ledgermind/core/stores/semantic.py`

**Purpose**: Long-term storage for decisions, proposals, and constraints with full audit trail.

**Architecture**: Hybrid of three layers:

```
┌─────────────────────────────────────────────────────────┐
│                 Semantic Store                        │
└───────────┬────────────────────────────────────┬──┘
             │                    │                    │
             ▼                    ▼                    ▼
┌──────────────────┐ ┌────────────────┐ ┌────────────────┐
│  Filesystem     │ │   Metadata      │ │  Git Audit      │
│ (Markdown files)│ │    Index       │ │     Provider    │
│                 │ │  (SQLite)      │ │                │
└──────────────────┘ └────────────────┘ └────────────────┘
```

**Filesystem Layer**:

- Each decision stored as Markdown file with YAML frontmatter
- Format: `---\nYAML_METADATA\n---\nMARKDOWN_BODY\n`
- Located in: `.ledgermind/semantic/`
- Example filename: `decision_id.md`

**Metadata Index**:

- SQLite database: `semantic_meta.db`
- Tables: `decisions`, `config`, `targets`
- Provides fast queries for: active decisions by target, namespace filtering, link counts
- Key fields: `fid`, `target`, `title`, `status`, `kind`, `timestamp`, `phase`, `vitality`, `confidence`, etc.

**Git Audit**:

- `GitAuditProvider` (if Git available) or `NoAuditProvider` (fallback)
- Every write operation creates a Git commit
- Commit message includes operation type
- Provides cryptographic proof of changes and history

#### 3.2.3 VectorStore

**Location**: `src/ledgermind/core/stores/vector.py`

**Purpose**: Semantic similarity search using vector embeddings.

**Backend Modes**:

```python
# GGUF Mode (Mobile-Optimized)
class GGUFEmbeddingAdapter:
    def __init__(self, model_path: str):
        from llama_cpp import Llama
        self.client = Llama(
            model_path=model_path,
            embedding=True,
            verbose=False,
            n_ctx=8192,
            n_gpu_layers=0,           # CPU-only for mobile
            n_threads=4,
            n_batch=512,
            pooling_type=1
        )
        self.dimension = 1024           # Auto-detected
        self._cache = {}               # 100-entry LRU cache

# Transformer Mode (Server)
# Uses sentence-transformers library
# Higher accuracy, larger memory footprint
```

**Optimizations**:

1. **Embedding Cache**: 100-entry cache with LRU eviction
2. **Lazy Loading**: Model loaded only on first `add_document()` or `search()`
3. **Task Prefix**: Jina 3.1.2 uses `"text-matching: "` prefix for better retrieval
4. **NumPy Operations**: Efficient cosine similarity without external dependencies

#### 3.2.4 Store Interfaces

**Location**: `src/ledgermind/core/stores/interfaces.py`

Abstract base classes for dependency injection and testing:

```python
class EpisodicProvider(ABC):
    @abstractmethod
    def append(self, event: MemoryEvent, linked_id: Optional[str] = None) -> int:
        """Append event to episodic store."""

    @abstractmethod
    def link_to_semantic(self, event_id: int, semantic_id: str):
        """Link an event to a semantic decision."""

    @abstractmethod
    def query(self, limit: int = 100, status: Optional[str] = 'active') -> List[Dict]:
        """Query events with optional filtering."""

class MetadataStore(ABC):
    @abstractmethod
    def upsert(self, fid: str, target: str, status: str, kind: str, ...):
        """Insert or update metadata record."""

    @abstractmethod
    def get_active_fid(self, target: str) -> Optional[str]:
        """Get active decision ID for a target."""

    @abstractmethod
    def increment_hit(self, fid: str):
        """Increment hit counter for relevance tracking."""

class AuditProvider(ABC):
    @abstractmethod
    def add_artifact(self, relative_path: str, content: str, commit_msg: str):
        """Add a new file to audit trail."""

    @abstractmethod
    def commit_transaction(self, message: str):
        """Commit all staged changes."""
```

---

### 3.3 Reasoning Engines

#### 3.3.1 ConflictEngine

**Location**: `src/ledgermind/core/reasoning/conflict.py`

**Purpose**: Detects when a new decision conflicts with existing active decisions for the same target.

**Algorithm**:

```python
class ConflictEngine:
    def get_conflict_files(self, event: MemoryEvent, namespace: Optional[str]) -> List[str]:
        """
        Identify files that conflict with given event.

        Conflict occurs if an existing active decision has the same target.
        """
        if event.kind != "decision":
            return []

        new_target = self._get_target(event)
        if not new_target:
            return []

        # Optimization: Use metadata index if available
        if self.meta:
            ns = namespace or self._get_namespace(event)
            fid = self.meta.get_active_fid(new_target, namespace=ns)
            return [fid] if fid else []

        return self._scan_for_conflicts(new_target, ns)
```

**Use Case**: Prevents inconsistent state where two decisions exist for the same target. Requires `ResolutionIntent` to supersede.

#### 3.3.2 ResolutionEngine

**Location**: `src/ledgermind/core/reasoning/resolution.py`

**Purpose**: Validates that a `ResolutionIntent` properly addresses all conflicts.

**Algorithm**:

```python
class ResolutionEngine:
    def validate_intent(self, intent: ResolutionIntent, conflict_files: List[str]) -> bool:
        """
        Ensures that intent covers all detected conflict files.

        Logic: actual ⊆ addressed
        All conflict files MUST be present in target_decision_ids.
        """
        addressed = set(intent.target_decision_ids)
        actual = set(conflict_files)
        return actual.issubset(addressed)
```

**ResolutionIntent Types**:

```python
class ResolutionIntent(BaseModel):
    resolution_type: Literal["supersede", "deprecate", "abort"]
    rationale: str
    target_decision_ids: List[str]
```

#### 3.3.3 DecayEngine

**Location**: `src/ledgermind/core/reasoning/decay.py`

**Purpose**: Manages lifecycle of episodic and semantic memories based on age and usage.

**Strategy**:

```python
class DecayEngine:
    def evaluate(self, events: List[Dict]) -> Tuple[List[int], List[int], int]:
        """
        Determines fate of episodic events.

        Rules:
        1. If linked_id is NOT NULL → Keep forever (Immortal Link)
        2. If kind is decision/constraint → Keep forever (Immortal Kind)
        3. If older than TTL and 'active' → Move to archive
        4. If older than TTL and 'archived' → Physical prune
        """

    def evaluate_semantic(self, decisions: List[Dict]) -> List[Tuple[str, float, bool]]:
        """
        Calculates confidence decay for semantic decisions.

        Differentiated decay rates:
        - Proposals decay at full rate (0.05 per week)
        - Decisions/Constraints decay at 1/3 rate
        - Drafts decay at 2x rate
        """
```

**DecayReport**:

```python
class DecayReport:
    def __init__(self, archived: int, pruned: int, retained: int, semantic_forgotten: int = 0):
        self.archived = archived
        self.pruned = pruned
        self.retained_by_link = retained
        self.semantic_forgotten = semantic_forgotten
```

#### 3.3.4 ReflectionEngine

**Location**: `src/ledgermind/core/reasoning/reflection.py`

**Purpose**: Discovers patterns from episodic events and generates proposals.

**Process Flow**:

```python
class ReflectionEngine:
    def run_cycle(self, after_id: Optional[int]) -> Tuple[List[str], Optional[int]]:
        """
        Executes one reflection cycle.

        Steps:
        1. Distillation: Extract procedural patterns
        2. Evidence Clustering: Group events by target
        3. Stream Updates: Update existing DecisionStream objects
        4. Vitality Decay: Apply decay to unused streams
        5. Summary Logging: Record reflection summary
        """
```

**Blacklisted Targets**: `"general"`, `"general_development"`, `"reflection_engine"` — patterns for these targets are ignored.

#### 3.3.5 LifecycleEngine

**Location**: `src/ledgermind/core/reasoning/lifecycle.py`

**Purpose**: Manages phase transitions and vitality for knowledge streams.

**Phases**:

```python
class DecisionPhase(str, Enum):
    PATTERN = "pattern"       # Initial observation
    EMERGENT = "emergent"   # Reinforced pattern
    CANONICAL = "canonical"   # Stable, proven

class DecisionVitality(str, Enum):
    ACTIVE = "active"      # Used within 7 days
    DECAYING = "decaying"  # 7-30 days
    DORMANT = "dormant"    # >30 days
```

**Transition Logic**:

```python
class LifecycleEngine:
    def promote_stream(self, stream: DecisionStream) -> DecisionStream:
        """
        Evaluates and transitions Phase based on temporal signals.

        PATTERN → EMERGENT:
            if frequency >= 3 OR confidence >= 0.5
            AND (lifetime_days > 0.5 OR frequency >= 5)

        EMERGENT → CANONICAL:
            if coverage > 0.3
            AND stability_score > 0.6
            AND removal_cost > 0.5
            AND vitality == ACTIVE
        """

    def update_vitality(self, stream: DecisionStream, now: datetime) -> DecisionStream:
        """
        Updates vitality state based on last_seen timestamp.

        Days since last use:
        < 7   → ACTIVE
        7-30  → DECAYING (confidence - 0.05)
        > 30   → DORMANT (confidence - 0.2)
        """
```

**Temporal Signals**:

- **Reinforcement Density**: Frequency per lifetime day
- **Stability Score**: 1.0 - variance of observation intervals
- **Coverage**: Lifetime days / observation window
- **Removal Cost**: Based on scope, consequences, provenance
- **Utility**: Based on frequency, unique contexts, scope

#### 3.3.6 DistillationEngine

**Location**: `src/ledgermind/core/reasoning/distillation.py`

**Purpose**: Implements MemP principle — converts successful trajectories into procedural knowledge.

**Algorithm**:

```python
class DistillationEngine:
    def distill_trajectories(self, limit: int, after_id: Optional[int]) -> List[ProposalContent]:
        """
        Groups events by actor-based sessions and distills into procedural proposals.

        Process:
        1. Fetch events (chronological)
        2. Group into Turns (User Prompt → Agent Chain)
        3. Stitch Turns into Task Trajectories by shared target
        4. Detect success signals
        5. Create procedural proposals with steps
        """
```

**Procedural Content**:

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

---

### 3.4 Supporting Systems

#### 3.4.1 MemoryRouter

**Location**: `src/ledgermind/core/core/router.py`

**Purpose**: Routes events to appropriate storage and enforces conflict policies.

```python
class MemoryRouter:
    def route(self, event: MemoryEvent, intent: Optional[ResolutionIntent]) -> MemoryDecision:
        """
        Routes event and enforces conflict resolution invariant.

        If semantic kind AND no conflict → semantic store
        If semantic kind AND conflict AND no intent → reject
        If semantic kind AND conflict AND valid intent → semantic store
        Otherwise → episodic store
        """
```

#### 3.4.2 TargetRegistry

**Location**: `src/ledgermind/core/core/targets.py`

**Purpose**: Normalizes target names to prevent namespace fragmentation.

```python
class TargetRegistry:
    def normalize(self, name: str) -> str:
        """
        Returns canonical name for a given target.

        Priority:
        1. Exact match in targets
        2. Match in aliases
        3. Case-insensitive match
        4. Return original if no match
        """

    def suggest(self, query: str, limit: int = 3) -> List[str]:
        """
        Suggests existing targets similar to query.
        Uses difflib.get_close_matches() with 0.6 cutoff.
        """
```

#### 3.4.3 GitIndexer

**Location**: `src/ledgermind/git_indexer.py`

**Purpose**: Automatically indexes Git commits as episodic events.

```python
class GitIndexer:
    def get_recent_commits(self, limit: int = 10, since_hash: Optional[str]) -> List[Dict]:
        """
        Extracts commit history via git log.

        Format: hash|author|date|subject|body\x00
        Returns: [{hash, author, date, subject, body}]
        """

    def index_to_memory(self, memory_instance, limit: int = 20) -> int:
        """
        Scans Git and records new commits as events.

        Process:
        1. Get last indexed commit hash from config
        2. Fetch new commits
        3. Infer target from changed files or commit message
        4. Record as MemoryEvent(kind="commit_change")
        5. Update last_hash in config
        """
```

**Security**: Path traversal protection — ensures repo path is within current working directory.

#### 3.4.4 MigrationEngine

**Location**: `src/ledgermind/core/migration.py`

**Purpose**: Ensures data format compatibility across versions.

```python
class MigrationEngine:
    def run_all(self):
        """
        Executes all necessary migrations.

        Current version: 1.22.0

        Migrations:
        - Ensure 'target' length >= 3
        - Ensure 'kind' exists
        - Ensure 'namespace' exists
        - Fix 'rationale' if too short
        - Rebuild metadata index after migrations
        """
```

#### 3.4.5 EventEmitter

**Location**: `src/ledgermind/core/utils/events.py`

**Purpose**: Decoupled event publication/subscription for extensions.

```python
class EventEmitter:
    def subscribe(self, callback: Callable):
        """Register callback for all events."""

    def emit(self, event_type: str, data: Any):
        """Publish event to all subscribers."""
```

**Used by**: `MCPServer._trigger_webhooks()` for notifying external systems.

---

## Data Flow

### Event Processing Flow

```
User/Agent Input
    │
    ├─→ Memory.process_event()
    │       │
    │       ├─→ MemoryRouter.route()
    │       │
    │       ├─→ ConflictEngine.get_conflict_files()
    │       │
    │       ├─→ Conflict? ──► ResolutionEngine.validate_intent()
    │       │       │           │
    │       │       ├─→ Semantic Store (Git + SQLite)
    │       │       │
    │       └─► Episodic Store (SQLite)
    │       │
    │       ├─→ VectorStore.encode()
    │       │       └─→ Vector Index
```

### Decision Recording Flow

```
record_decision(title, target, rationale)
    │
    ├─→ Conflict Check (ConflictEngine)
    │       │
    │       ├─→ No Conflict ──► Write to SemanticStore
    │       │       │
    │       │       ├─→ Create Markdown file
    │       │       │       ├─→ Update metadata index
    │       │       │       ├─→ Git commit (AuditProvider)
    │       │       │       └─→ Vector encode
    │       │
    │       └─→ Conflict Exists ──► Check for ResolutionIntent
    │               │
    │               ├─→ No Intent ──► Reject
    │               │
    │               └─→ Valid Intent ──► Supersede old decisions
    │                           │
    │                           ├─→ Update old decisions (superseded_by)
    │                           ├─→ Write new decision
    │                           └─→ Git commit
```

### Search Operation Flow

```
search_decisions(query, limit, mode)
    │
    ├─→ Keyword Search (SQLite)
    │       │
    │       ├─→ Query semantic_meta.db
    │       ├─→ Filter by status (strict/balanced)
    │       ├─→ Filter by namespace
    │       └─→ Get link counts (batch operation)
    │       │
    ├─→ Vector Search (if available)
    │       │
    │       ├─→ Encode query
    │       ├─→ Vector similarity search
    │       └─→ Get scores
    │       │
    └─→ RRF Fusion
            ├─→ Combine keyword + vector results
            ├─→ Apply evidence boost (+20% per link)
            └─→ Sort and return top N
```

### Background Worker Flow

```
BackgroundWorker._loop() [runs every 300 seconds]
    │
    ├─→ Health Check
    │       │
    │       ├─→ Memory.check_environment()
    │       ├─→ Stale lock? ──► Break after 10 min age
    │       └─→ Record to logs
    │
    ├─→ Git Sync
    │       │
    │       ├─→ GitIndexer.index_to_memory()
    │       └─→ Index N new commits
    │
    ├─→ Reflection Cycle
    │       │
    │       ├─→ Distillation: Extract patterns
    │       ├─→ Evidence Clustering: Group by target
    │       ├─→ Stream Updates: Apply reinforcement
    │       ├─→ Vitality Decay: Apply decay
    │       └─→ Generate proposals
    │
    └─→ Decay Cycle
            │
            ├─→ DecayEngine.evaluate() on events
            ├─→ Mark old events as archived
            └─→ Prune archived events (> TTL)
```

---

## Storage Architecture

### Episodic Memory Structure

**File**: `.ledgermind/episodic.db` (SQLite)

**Table: events**

| Column | Type | Purpose |
|---------|------|---------|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | Unique event identifier |
| `source` | TEXT | Origin: user, agent, system, reflection_engine, bridge |
| `kind` | TEXT | Event type: decision, error, prompt, task, call, commit_change, etc. |
| `content` | TEXT | Event payload (free-form text) |
| `context` | TEXT | JSON-serialized context object (DecisionContent, etc.) |
| `timestamp` | TEXT | ISO 8601 datetime |
| `status` | TEXT | "active" or "archived" |
| `linked_id` | TEXT | Links to semantic decision ID |
| `link_strength` | REAL | Evidence weight (0.0-1.0) |

**Indexes**:
- `idx_events_duplicate`: `(source, kind, content)` — Prevents duplicates
- Composite index on `(status, timestamp)` — Efficient filtering

### Semantic Memory Structure

**Directory**: `.ledgermind/semantic/`

**File Format**:

```markdown
---
target: database
title: Use PostgreSQL
status: active
phase: canonical
vitality: active
kind: decision
namespace: default
confidence: 0.85
reinforcement_density: 2.3
stability_score: 0.72
coverage: 0.45
lifetime_days: 45.2
provenance: internal
first_seen: "2025-12-15T10:30:00"
last_seen: "2026-02-28T14:22:00"
evidence_event_ids: [123, 156, 178]
superseded_by: null
---

Use PostgreSQL for all production databases. This decision has been reinforced through multiple successful deployments and is now in canonical phase.

## Related Decisions

This supersedes: Use MySQL (deprecated_abc123.md)

## Context

Additional context and procedural information can be stored here.
```

**Metadata Index** (`semantic_meta.db`):

**Table: decisions**

| Column | Type | Purpose |
|---------|------|---------|
| `fid` | TEXT PRIMARY KEY | Decision filename |
| `target` | TEXT | Decision target |
| `title` | TEXT | Decision title |
| `status` | TEXT | active, deprecated, superseded |
| `kind` | TEXT | decision, proposal, constraint, etc. |
| `timestamp` | DATETIME | Last updated time |
| `superseded_by` | TEXT | ID of decision that superseded this |
| `namespace` | TEXT | Logical partition |
| `confidence` | REAL | Confidence score (0.0-1.0) |
| `phase` | TEXT | pattern, emergent, canonical |
| `vitality` | TEXT | active, decaying, dormant |
| `link_count` | INTEGER | Number of linked events |
| `context_json` | TEXT | Serialized context for queries |

**Indexes**:
- `idx_decisions_target_namespace`: `(target, namespace)` — Fast conflict detection
- `idx_decisions_status`: `(status)` — Filtering by state

### Vector Index Structure

**Directory**: `.ledgermind/vector_index/`

**Implementation**: In-memory NumPy arrays backed by disk persistence (Annoy-style but simplified)

**Storage**:
- `embeddings.npy`: Float32 matrix (N × dimension)
- `doc_ids.npy`: String array mapping rows to document IDs
- `metadata.json`: Document metadata mapping

**Operations**:
- `add_document(doc_id, text)`: Encode and store
- `search(query, limit)`: Cosine similarity, return top K

---

## Reasoning Architecture

### Conflict Detection Mechanism

```
New Event (kind=decision, target=T)
    │
    ├─→ Query metadata for active fid with target=T, namespace=NS
    │
    ├─→ Found?
    │   │
    │   ├─→ YES ──► Conflict detected
    │   │       │
    │   │       ├─→ Has ResolutionIntent?
    │   │       │       │
    │   │       │       ├─→ YES, includes all conflicts ──► ALLOW
    │   │       │       │       └─→ NO or incomplete ──► REJECT
    │   │       │
    │   └─→ NO ──► Allow
```

### Lifecycle State Machine

```
                    ┌─────────────┐
                    │  PATTERN   │
                    └───────┬─────┘
                            │
            Frequency ≥ 3 OR Conf ≥ 0.5
            AND Lifetime > 0.5 OR Freq ≥ 5
                            │
                            ▼
                    ┌─────────────┐
                    │ EMERGENT   │
                    └───────┬─────┘
                            │
            Coverage > 0.3
            AND Stability > 0.6
            AND Cost > 0.5
            AND Vitality = ACTIVE
                            │
                            ▼
                    ┌─────────────┐
                    │  CANONICAL  │
                    └─────────────┘
```

### Reflection Cycle Process

```
1. Distillation
   ├─→ Fetch N recent events (limit=200, after_id=X)
   ├─→ Group into Turns (User → Agent chain)
   ├─→ Stitch into Trajectories by target
   ├─→ Detect success (keywords: "успешно", "passed", "completed", etc.)
   └─→ Create ProceduralContent with steps

2. Evidence Clustering
   ├─→ Query recent events (limit=3000)
   ├─→ Load all active DecisionStream objects
   ├─→ Group by target
   └─→ For each cluster:
       ├─→ Count events, commits, successes
       ├─→ Update reinforcement timestamps
       ├─→ Calculate new metrics (density, stability, coverage)
       ├─→ Attach procedural steps if confidence ≥ 0.7
       └─→ Write updated DecisionStream

3. Vitality Decay (for unprocessed streams)
   ├─→ Calculate days since last_seen
   ├─→ Update vitality state
   ├─→ Decay confidence if not active
   └─→ Write updated DecisionStream

4. Summary
   └─→ Log reflection_summary event to episodic
```

### Distillation Algorithm

```
Turn Detection:
┌────────────────────────────────────────────┐
│ User Prompt                           │
└───────────────┬───────────────────────┘
                │
                ▼
┌────────────────────────────────────────────┐
│ Agent Chain                            │
│ - task (action)                       │
│ - call (function)                      │
│ - result (outcome)                      │
└───────────────┬───────────────────────┘
                │
                ▼
         SUCCESS SIGNAL?

Trajectory Stitching:
By target T:
  Turn 1 (T) + Turn 2 (T) + ... + Success
  = Single Trajectory

Procedural Extraction:
For each event in trajectory:
  - Extract action (from task/call)
  - Extract rationale (from context)
  - Extract outcome (from result)
  = ProceduralStep

ProceduralProposal:
  Title: "How to [T]"
  Target: T
  Steps: [ProceduralStep...]
  Evidence IDs: [all event IDs]
```

---

## Concurrency & Thread Safety

### File System Locking

**Implementation**: `FileSystemLock` in `stores/semantic_store/transactions.py`

```python
class FileSystemLock:
    def __init__(self, lock_file: str):
        self.lock_file = lock_file
        self._local = threading.local()

    def acquire(self, exclusive: bool = False):
        """
        Acquire lock with retry logic.
        exclusive=True: Write lock
        exclusive=False: Read lock (multiple readers)
        """
        # Uses lockref protocol for NFS compatibility
        # Timeout: 30 seconds
        # Backoff: 0.1s, 0.2s, 0.4s...
```

**Lock Files**:
- `.ledgermind/semantic/.lock` — Semantic store
- `.ledgermind/episodic.lock` — Episodic database (via SQLite internal)

### Database Transaction Management

**SQLite WAL Mode**:

```python
# In EpisodicStore.__init__():
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA busy_timeout=10000")
```

**Transaction Context Manager**:

```python
@contextmanager
def _get_conn(self):
    with self._lock:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        yield conn
        conn.close()
```

**Semantic Transactions**:

```python
@contextmanager
def transaction(self):
    """
    Ensures atomic Git + SQLite operations.

    If SQLite fails, Git commit is aborted.
    """
    self._fs_lock.acquire(exclusive=True)
    try:
        yield
        # All operations succeed
        self.audit.commit_transaction(message)
    except Exception:
        self.audit.abort_transaction()
        raise
    finally:
        self._fs_lock.release()
```

### Thread Safety Considerations

1. **Thread-Local Storage**: `self._local` in stores for per-thread state
2. **Reentrant Locks**: Lock counter tracks acquisition depth
3. **Immutable Data**: Pydantic models for thread-safe data passing
4. **EventEmitter**: Thread-safe list of callbacks (protected by locks)

---

## Performance Optimizations

### Subquery RowID Optimization

**Problem**: Full JOIN operations between events and decisions are slow.

**Solution**: Use pre-fetched RowID for direct lookups.

```python
# In semantic store meta.get_upsert():
# Optimized query that uses RowID:
INSERT INTO decisions (fid, target, ...)
VALUES (?, ?, ...)
WHERE rowid NOT IN (
    SELECT id FROM events WHERE linked_id IN (?, ?, ...)
)
```

**Impact**: Search operations improved from ~500 ops/sec to **19,000+ ops/sec**.

### Embedding Cache

**Implementation**: `_MODEL_CACHE` in `VectorStore`

```python
class VectorStore:
    def __init__(self, index_path, model_name, workers):
        self._cache = {}
        self._max_cache = 100

    def encode(self, sentences):
        for text in sentences:
            if text in self._cache:
                return self._cache[text]
            embedding = self.model.encode(text)
            if len(self._cache) >= self._max_cache:
                self._cache.pop(next(iter(self._cache)))
            self._cache[text] = embedding
```

**Impact**: Repeated searches (e.g., "database migrations") are ~10x faster.

### Batch Operations

**Link Counting**:

```python
# Old way (N queries):
for semantic_id in semantic_ids:
    count = SELECT COUNT(*) FROM events WHERE linked_id = ?

# New way (1 query):
SELECT linked_id, COUNT(*), SUM(link_strength)
FROM events
WHERE linked_id IN (?, ?, ?, ...)
GROUP BY linked_id
```

**Impact**: Fetching link counts for 50 decisions reduced from 50 queries to 1.

### Lazy Loading

**VectorStore**:

```python
class VectorStore:
    def __init__(self, index_path, model_name, workers):
        self._model = None  # Don't load yet
        self._dimension = None

    def _ensure_loaded(self):
        if self._model is None:
            self._model = load_model(self.model_name)
            self._dimension = self._model.get_dimension()

    def add_document(self, doc_id, text):
        self._ensure_loaded()  # Load only on first use
        # ... add document
```

**Impact**: Startup time reduced by ~2 seconds when vector search isn't used immediately.

---

## Security Considerations

### Trust Boundaries

```python
class TrustBoundary(str, Enum):
    AGENT_WITH_INTENT = "agent"  # Agent with human oversight
    HUMAN_ONLY = "human"          # Human-only operations
```

**Application**:

```python
# In MCPServer:
def _validate_isolation(self, decision_ids: List[str]):
    """
    Enforces that agents can only supersede decisions created via MCP.
    Human-created decisions are protected.
    """
    if self.default_role != MCPRole.ADMIN:
        for d_id in decision_ids:
            path = os.path.join(self.memory.semantic.repo_path, d_id)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    content = f.read()
                    if "[via MCP]" not in content:
                        raise PermissionError(
                            f"Isolation Violation: Decision {d_id} was "
                            "created by a human and cannot be modified by an agent."
                        )
```

### Audit Logging

**Location**: `server/audit.py`

```python
class AuditLogger:
    def log_access(self, role: str, tool: str, params: dict,
                   success: bool, error: str = None):
        """
        Logs all MCP access for security monitoring.

        Format: timestamp | level | message
        """
        msg = f"PID: {pid} | Role: {role} | Tool: {tool} | Status: {status}"
        if error:
            msg += f" | Error: {error}"
        self.logger.info(msg)
```

**Audit File**: `.ledgermind/audit.log`

### Path Validation

**GitIndexer**:

```python
def _validate_path_safety(self):
    """
    Prevents path traversal attacks.
    Ensures repo path is within current working directory.
    """
    abs_repo_path = os.path.realpath(os.path.abspath(self.repo_path))
    cwd = os.path.realpath(os.getcwd())

    try:
        if os.path.commonpath([cwd, abs_repo_path]) != cwd:
            raise ValueError(
                f"Security violation: Access to {self.repo_path} "
                "is outside of allowed scope (CWD: {cwd})."
            )
    except ValueError:
        # Can happen on different drives (Windows)
        raise ValueError("Security violation: Path outside allowed scope.")
```

### API Key Authentication

```python
# In MCPServer:
def _validate_auth(self):
    if not self.api_key:
        return

    ctx: Context = getattr(self.mcp, "context", None)
    if ctx and hasattr(ctx, "request_context"):
        headers = getattr(ctx.request_context.request, "headers", {})
        provided_key = headers.get("X-API-Key") or headers.get("x-api-key")
        if provided_key != self.api_key:
            raise PermissionError("Invalid or missing X-API-Key header.")
```

**Environment Variable**: `LEDGERMIND_API_KEY`

---

## Extension Points

LedgerMind supports extension through several injection points.

### Custom Stores

Via provider interfaces:

```python
# Custom episodic store
class MyEpisodicStore(EpisodicProvider):
    def append(self, event, linked_id=None):
        # Custom implementation
        return 123

# Usage:
memory = Memory(
    episodic_store=MyEpisodicStore(),
    ...
)

# Custom metadata store
class MyMetadataStore(MetadataStore):
    def upsert(self, fid, target, status, ...):
        # Custom implementation

# Usage:
semantic = SemanticStore(
    meta_store=MyMetadataStore(),
    ...
)
```

### Custom Arbiters

```python
# Custom conflict resolution
def my_arbiter(new_decision, old_decisions):
    # Use your LLM or custom logic
    resolution = call_llm(new_decision, old_decisions)
    return resolution

# Usage:
bridge.record_decision(
    title="Use PostgreSQL",
    target="db",
    rationale="...",
    arbiter_callback=my_arbiter
)
```

### Webhook Integration

```bash
# Start server with webhooks
ledgermind run --path .ledgermind \
    --metrics-port 9090 \
    --rest-port 8080 \
    --capabilities '{"webhooks":["https://my-server.com/hook"]}'
```

**Webhook Payload**:

```json
{
  "event": "decision_created",
  "data": {
    "decision_id": "abc123",
    "title": "Use PostgreSQL"
  },
  "timestamp": 1677645200.123
}
```

---

## Next Steps

For implementation details:
- [API Reference](api-reference.md) — All public methods
- [Data Schemas](data-schemas.md) — Complete model definitions
- [Configuration](configuration.md) — Environment variables and CLI options

For practical usage:
- [Quick Start](quickstart.md) — Step-by-step setup
- [Integration Guide](integration-guide.md) — Client integration patterns
- [Workflows](workflow.md) — Common operational patterns
