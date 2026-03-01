# Data Schemas

Complete reference for all Pydantic data models used in LedgerMind.

---

## Introduction

This document provides a comprehensive reference for all data schemas in LedgerMind. All models use Pydantic for validation, serialization, and type hints.

**Audience**:
- **Developers** extending LedgerMind or adding custom schema fields
- **System Architects** understanding data flow and constraints
- **Contributors** modifying or creating new event types
- **Tool Developers** building custom arbiters or LLM integrations

**Schema Versioning**:
LedgerMind uses a `schema_version` field to track data format evolution. Current version is **1**.

---

## Base Models

### StrictStr

String type with minimum length validation.

```python
class StrictStr(str):
    min_length: int = 1

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type):
        schema = super().__get_pydantic_core_schema__(source_type)
        field = schema["fields"][0]
        field["min_length"] = cls.min_length
        return schema
```

**Usage**:
```python
from ledgermind.core.core.schemas import StrictStr

title = StrictStr(title="Use PostgreSQL")  # Valid
rationale = StrictStr(rationale="ACID compliance")  # Valid

# Invalid (raises ValidationError)
short = StrictStr(title="X")  # Raises: ensure this value has at least 1 characters
```

**Fields Using StrictStr**:
- `MemoryEvent.content`
- `DecisionContent.title`
- `DecisionContent.rationale`
- `ProposalContent.title`
- `ProposalContent.rationale`
- All text fields requiring minimum length

### TargetStr

String type for target identifiers with minimum length validation.

```python
class TargetStr(str):
    min_length: int = 3

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type):
        schema = super().__get_pydantic_core_schema__(source_type)
        field = schema["fields"][0]
        field["min_length"] = cls.min_length
        return schema
```

**Usage**:
```python
from ledgermind.core.core.schemas import TargetStr

target = TargetStr(target="database")  # Valid
short = TargetStr(target="db")  # Raises: ensure this value has at least 3 characters
```

**Fields Using TargetStr**:
- `DecisionContent.target`
- `ProposalContent.target`
- `DecisionStream.target`
- All `target` fields requiring minimum 3 characters

### RationaleStr

String type for rationale content with minimum length validation.

```python
class RationaleStr(str):
    min_length: int = 10

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type):
        schema = super().__get_pydantic_core_schema__(source_type)
        field = schema["fields"][0]
        field["min_length"] = cls.min_length
        return schema
```

**Usage**:
```python
from ledgermind.core.core.schemas import RationaleStr

rationale = RationaleStr(rationale="Provides ACID compliance and JSONB support")  # Valid
short = RationaleStr(rationale="Too short")  # Raises: ensure this value has at least 10 characters
```

**Fields Using RationaleStr**:
- `DecisionContent.rationale`
- `ProposalContent.rationale`
- `SupersedeDecisionRequest.rationale`
- All `rationale` fields requiring minimum 10 characters

---

## Event-Related Schemas

### MemoryEvent

Base model for all events processed by LedgerMind memory system.

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

| Field | Type | Description | Validation |
|-------|------|-------------|-------------|
| `schema_version` | int | Schema version (default: 1) | — |
| `source` | Literal | Origin of the event | Must be one of: user, agent, system, reflection_engine, bridge |
| `kind` | Literal | Event type | Must be one of: decision, error, config_change, assumption, constraint, result, proposal, context_snapshot, context_injection, task, call, commit_change, prompt, intervention, reflection_summary |
| `content` | StrictStr | Event payload (min 1 char) | Required, min_length=1 |
| `context` | Union | Structured metadata | — | Variable by kind |
| `timestamp` | datetime | When event occurred | Auto-generated if not provided |

**Event Kinds**:

