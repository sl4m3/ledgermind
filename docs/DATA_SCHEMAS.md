# Data Schemas

All data models in LedgerMind are defined using Pydantic v2 with strict validation. This document covers every schema used as input or output across the public API.

---

## Core Event Models

### MemoryEvent

The base type for all information flowing into `process_event()`.

```python
class MemoryEvent(BaseModel):
    schema_version: int = 1
    source: Literal["user", "agent", "system", "reflection_engine", "bridge"]
    kind: Literal[
        "decision", "error", "config_change", "assumption", "constraint",
        "result", "proposal", "context_snapshot", "context_injection",
        "task", "call", "commit_change", "prompt"
    ]
    content: str  # min_length=1, strip_whitespace=True
    context: Union[DecisionContent, ProposalContent, Dict[str, Any]]
    timestamp: datetime  # auto-set to now()
```

**Routing:** `kind` values in `SEMANTIC_KINDS = ["decision", "constraint", "assumption", "proposal"]` are persisted to the SemanticStore. All others go to EpisodicStore.

**Auto-casting:** When `kind` is a semantic kind, the `context` dict is automatically cast to `DecisionContent` or `ProposalContent` via a model validator.

---

### DecisionContent

Context payload for `decision`, `constraint`, and `assumption` events.

```python
class DecisionContent(BaseModel):
    title: str            # StrictStr: min_length=1, strip_whitespace=True
    target: str           # TargetStr: min_length=3, strip_whitespace=True
    status: Literal["active", "deprecated", "superseded"] = "active"
    rationale: str        # RationaleStr: min_length=10, strip_whitespace=True
    consequences: List[str] = []
    supersedes: List[str] = []        # IDs of decisions this one replaces
    superseded_by: Optional[str] = None  # ID of the decision that replaced this
    attachments: List[Dict[str, str]] = []  # [{type: "image", path: "blobs/..."}]
```

---

### ProposalContent

Context payload for `proposal` events. Implements a full epistemic model.

```python
class ProposalContent(BaseModel):
    title: str
    target: str
    status: ProposalStatus = ProposalStatus.DRAFT
    rationale: str        # min_length=10
    confidence: float     # ge=0.0, le=1.0

    # Epistemic model
    strengths: List[str] = []            # Arguments in favor of the hypothesis
    objections: List[str] = []           # Counter-arguments or missing evidence
    counter_patterns: List[str] = []     # Scenarios where hypothesis didn't trigger
    alternative_ids: List[str] = []      # IDs of competing proposals (same evidence cluster)

    # Evidence tracking
    evidence_event_ids: List[int] = []
    counter_evidence_event_ids: List[int] = []

    # Acceptance hints
    suggested_consequences: List[str] = []
    suggested_supersedes: List[str] = []  # Decisions to supersede when accepted

    # Procedural extension (MemP principle)
    procedural: Optional[ProceduralContent] = None

    # Lifecycle metadata
    first_observed_at: datetime = now()
    last_observed_at: datetime = now()
    hit_count: int = 0
    miss_count: int = 0
    ready_for_review: bool = False
```

#### `ProposalStatus` enum

| Value | Description |
|---|---|
| `draft` | Newly created, under observation |
| `accepted` | Converted to an active decision |
| `rejected` | Manually or automatically rejected |
| `falsified` | Disproven by contradictory evidence |

---

### ProceduralContent

Extension of `ProposalContent` for storing step-by-step action sequences (MemP principle).

```python
class ProceduralContent(BaseModel):
    steps: List[ProceduralStep]
    target_task: str
    success_evidence_ids: List[int]

class ProceduralStep(BaseModel):
    action: str
    rationale: Optional[str] = None
    expected_outcome: Optional[str] = None
```

---

## Operation Result Models

### MemoryDecision

Returned by every write operation (`process_event`, `record_decision`, etc.).

