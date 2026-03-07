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

class ProposalContent(BaseModel):
    # CRITICAL: Allow mutations during enrichment and lifecycle updates
    model_config = ConfigDict(frozen=False, extra='allow')
    
    decision_id: StrictStr = Field(default_factory=lambda: str(uuid.uuid4()))
    title: StrictStr
    target: TargetStr
    status: ProposalStatus = ProposalStatus.DRAFT
    rationale: RationaleStr
    compressive_rationale: Optional[str] = None
    namespace: str = "default"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    
    # Unified Lifecycle Fields
    phase: DecisionPhase = DecisionPhase.PATTERN
    vitality: DecisionVitality = DecisionVitality.ACTIVE
    stability_score: float = 0.0
    frequency: int = 1
    
    # Epistemic Model Fields
    keywords: List[str] = Field(default_factory=list, description="Semantic keywords for better retrieval")
    strengths: List[str] = Field(default_factory=list, description="Arguments in favor of this hypothesis")
    objections: List[str] = Field(default_factory=list, description="Active counter-arguments or missing evidence")
    counter_patterns: List[str] = Field(default_factory=list, description="Scenarios where this hypothesis was expected to trigger but didn't")
    alternative_ids: List[str] = Field(default_factory=list, description="IDs of competing proposals for the same cluster of evidence")
    
    evidence_event_ids: List[int] = Field(default_factory=list)
    total_evidence_count: int = 0
    counter_evidence_event_ids: List[int] = Field(default_factory=list) 
    
    suggested_consequences: List[str] = Field(default_factory=list)
    suggested_supersedes: List[str] = Field(default_factory=list)
    
    first_observed_at: datetime = Field(default_factory=datetime.now)
    last_observed_at: datetime = Field(default_factory=datetime.now)
    hit_count: int = 0
    miss_count: int = 0 
    
    ready_for_review: bool = False


class DecisionStream(BaseModel):
    # CRITICAL: Allow mutations for temporal metrics and status decays
    model_config = ConfigDict(frozen=False, extra='allow')
    
    decision_id: StrictStr
    target: TargetStr
    title: StrictStr
    rationale: RationaleStr
    compressive_rationale: Optional[str] = None
    namespace: str = "default"
    scope: PatternScope = PatternScope.LOCAL
    status: str = "active"
    
    phase: DecisionPhase = DecisionPhase.PATTERN
    vitality: DecisionVitality = DecisionVitality.ACTIVE
    provenance: Literal["internal", "external"] = "internal"
    
    # Context & Links
    keywords: List[str] = Field(default_factory=list)
    evidence_event_ids: List[int] = Field(default_factory=list)
    total_evidence_count: int = 0
    consequences: List[str] = Field(default_factory=list)
    supersedes: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    attachments: List[Dict[str, str]] = Field(default_factory=list)
    
    # Lifecycle Metrics
    frequency: int = 0
    unique_contexts: int = 0
    hit_count: int = 0
    last_hit_at: Optional[datetime] = None
    confidence: float = 1.0
    stability_score: float = 0.0
    
    procedural_ids: List[str] = Field(default_factory=list)
    
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)
    lifetime_days: float = 0.0
    reinforcement_density: float = 0.0
    coverage: float = 0.0
    
    estimated_removal_cost: float = 0.0
    estimated_utility: float = 0.0

    schema_version: int = 1

class DecisionContent(BaseModel):
    model_config = ConfigDict(frozen=False, extra='allow')
    title: StrictStr
    target: TargetStr
    status: str = "active"
    rationale: RationaleStr
    compressive_rationale: Optional[str] = None
    namespace: str = "default"
    keywords: List[str] = Field(default_factory=list)
    evidence_event_ids: List[int] = Field(default_factory=list)
    total_evidence_count: int = 0
    consequences: List[str] = Field(default_factory=list)
    supersedes: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    attachments: List[Dict[str, str]] = Field(default_factory=list)
    
    @field_validator('title', 'target', 'rationale')
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Field cannot be empty')
        return v

class MemoryEvent(BaseModel):
    schema_version: int = Field(default=1)
    source: Literal["user", "agent", "system", "reflection_engine", "bridge"]
    kind: Literal["decision", "error", "config_change", "assumption", "constraint", "result", "proposal", "context_snapshot", "context_injection", "task", "call", "commit_change", "prompt", "intervention", "reflection_summary"]
    content: StrictStr
    context: Union[DecisionContent, ProposalContent, DecisionStream, Dict[str, Any]] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

    @field_validator('content')
    @classmethod
    def sanitize_and_validate_content(cls, v: str) -> str:
        if not v.strip(): raise ValueError('Content cannot be empty')
        # Simple length check for speed in tests
        if len(v) > 1_000_000: raise ValueError('Content too long')
        return v

    @model_validator(mode='after')
    def validate_semantic_context(self) -> 'MemoryEvent':
        if self.kind in SEMANTIC_KINDS:
            if self.kind == KIND_PROPOSAL:
                if isinstance(self.context, dict):
                    if "phase" in self.context or "decision_id" in self.context:
                        self.context = DecisionStream(**self.context)
                    else:
                        self.context = ProposalContent(**self.context)
            else:
                if isinstance(self.context, dict):
                    if "decision_id" in self.context or "phase" in self.context:
                        self.context = DecisionStream(**self.context)
                    else:
                        self.context = DecisionContent(**self.context)
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