| Kind | Storage | Purpose |
|------|----------|-------------|
| `decision` | Semantic | Long-term strategic decisions |
| `proposal` | Semantic | Draft hypotheses for evaluation |
| `intervention` | Semantic | Normative system acts |
| `constraint` | Semantic | System limitations or rules |
| `assumption` | Semantic | Beliefs without full evidence |
| `error` | Episodic | Error events |
| `result` | Episodic | Execution results |
| `config_change` | Episodic | Configuration updates |
| `task` | Episodic | Task descriptions |
| `call` | Episodic | Tool/function calls |
| `commit_change` | Episodic | Git commits |
| `prompt` | Episodic | User inputs |
| `context_snapshot` | Episodic | Environment state |
| `context_injection` | Episodic | Injected memory into agent |
| `intervention` | Episodic | Human decisions |
| `reflection_summary` | Episodic | Reflection cycle results |

**Context by Kind**:

| Kind | Context Type |
|------|-------------|
| `decision` | `DecisionContent` | Title, target, rationale, consequences, etc. |
| `proposal` | `ProposalContent` | Title, target, rationale, strengths, objections, etc. |
| `intervention` | `DecisionContent` | Title, target, rationale (normative act) |
| `constraint` | `DecisionContent` | Title, target, rationale (constraint rule) |
| `assumption` | `DecisionContent` | Title, target, rationale (belief) |
| `error`, `result` | `Dict` | Arbitrary metadata (error code, success flag) |
| `config_change`, `task` | `Dict` | Configuration data, command output |
| `call` | `Dict` | Tool name, parameters |
| `commit_change` | `Dict` | Commit hash, author, changed files |
| `prompt` | `StrictStr` | User query text |
| `context_snapshot` | `Dict` | Environment state (disk, git, etc.) |
| `context_injection` | `Dict` | Injected memory format |
| `intervention` | N/A | (Special kind, used internally) |
| `reflection_summary` | `Dict` | Reflection cycle metadata |

---

### DecisionContent

Content model for semantic decisions (not proposals).

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

**Fields**:

| Field | Type | Default | Validation |
|-------|------|-------------|----------|
| `title` | StrictStr | — | Required, min_length=1 |
| `target` | TargetStr | — | Required, min_length=3 |
| `rationale` | RationaleStr | — | Required, min_length=10 |
| `status` | str | `"active"` | Must be: active, deprecated, superseded |
| `namespace` | str | `"default"` | Logical partition for isolation |
| `keywords` | List[str] | `[]` | Optional search terms |
| `evidence_event_ids` | List[int] | `[]` | IDs of supporting episodic events |
| `consequences` | List[str] | `[]` | Rules or effects |
| `superseded_by` | str | `None` | ID of decision that superseded this |
| `attachments` | List[Dict] | `[]` | File attachments |
| `procedural` | ProceduralContent | `None` | Optional procedural knowledge |

**Status Values**:

| Status | Description | Lifecycle |
|--------|-------------|----------|
| `active` | Currently valid and in use | Normal operation |
| `deprecated` | No longer in use but kept for history | Phase out |
| `superseded` | Replaced by another decision | Phase out |

---

### ProposalContent

Content model for draft proposals requiring evaluation.

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
    strengths: List[str]
    objections: List[str]
    counter_patterns: List[str]
    alternative_ids: List[str]
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

**Fields**:

| Field | Type | Default | Description |
|-------|------|-------------|----------|
| `status` | ProposalStatus | `DRAFT` | Draft awaiting evaluation |
| `confidence` | float | `0.0` | Confidence in hypothesis quality (0.0-1.0) |
| `procedural` | ProceduralContent | `None` | Optional procedural steps from distillation |
| `first_observed_at` | datetime | `None` | Auto-set on first observation |
| `last_observed_at` | datetime | `None` | Auto-updated on each observation |
| `hit_count` | int | `0` | How many times this proposal was successfully used |
| `miss_count` | int | `0` | How many times this proposal was falsified |

**Epistemic Fields**:

