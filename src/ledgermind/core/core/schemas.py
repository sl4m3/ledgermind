from datetime import datetime
import uuid
from typing import Literal, Dict, Any, Optional, List, Annotated, Union
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator, ConfigDict
from enum import Enum
import re
import html

try:
    from bleach import clean
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False
    def clean(text, tags=None, protocols=None, strip=None, strip_comments=None):
        if tags is None:
            tags = []
        return html.escape(text)

class TrustBoundary(str, Enum):
    AGENT_WITH_INTENT = "agent"
    HUMAN_ONLY = "human"

# Constants for Event Kinds
KIND_DECISION = "decision"
KIND_ERROR = "error"
KIND_CONFIG = "config_change"
KIND_ASSUMPTION = "assumption"
KIND_CONSTRAINT = "constraint"
KIND_RESULT = "result"
KIND_CALL = "call"
KIND_PROMPT = "prompt"
KIND_PROPOSAL = "proposal"
KIND_SNAPSHOT = "context_snapshot"
KIND_INJECTION = "context_injection"
KIND_INTERVENTION = "intervention"
KIND_REFLECTION_SUMMARY = "reflection_summary"

SEMANTIC_KINDS = [KIND_DECISION, KIND_CONSTRAINT, KIND_ASSUMPTION, KIND_PROPOSAL, KIND_INTERVENTION]

StrictStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
RationaleStr = Annotated[str, StringConstraints(min_length=10, strip_whitespace=True)]
TargetStr = Annotated[str, StringConstraints(min_length=3, strip_whitespace=True)]


class DecisionPhase(str, Enum):
    PATTERN = "pattern"
    EMERGENT = "emergent"
    CANONICAL = "canonical"

class DecisionVitality(str, Enum):
    ACTIVE = "active"
    DECAYING = "decaying"
    DORMANT = "dormant"

class PatternScope(str, Enum):
    LOCAL = "local"
    SYSTEM = "system"
    INFRA = "infra"

class ProposalStatus(str, Enum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FALSIFIED = "falsified"

# --- V5.0 Unified Hypothesis Components ---

class ProceduralStep(BaseModel):
    """A single step in a distilled procedural guide."""
    action: str
    expected_outcome: Optional[str] = None
    rationale: Optional[str] = None

class ProceduralContent(BaseModel):
    """A collection of steps forming a procedural instruction."""
    steps: List[ProceduralStep] = Field(default_factory=list)
    target_task: Optional[str] = None

class BaseSemanticContent(BaseModel):
    model_config = ConfigDict(frozen=False, extra='allow')
    
    title: StrictStr
    target: TargetStr
    status: str = "active"
    rationale: RationaleStr
    compressive_rationale: Optional[str] = None
    namespace: str = "default"
    
    # Lifecycle Metrics
    phase: DecisionPhase = DecisionPhase.PATTERN
    vitality: DecisionVitality = DecisionVitality.ACTIVE
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    stability_score: float = 0.0
    estimated_removal_cost: float = 0.0
    estimated_utility: float = 0.0
    coverage: float = 0.0
    last_hit_at: Optional[datetime] = None
    
    # Analytical & Procedural Fields (Unified V5.0)
    strengths: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    consequences: List[str] = Field(default_factory=list)
    procedural: Optional[ProceduralContent] = None
    enrichment_status: str = Field(default="pending", description="Status of LLM enrichment: completed, pending, or failed")
    total_evidence_count: int = 0
    
    # Metadata & Links
    keywords: List[str] = Field(default_factory=list)
    evidence_event_ids: List[int] = Field(default_factory=list)
    supersedes: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)
    hit_count: int = 0
    
    schema_version: int = 1

class DecisionStream(BaseSemanticContent):
    decision_id: StrictStr = Field(default_factory=lambda: str(uuid.uuid4()))
    scope: PatternScope = PatternScope.LOCAL
    provenance: Literal["internal", "external"] = "internal"
    frequency: int = 0
    lifetime_days: float = 0.0
    reinforcement_density: float = 0.0

class DecisionContent(BaseSemanticContent):
    # Backward compatibility for direct saves
    pass

class MemoryEvent(BaseModel):
    schema_version: int = Field(default=1)
    source: Literal["user", "agent", "system", "reflection_engine", "bridge"]
    kind: Literal["decision", "error", "config_change", "assumption", "constraint", "result", "proposal", "context_snapshot", "context_injection", "task", "call", "commit_change", "prompt", "intervention", "reflection_summary"]
    content: StrictStr
    context: Any = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('content')
    @classmethod
    def sanitize_and_validate_content(cls, v: str) -> str:
        if not v.strip(): raise ValueError('Content cannot be empty')
        if len(v) > 1_000_000: raise ValueError('Content too long')
        return v

    @model_validator(mode='after')
    def validate_semantic_context(self) -> 'MemoryEvent':
        """Convert dict context to appropriate type based on kind."""
        if self.kind in SEMANTIC_KINDS and isinstance(self.context, dict):
            try:
                # V5.0 Unified Knowledge Model
                self.context = DecisionStream(**self.context)
            except Exception:
                # Silently fallback to dict if data is incomplete/legacy
                pass
        return self

class MemoryDecision(BaseModel):
    should_persist: bool
    store_type: Literal["episodic", "semantic", "none"]
    reason: str
    priority: int = Field(default=0, ge=0, le=10)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ResolutionIntent(BaseModel):
    resolution_type: Literal["supersede", "deprecate", "abort", "record"]
    rationale: Annotated[str, StringConstraints(min_length=10, strip_whitespace=True)]
    target_decision_ids: List[str] = Field(default_factory=list)

class LedgermindConfig(BaseModel):
    storage_path: str = Field(default="../.ledgermind")
    ttl_days: int = Field(default=30, ge=1)
    trust_boundary: TrustBoundary = Field(default=TrustBoundary.AGENT_WITH_INTENT)
    namespace: str = "default"
    vector_model: str = Field(default="../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf")
    vector_workers: int = Field(default=0, ge=0)
    enable_git: bool = Field(default=True)
    relevance_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    enrichment_model: Optional[str] = Field(default=None)
    
    # Gemini CLI Configuration
    gemini_binary_path: Optional[str] = Field(default=None, description="Path to gemini CLI binary")
    gemini_global_config_path: str = Field(default="~/.gemini/settings.json", description="Path to global gemini config")
    gemini_project_config_path: str = Field(default=".gemini/settings.json", description="Path to project gemini config")
    gemini_config_mode: Literal["global", "project"] = Field(default="global", description="Gemini configuration mode")
    max_enrichment_tokens: int = Field(default=100000, ge=1000)

# --- V5.0 Deep Integrity Trajectory Models ---

class TrajectoryAtom(BaseModel):
    """A single logical cycle of interaction (e.g., prompt -> calls -> result)."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    events: List[MemoryEvent] = Field(default_factory=list)
    start_time: datetime
    end_time: datetime
    signature: str = "" # structural sequence e.g., "prompt->call:read_file->result"
    deduced_target: Optional[str] = None
    
    @property
    def event_ids(self) -> List[int]:
        return [e.metadata.get('event_id') for e in self.events if getattr(e, 'metadata', {}).get('event_id')]

class TrajectoryChain(BaseModel):
    """A sequence of linked atoms forming a comprehensive workflow pattern."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    atoms: List[TrajectoryAtom] = Field(default_factory=list)
    global_target: str = "unknown"
    context_files: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    
    @property
    def all_event_ids(self) -> List[int]:
        return [eid for atom in self.atoms for eid in atom.event_ids]