```python
class MemoryDecision(BaseModel):
    should_persist: bool
    store_type: Literal["episodic", "semantic", "none"]
    reason: str
    priority: int = 0     # ge=0, le=10
    metadata: Dict[str, Any] = {}
```

**`metadata` keys after a successful write:**
- `file_id` — relative path to the Markdown file (semantic writes)
- `event_id` — integer row ID in episodic SQLite (episodic writes and immortal links)

---

### ResolutionIntent

Passed to `process_event()` to authorize a supersede or deprecate operation.

```python
class ResolutionIntent(BaseModel):
    resolution_type: Literal["supersede", "deprecate", "abort"]
    rationale: str        # min_length=15, strip_whitespace=True
    target_decision_ids: List[str]
```

---

### DecayReport

Returned by `run_decay()`.

```python
class DecayReport:
    archived: int           # Episodic events moved to status=archived
    pruned: int             # Episodic events physically deleted from SQLite
    retained_by_link: int   # Immortal events skipped
    semantic_forgotten: int # Semantic records deleted via forget()
```

---

## Configuration Model

### LedgermindConfig

```python
class LedgermindConfig(BaseModel):
    storage_path: str = "./memory"
    ttl_days: int = 30          # ge=1
    trust_boundary: TrustBoundary = TrustBoundary.AGENT_WITH_INTENT
    namespace: str = "default"
    vector_model: str = "all-MiniLM-L6-v2"
    enable_git: bool = True
    relevance_threshold: float = 0.35   # ge=0.0, le=1.0
```

---

## Trust Boundary Enum

```python
class TrustBoundary(str, Enum):
    AGENT_WITH_INTENT = "agent"   # Default. Agents can read and write.
    HUMAN_ONLY = "human"          # Agent decision writes are silently blocked.
```

---

## MCP Request/Response Models

### Request Models

```python
class RecordDecisionRequest(BaseModel):
    title: str          # min_length=1
    target: str         # min_length=1
    rationale: str      # min_length=10
    consequences: List[str] = []

class SupersedeDecisionRequest(BaseModel):
    title: str
    target: str
    rationale: str      # min_length=15
    old_decision_ids: List[str]   # min_length=1
    consequences: List[str] = []

class SearchDecisionsRequest(BaseModel):
    query: str          # min_length=1
    limit: int = 5      # ge=1, le=20
    mode: Literal["strict", "balanced", "audit"] = "balanced"

class AcceptProposalRequest(BaseModel):
    proposal_id: str

class SyncGitHistoryRequest(BaseModel):
    repo_path: str = "."
    limit: int = 20     # ge=1, le=100
```

### Response Models

```python
class BaseResponse(BaseModel):
    status: Literal["success", "error"]
    message: Optional[str] = None

class DecisionResponse(BaseResponse):
    decision_id: Optional[str] = None

class SearchResultItem(BaseModel):
    id: str
    score: float
    status: str
    preview: str
    kind: str

class SearchResponse(BaseResponse):
    results: List[SearchResultItem] = []

class SyncGitResponse(BaseResponse):
    indexed_commits: int = 0
```

---

## Event Kind Reference

| Kind | Store | Description |
|---|---|---|
| `decision` | Semantic | A strategic or architectural choice. |
| `constraint` | Semantic | An immutable rule that must not be violated. |
| `assumption` | Semantic | A belief held by the agent that may need revision. |
| `proposal` | Semantic | A hypothesis generated by reflection, pending review. |
| `error` | Episodic | A failed operation or exception. |
| `result` | Episodic | Outcome of an operation (success or failure). |
| `prompt` | Episodic | An incoming user or system prompt. |
| `commit_change` | Episodic | A Git commit imported via `sync_git()`. |
| `config_change` | Episodic | A configuration modification event. |
| `context_snapshot` | Episodic | A snapshot of agent state at a point in time. |
| `context_injection` | Episodic | A context block injected into an agent prompt. |
| `task` | Episodic | A discrete task assignment or completion. |
| `call` | Episodic | An external API or tool call. |