| Field | Description |
|-------|------|-------------|
| `keywords` | List[str] | Search terms for retrieval |
| `strengths` | List[str] | Arguments in favor of this proposal |
| `objections` | List[str] | Active counter-arguments |
| `counter_patterns` | List[str] | Scenarios where this prediction was wrong |
| `alternative_ids` | List[str] | IDs of competing proposals |
| `evidence_event_ids` | List[int] | IDs of supporting episodic events |

---

### DecisionStream

Extended model for autonomous lifecycle management of knowledge.

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
    provenance: Literal["internal", "external"] = "internal"

    # Context & Links
    keywords: List[str]
    evidence_event_ids: List[int]
    consequences: List[str]
    superseded_by: Optional[str]
    supersedes: List[str]
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

**Fields**:

| Field | Type | Description |
|-------|------|-------------|----------|
| `decision_id` | StrictStr | — | Unique decision identifier |
| `phase` | DecisionPhase | — | PATTERN, EMERGENT, or CANONICAL |
| `vitality` | DecisionVitality | — | ACTIVE, DECAYING, or DORMANT |
| `scope` | PatternScope | — | LOCAL, SYSTEM, or INFRA |
| `provenance` | str | — | INTERNAL or EXTERNAL |
| `confidence` | float | — | Quality score (0.0-1.0) |
| `procedural` | ProceduralContent | — | Optional distilled procedures |
| `frequency` | int | — | How often this pattern has been observed |
| `coverage` | float | — | Percentage of observation window covered |
| `stability_score` | float | — | Lower variance = more stable |

**Lifecycle Phases**:

| Phase | Confidence Range | Frequency Threshold | Coverage Threshold | Stability Threshold | Removal Cost Threshold |
|--------|------------------|----------------|-------------------|-------------------|----------------|
| PATTERN | Any | < 3 | — | — | — |
| EMERGENT | ≥ 0.5 | ≥ 3 | > 0.5 | > 0.6 | — | < 0.5 |
| CANONICAL | — | — | > 0.3 | > 0.6 | > 0.6 | — |

**Vitality Decay Rules**:

- **ACTIVE**: Last used within 7 days
- **DECAYING**: Used 7-30 days ago, confidence - 0.05 per week
- **DORMANT**: Used > 30 days ago, confidence - 0.2 per week

---

### ProceduralContent & ProceduralStep

Models for distilled procedural knowledge from successful trajectories.

```python
class ProceduralStep(BaseModel):
    action: str
    rationale: Optional[str]
    expected_outcome: Optional[str]

class ProceduralContent(BaseModel):
    steps: List[ProceduralStep]
    target_task: str
    success_evidence_ids: List[int]
```

**Usage**:
```python
from ledgermind.core.core.schemas import ProceduralContent, ProceduralStep

procedural = ProceduralContent(
    steps=[
        ProceduralStep(
            action="Run database migrations",
            rationale="Ensures schema consistency",
            expected_outcome="All migrations apply successfully"
        ),
        ProceduralStep(
            action="Verify connection strings",
            rationale="Prevents connection string typos",
            expected_outcome="Valid connection format"
        )
    ],
    target_task="database_configuration",
    success_evidence_ids=[123, 456]
)
```

**Purpose**: Automatically populated by `DistillationEngine` during reflection cycles. Stores step-by-step instructions extracted from successful task trajectories.

---

## Context-Related Schemas

### ProposalStatus

Status enum for draft proposals.

```python
class ProposalStatus(str, Enum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FALSIFIED = "falsified"
```

**Status Flow**:
- `DRAFT` → `ACCEPTED` or `REJECTED` or `FALSIFIED`
- `FALSIFIED` proposals remain but are marked as contradicted by new data

---

### DecisionPhase

Phase enum for lifecycle progression.

```python
class DecisionPhase(str, Enum):
    PATTERN = "pattern"
    EMERGENT = "emergent"
    CANONICAL = "canonical"
```

**Phase Transition Logic** (see [Architecture](architecture.md) for details):

