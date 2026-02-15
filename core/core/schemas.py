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

SEMANTIC_KINDS = [KIND_DECISION, KIND_CONSTRAINT, KIND_ASSUMPTION]

StrictStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]

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
    source: Literal["user", "agent", "system"]
    kind: Literal["decision", "error", "config_change", "assumption", "constraint", "result"]
    content: StrictStr
    context: Union[DecisionContent, Dict[str, Any]] = Field(default_factory=dict)
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
            # Force validation of context as DecisionContent for semantic types
            if isinstance(self.context, dict):
                # This will raise ValidationError if required fields are missing/empty
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
