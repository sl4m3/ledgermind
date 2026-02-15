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

SEMANTIC_KINDS = [KIND_DECISION, KIND_CONSTRAINT, KIND_ASSUMPTION, KIND_PROPOSAL]

StrictStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]

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
    target: StrictStr
    status: ProposalStatus = ProposalStatus.DRAFT
    rationale: StrictStr
    confidence: float = Field(ge=0.0, le=1.0)
    
    # Epistemic Model Fields
    strengths: List[str] = Field(default_factory=list, description="Почему эта гипотеза вероятна")
    objections: List[str] = Field(default_factory=list, description="Факты или логика против этой гипотезы")
    counter_patterns: List[str] = Field(default_factory=list, description="Сценарии, в которых эта гипотеза НЕ работает")
    epistemic_merit: float = Field(default=0.5, ge=0.0, le=1.0, description="Качество самой гипотезы (логичность, фальсифицируемость)")
    
    evidence_event_ids: List[int] = Field(default_factory=list)
    counter_evidence_event_ids: List[int] = Field(default_factory=list) # Events that contradict this hypothesis
    competing_proposal_ids: List[str] = Field(default_factory=list) # Alternative hypotheses
    
    suggested_consequences: List[str] = Field(default_factory=list)
    suggested_supersedes: List[str] = Field(default_factory=list) # Какие решения предлагается заменить
    
    # MemP extension: Procedural data
    procedural: Optional[ProceduralContent] = None
    
    first_observed_at: datetime = Field(default_factory=datetime.now)
    last_observed_at: datetime = Field(default_factory=datetime.now)
    hit_count: int = 0
    miss_count: int = 0 # Количество успешных операций в этой области
    
    ready_for_review: bool = False

class DecisionContent(BaseModel):
    title: StrictStr
    target: StrictStr
    status: Literal["active", "deprecated", "superseded"] = "active"
    rationale: StrictStr
    consequences: List[str] = Field(default_factory=list)
    supersedes: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None

    @field_validator('title', 'target', 'rationale')
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('Field cannot be empty')
        return v

class MemoryEvent(BaseModel):
    schema_version: int = Field(default=1)
    source: Literal["user", "agent", "system", "reflection_engine"]
    kind: Literal["decision", "error", "config_change", "assumption", "constraint", "result", "proposal", "context_snapshot", "task", "call", "commit_change"]
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
    store_type: Literal["episodic", "semantic", "vector", "none"]
    reason: str
    priority: int = Field(default=0, ge=0, le=10)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ResolutionIntent(BaseModel):
    resolution_type: Literal["supersede", "deprecate", "abort"]
    rationale: StrictStr
    target_decision_ids: List[str]

class EmbeddingProvider:
    """Interface for generating text embeddings."""
    def get_embedding(self, text: str) -> List[float]:
        raise NotImplementedError

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self.get_embedding(t) for t in texts]