| Transition | Requirements |
|-----------|-------------|
| PATTERN → EMERGENT | frequency ≥ 3 OR confidence ≥ 0.5; AND (lifetime > 0.5 OR frequency ≥ 5) |
| EMERGENT → CANONICAL | coverage > 0.3 AND stability > 0.6 AND removal_cost > 0.5 AND vitality == ACTIVE |

---

### DecisionVitality

Vitality enum for tracking usage recency.

```python
class DecisionVitality(str, Enum):
    ACTIVE = "active"
    DECAYING = "decaying"
    DORMANT = "dormant"
```

**Vitality Rules**:

| State | Days Since Last Use | Confidence Impact |
|-----------|---------------------|-------------------|-------------------|
| ACTIVE | < 7 | None | No change |
| DECAYING | 7-30 | -0.05 per week | Gradual reduction |
| DORMANT | > 30 | -0.2 per week | Significant reduction |

---

### PatternScope

Scope enum for categorizing decision impact.

```python
class PatternScope(str, Enum):
    LOCAL = "local"
    SYSTEM = "system"
    INFRA = "infra"
```

**Scope Definitions**:

| Scope | Description | Examples |
|--------|-------------|----------|
| LOCAL | Affects single component or module | Authentication flow, logging level |
| SYSTEM | Affects multiple components | API design, caching strategy |
| INFRA | Affects infrastructure or deployment | Database choice, hosting provider |

**Impact on Removal Cost**: Higher scope decisions are harder to replace.

---

### TrustBoundary

Trust boundary enum for controlling memory operation permissions.

```python
class TrustBoundary(str, Enum):
    AGENT_WITH_INTENT = "agent_with_intent"
    HUMAN_ONLY = "human_only"
```

**Boundary Descriptions**:

| Boundary | Description | Protected Operations |
|-----------|-------------|----------|
| AGENT_WITH_INTENT | Agent operations with human oversight | Record, propose, supersede decisions created by same agent; Accept proposals via callback |
| HUMAN_ONLY | Human-only operations | All memory operations; Accept/reject proposals; Forget memories |

**Use Case**: Multiple agents working on same project with different namespaces.

---

### ResolutionIntent

Intent specification for conflict resolution.

```python
class ResolutionIntent(BaseModel):
    resolution_type: Literal["supersede", "deprecate", "abort"]
    rationale: str
    target_decision_ids: List[str]
```

**Resolution Types**:

| Type | Description | Effect |
|-----------|-------------|----------|
| `supersede` | Replace old decisions with new one | Old decisions marked as `superseded_by` pointing to new decision |
| `deprecate` | Mark old decisions as outdated | Old decisions marked as `deprecated` (not replaced) |
| `abort` | Cancel the operation | No changes made |

**Validation**: Must include all conflicting decision IDs in `target_decision_ids`. See [Architecture](architecture.md).

---

### MemoryDecision

Return type for memory operations.

```python
class MemoryDecision(BaseModel):
    should_persist: bool
    store_type: Literal["episodic", "semantic", "none"]
    reason: str
    priority: int = Field(default=0, ge=0, le=10)
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

**Fields**:

| Field | Type | Description |
|-------|------|-------------|----------|
| `should_persist` | bool | Whether event was successfully stored |
| `store_type` | str | Where it was stored (episodic, semantic, none) |
| `reason` | str | Explanation of routing decision or why not stored |
| `priority` | int | 0-10 | Importance level (internal routing) |
| `metadata` | dict | Additional data (file_id, event_id, etc.) |

**Use Cases**:

```python
# Success case
MemoryDecision(
    should_persist=True,
    store_type="semantic",
    reason="Decision recorded",
    metadata={"file_id": "abc123"}
)

# Failure case
MemoryDecision(
    should_persist=False,
    store_type="none",
    reason="CONFLICT: Active decision exists. ResolutionIntent required."
)

