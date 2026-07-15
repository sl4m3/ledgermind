from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum
import math

class Phase(str, Enum):
    PATTERN = "pattern"
    EMERGENT = "emergent"
    CANONICAL = "canonical"

class Vitality(str, Enum):
    ACTIVE = "active"
    DECAYING = "decaying"
    DORMANT = "dormant"

class KnowledgeItem(BaseModel):
    """Knowledge item with phase."""
    
    # Identity
    fid: str
    title: str
    target: str
    profile: str
    
    # Content
    rationale: str
    compressive_rationale: str
    
    # Behavioral Pattern
    strengths: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    consequences: List[str] = Field(default_factory=list)
    
    # Phase (maturity level)
    phase: Phase = Field(default=Phase.PATTERN)
    vitality: Vitality = Field(default=Vitality.ACTIVE)
    
    # Metrics
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    stability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_utility: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    
    # Evidence (accumulative merge count)
    total_evidence_count: int = Field(default=0, ge=0)
    
    # Temporal
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)
    hit_count: int = Field(default=0, ge=0)
    last_hit_at: Optional[datetime] = None
    
    # Links
    supersedes: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    
    # Metadata
    schema_version: int = Field(default=3)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    def calculate_confidence(self) -> float:
        """Calculate confidence from hit_count."""
        return min(1.0, math.log1p(self.hit_count) / 2.3)
