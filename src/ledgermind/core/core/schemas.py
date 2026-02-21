from datetime import datetime
from typing import Literal, Dict, Any, Optional, List, Annotated, Union
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator
from enum import Enum

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
KIND_PROPOSAL = "proposal"
KIND_SNAPSHOT = "context_snapshot"
KIND_INJECTION = "context_injection"

SEMANTIC_KINDS = [KIND_DECISION, KIND_CONSTRAINT, KIND_ASSUMPTION, KIND_PROPOSAL]

StrictStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
RationaleStr = Annotated[str, StringConstraints(min_length=10, strip_whitespace=True)]
TargetStr = Annotated[str, StringConstraints(min_length=3, strip_whitespace=True)]

class ProposalStatus(str, Enum):
    DRAFT = "draft"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FALSIFIED = "falsified"

class ProceduralStep(BaseModel):
    action: str
    rationale: Optional[str] = None
    expected_outcome: Optional[str] = None

class ProceduralContent(BaseModel):
    steps: List[ProceduralStep]
    target_task: str
    success_evidence_ids: List[int]

class ProposalContent(BaseModel):
    title: StrictStr
    target: TargetStr
    status: ProposalStatus = ProposalStatus.DRAFT
    rationale: RationaleStr
    confidence: float = Field(ge=0.0, le=1.0)
    
    # Epistemic Model Fields
    strengths: List[str] = Field(default_factory=list, description="Arguments in favor of this hypothesis")
    objections: List[str] = Field(default_factory=list, description="Active counter-arguments or missing evidence")
    counter_patterns: List[str] = Field(default_factory=list, description="Scenarios where this hypothesis was expected to trigger but didn't")
    alternative_ids: List[str] = Field(default_factory=list, description="IDs of competing proposals for the same cluster of evidence")
    
    evidence_event_ids: List[int] = Field(default_factory=list)
    counter_evidence_event_ids: List[int] = Field(default_factory=list) # Events that weaken this hypothesis
    
    suggested_consequences: List[str] = Field(default_factory=list)
    suggested_supersedes: List[str] = Field(default_factory=list) # Какие решения предлагается заменить
    
    # MemP extension: Procedural data
    procedural: Optional[ProceduralContent] = None
    
    first_observed_at: datetime = Field(default_factory=datetime.now)
    last_observed_at: datetime = Field(default_factory=datetime.now)
    hit_count: int = 0
    miss_count: int = 0 # Количество неудачных операций в этой области
    
    ready_for_review: bool = False

class DecisionContent(BaseModel):
    title: StrictStr
    target: TargetStr
    status: Literal["active", "deprecated", "superseded"] = "active"
    rationale: RationaleStr
    consequences: List[str] = Field(default_factory=list)
    supersedes: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    attachments: List[Dict[str, str]] = Field(default_factory=list) # List of {type: "image", path: "blobs/..."}

    @field_validator('title', 'target', 'rationale')
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Field cannot be empty')
        return v

class MemoryEvent(BaseModel):
    schema_version: int = Field(default=1)
    source: Literal["user", "agent", "system", "reflection_engine", "bridge"]
    kind: Literal["decision", "error", "config_change", "assumption", "constraint", "result", "proposal", "context_snapshot", "context_injection", "task", "call", "commit_change", "prompt"]
    content: StrictStr
    context: Union[DecisionContent, ProposalContent, Dict[str, Any]] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)

    @field_validator('content')
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Content cannot be empty')
        return v

    @model_validator(mode='after')
    def validate_semantic_context(self) -> 'MemoryEvent':
        if self.kind in SEMANTIC_KINDS:
            if self.kind == KIND_PROPOSAL:
                if isinstance(self.context, dict):
                    self.context = ProposalContent(**self.context)
            else:
                # Force validation of context as DecisionContent for other semantic types
                if isinstance(self.context, dict):
                    self.context = DecisionContent(**self.context)
        return self

class MemoryDecision(BaseModel):
    should_persist: bool
    store_type: Literal["episodic", "semantic", "none"]
    reason: str
    priority: int = Field(default=0, ge=0, le=10)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ResolutionIntent(BaseModel):
    resolution_type: Literal["supersede", "deprecate", "abort"]
    rationale: Annotated[str, StringConstraints(min_length=15, strip_whitespace=True)]
    target_decision_ids: List[str]

class LedgermindConfig(BaseModel):
    storage_path: str = Field(default="./memory")
    ttl_days: int = Field(default=30, ge=1)
    trust_boundary: TrustBoundary = Field(default=TrustBoundary.AGENT_WITH_INTENT)
    namespace: str = Field(default="default")
    vector_model: str = Field(default="all-MiniLM-L6-v2")
    vector_workers: int = Field(default=0, ge=0, description="Number of workers for multi-process encoding. 0 for auto-detection.")
    enable_git: bool = Field(default=True)
    relevance_threshold: float = Field(default=0.35, ge=0.0, le=1.0)