# Success with metadata
MemoryDecision(
    should_persist=True,
    store_type="semantic",
    reason="Decision recorded",
    priority=5,
    metadata={
        "file_id": "abc123",
        "event_id": 456
    }
)
```

---

## API Models

### Request Models

Models for MCP server and integration bridge operations.

```python
class RecordDecisionRequest(BaseModel):
    title: StrictStr
    target: TargetStr
    rationale: RationaleStr
    consequences: List[str]
    namespace: str = "default"
```

```python
class SupersedeDecisionRequest(BaseModel):
    title: StrictStr
    target: TargetStr
    rationale: RationaleStr
    old_decision_ids: List[str] = Field(min_length=1)
    consequences: List[str]
    namespace: str = "default"
```

```python
class SearchDecisionsRequest(BaseModel):
    query: StrictStr
    limit: int = Field(default=5, ge=1, le=50)
    offset: int = Field(default=0, ge=0)
    namespace: str = "default"
    mode: Literal["strict", "balanced", "audit"] = "balanced"
```

```python
class AcceptProposalRequest(BaseModel):
    proposal_id: str
```

### Response Models

Models for MCP server responses.

```python
class DecisionResponse(BaseResponse):
    decision_id: Optional[str]
```

```python
class SearchResponse(BaseResponse):
    results: List[SearchResultItem]
```

```python
class SearchResultItem(BaseModel):
    id: str
    score: float
    status: str
    preview: str
    kind: str
```

```python
class SyncGitResponse(BaseResponse):
    indexed_commits: int = 0
```

---

## Enums

### Event Kinds

Complete enumeration of all event types.

```python
KIND_DECISION = "decision"
KIND_PROPOSAL = "proposal"
KIND_INTERVENTION = "intervention"
KIND_CONSTRAINT = "constraint"
KIND_ASSUMPTION = "assumption"
KIND_ERROR = "error"
KIND_RESULT = "result"
KIND_CONFIG_CHANGE = "config_change"
KIND_TASK = "task"
KIND_CALL = "call"
KIND_COMMIT_CHANGE = "commit_change"
KIND_PROMPT = "prompt"
KIND_CONTEXT_SNAPSHOT = "context_snapshot"
KIND_CONTEXT_INJECTION = "context_injection"
KIND_REFLECTION_SUMMARY = "reflection_summary"

# Storage categories
SEMANTIC_KINDS = [KIND_DECISION, KIND_PROPOSAL, KIND_INTERVENTION, KIND_CONSTRAINT, KIND_ASSUMPTION]

