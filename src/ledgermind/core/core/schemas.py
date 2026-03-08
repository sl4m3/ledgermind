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
    
    # Metadata & Links
    keywords: List[str] = Field(default_factory=list)
    evidence_event_ids: List[int] = Field(default_factory=list)
    supersedes: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)
    hit_count: int = 0
    
    schema_version: int = 1

class ProposalContent(BaseSemanticContent):
    decision_id: StrictStr = Field(default_factory=lambda: str(uuid.uuid4()))
    status: ProposalStatus = ProposalStatus.DRAFT
    
    # Proposal-specific fields
    strengths: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    counter_patterns: List[str] = Field(default_factory=list)
    alternative_ids: List[str] = Field(default_factory=list)
    expected_outcome: Optional[str] = None
    ready_for_review: bool = False

class DecisionStream(BaseSemanticContent):
    decision_id: StrictStr
    scope: PatternScope = PatternScope.LOCAL
    provenance: Literal["internal", "external"] = "internal"
    frequency: int = 0
    lifetime_days: float = 0.0
    reinforcement_density: float = 0.0
    consequences: List[str] = Field(default_factory=list)

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
            if self.kind == KIND_PROPOSAL:
                if "phase" in self.context or "decision_id" in self.context:
                    self.context = DecisionStream(**self.context)
                else:
                    self.context = ProposalContent(**self.context)
            else:
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