# Event kind mapping for routing
KIND_STORAGE_MAP = {
    **KIND_DECISION**: "semantic",
    **KIND_PROPOSAL**: "semantic",
    **KIND_INTERVENTION**: "semantic",
    **KIND_CONSTRAINT**: "semantic",
    **KIND_ASSUMPTION**: "semantic",
}
# All others route to episodic
```

---

## Complete Reference

### All Fields

Complete reference of all fields across all models with types, defaults, and constraints.

| Field | Type | Model(s) | Default | Validation |
|-------|------|-------------|----------|----------|
| `schema_version` | int | `MemoryEvent`, `DecisionStream` | 1 | — |
| `source` | Literal | `MemoryEvent` | user, agent, system, reflection_engine, bridge | user | Must be one of allowed values |
| `kind` | Literal | `MemoryEvent` | One of event kinds | — | — |
| `content` | StrictStr | `MemoryEvent` | — | Required, min_length=1 | — |
| `context` | Union | `MemoryEvent` | — | Variable by kind | — |
| `timestamp` | datetime | `MemoryEvent` | — | Auto-set to `datetime.now()` | — |
| `title` | StrictStr | `DecisionContent`, `ProposalContent` | — | Required, min_length=1 | — |
| `target` | TargetStr | `DecisionContent`, `ProposalContent`, `DecisionStream` | — | Required, min_length=3 | — |
| `rationale` | RationaleStr | `DecisionContent`, `SupersedeDecisionRequest` | — | Required, min_length=10 | — |
| `status` | str | `DecisionContent` | — | active, deprecated, or superseded | — |
| `namespace` | str | All models | "default" | — | Logical partition | — |
| `keywords` | List[str] | `DecisionContent`, `ProposalContent`, `DecisionStream` | — | [] | — |
| `evidence_event_ids` | List[int] | `DecisionContent`, `DecisionContent`, `ProposalContent` | — | [] | — |
| `consequences` | List[str] | `DecisionContent` | — | [] | — |
| `superseded_by` | str | `DecisionContent` | — | None | — |
| `attachments` | List[Dict] | `DecisionContent` | — | [] | — |
| `procedural` | `ProceduralContent` | `ProposalContent`, `DecisionStream` | — | None | — |
| `frequency` | int | `ProposalContent`, `DecisionStream` | — | 0 | — |
| `unique_contexts` | int | `ProposalContent`, `DecisionStream` | — | 0 | — |
| `hit_count` | int | `ProposalContent`, `DecisionStream` | — | 0 | — |
| `confidence` | float | `ProposalContent`, `DecisionStream` | — | 0.0 | — |
| `stability_score` | float | `DecisionStream` | — | 0.0 | — |
| `reinforcement_density` | float | `DecisionStream` | — | 0.0 | — |
| `coverage` | float | `DecisionStream` | — | 0.0 | — |
| `lifetime_days` | float | `DecisionStream` | — | 0.0 | — |
| `phase` | DecisionPhase | `DecisionStream` | — | PATTERN | — |
| `vitality` | DecisionVitality | `DecisionStream` | — | ACTIVE | — |
| `scope` | PatternScope | `DecisionStream` | — | LOCAL | — |
| `provenance` | str | `DecisionStream` | — | internal | — |
| `first_seen` | datetime | `DecisionStream` | — | None | — |
| `last_seen` | datetime | `DecisionStream` | — | None | — |
| `procedureal_ids` | List[str] | `DecisionStream` | — | [] | — |

| Field Validators**:

| Field | Validation |
|-------|----------|
| `content` | min_length=1 | — |
| `title` | min_length=1 | — |
| `target` | min_length=3 | — |
| `rationale` | min_length=10 | — |
| `confidence` | ge=0.0, le=1.0 | — |
| `frequency` | ge=0 | — |
| `coverage` | ge=0.0, le=1.0 | — |
| `stability_score` | ge=0.0, le=1.0 | — |

---

## Migration Guide

### Schema Version History

| Version | Changes | Breaking Changes | Migration Required |
|--------|----------|--------------|------------------|----------|
| 1 | Initial | First version | — | — | No |
| 2 | 1.1.0 | Add `schema_version` field | — | Yes | No | Update `Memory` to set `schema_version=1` on new events |

### Breaking Changes

None in current version (v1). Data format is backward compatible.

### Migration Strategies

When upgrading from older versions:

**Version 0.x → v1**:
- Add `schema_version` field to existing events
- Use default value of 1 for new events

**Version 1 → v1.1.0+**:
- No breaking changes
- No action required

**Version 1.22.0 → v1.23.0** (Current):
- No breaking changes
- Full backward compatibility
- Existing data is valid as-is

---

## Next Steps

For implementation usage:
- [Quick Start](quickstart.md) — Step-by-step setup
- [Integration Guide](integration-guide.md) — Client integration patterns
- [Architecture](architecture.md) — System internals

For reference implementation:
- [API Reference](api-reference.md) — Method signatures
- [Configuration](configuration.md) — Environment variables and options

For extending schemas:
- All base types (`StrictStr`, `TargetStr`, `RationaleStr`) are available for custom model extensions
- New event kinds should use `Literal` with explicit value definition
- Follow Pydantic patterns for custom validators

**For testing**:
- Pydantic provides automatic validation
- Use `Field(min_length=...)` for custom constraints
- Default values can be overridden in tests
