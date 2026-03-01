from datetime import datetime
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

class ProceduralStep(BaseModel):
    action: str
    rationale: Optional[str] = None
    expected_outcome: Optional[str] = None

class ProceduralContent(BaseModel):
    steps: List[ProceduralStep]
    target_task: str
    success_evidence_ids: List[int]

class ProposalContent(BaseModel):
    model_config = ConfigDict(extra='allow')
    title: StrictStr
    target: TargetStr
    status: ProposalStatus = ProposalStatus.DRAFT
    rationale: RationaleStr
    namespace: str = "default"
    confidence: float = Field(ge=0.0, le=1.0)
    
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


class DecisionStream(BaseModel):
    model_config = ConfigDict(extra='allow')
    decision_id: StrictStr
    target: TargetStr
    title: StrictStr
    rationale: RationaleStr
    namespace: str = "default"
    scope: PatternScope = PatternScope.LOCAL
    status: Literal["active", "deprecated", "superseded"] = "active"
    
    phase: DecisionPhase = DecisionPhase.PATTERN
    vitality: DecisionVitality = DecisionVitality.ACTIVE
    provenance: Literal["internal", "external"] = "internal"
    
    # Context & Links
    keywords: List[str] = Field(default_factory=list)
    evidence_event_ids: List[int] = Field(default_factory=list)
    consequences: List[str] = Field(default_factory=list)
    supersedes: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    attachments: List[Dict[str, str]] = Field(default_factory=list)
    
    # Lifecycle Metrics
    frequency: int = 0
    unique_contexts: int = 0
    hit_count: int = 0
    confidence: float = 1.0
    stability_score: float = 0.0
    
    # MemP Linking: Associated procedural knowledge
    procedural: Optional[ProceduralContent] = None
    procedural_ids: List[str] = Field(default_factory=list, description="IDs of dedicated procedural records for this stream")
    
    first_seen: datetime = Field(default_factory=datetime.now)
    last_seen: datetime = Field(default_factory=datetime.now)
    lifetime_days: float = 0.0
    reinforcement_density: float = 0.0
    coverage: float = 0.0
    
    estimated_removal_cost: float = 0.0
    estimated_utility: float = 0.0

    schema_version: int = 1

class DecisionContent(BaseModel):
    title: StrictStr
    target: TargetStr
    status: Literal["active", "deprecated", "superseded"] = "active"
    rationale: RationaleStr
    namespace: str = "default"
    keywords: List[str] = Field(default_factory=list, description="Semantic keywords for better retrieval")
    evidence_event_ids: List[int] = Field(default_factory=list)
    consequences: List[str] = Field(default_factory=list)
    supersedes: List[str] = Field(default_factory=list)
    superseded_by: Optional[str] = None
    attachments: List[Dict[str, str]] = Field(default_factory=list) # List of {type: "image", path: "blobs/..."}
    
    # MemP extension: Procedural data
    procedural: Optional[ProceduralContent] = None

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
        """
        Sanitizes content to prevent XSS, Markdown injection, and other attacks.
        Also enforces length limits and checks for suspicious patterns.
        """
        # ===== LAYER 1: Empty check (existing) =====
        if not v.strip():
            raise ValueError('Content cannot be empty')

        # ===== LAYER 2: Length limits (DoS protection) =====
        MIN_LENGTH = 1
        MAX_LENGTH = 500_000  # 500KB max for memory events

        if len(v) < MIN_LENGTH:
            raise ValueError(f'Content too short (min {MIN_LENGTH} characters)')

        if len(v) > MAX_LENGTH:
            raise ValueError(
                f'Content too long ({len(v)} characters, max {MAX_LENGTH})'
            )

        # ===== LAYER 3: Null byte and control character check =====
        if '\x00' in v:
            raise ValueError('Content contains null bytes')

        # Check for excessive control characters
        control_chars = sum(1 for c in v if ord(c) < 32 and c not in '\t\n\r')
        if control_chars > len(v) * 0.1:  # More than 10% control chars
            raise ValueError('Content contains too many control characters')

        # ===== LAYER 4: Unicode attack patterns =====
        # Bidirectional override attacks
        bidi_patterns = ['\u202E', '\u202F', '\u2066', '\u2067', '\u2068', '\u2069']
        if any(pattern in v for pattern in bidi_patterns):
            raise ValueError('Content contains bidirectional override characters')

        # Zero-width characters (can hide attacks)
        zero_width = ['\u200B', '\u200C', '\u200D', '\uFEFF']
        if sum(1 for c in v if c in zero_width) > 10:
            raise ValueError('Content contains excessive zero-width characters')


        # ===== LAYER 5: HTML/Markdown sanitization =====
        # Use bleach to strip dangerous HTML
        # Allow common Markdown-safe tags
        ALLOWED_TAGS = []  # Strip ALL HTML tags for safety
        ALLOWED_PROTOCOLS = ['http', 'https', 'ftp']

        sanitized = clean(
            v,
            tags=ALLOWED_TAGS,
            protocols=ALLOWED_PROTOCOLS,
            strip=True,           # Remove unsafe tags
            strip_comments=True   # Remove HTML comments
        )

        # ===== LAYER 6: URL/Link sanitization =====
        # Check for dangerous URL schemes
        dangerous_schemes = [
            'javascript:', 'data:', 'vbscript:', 'mailto:', 'file:'
        ]

        # Check all URLs in content
        url_pattern = r'(https?|ftp)://[^\s<>"\')]|javascript:[^\s]*;'
        urls = re.findall(url_pattern, sanitized, re.IGNORECASE)

        for url in urls:
            if any(scheme in url.lower() for scheme in dangerous_schemes):
                raise ValueError(
                    f'Content contains dangerous URL scheme'
                )

        return sanitized

    @model_validator(mode='after')
    def validate_semantic_context(self) -> 'MemoryEvent':
        if self.kind in SEMANTIC_KINDS:
            if self.kind == KIND_PROPOSAL:
                if isinstance(self.context, dict):
                    # Distinguish between ProposalContent and DecisionStream (if embedded in proposal)
                    if "phase" in self.context or "decision_id" in self.context:
                        self.context = DecisionStream(**self.context)
                    else:
                        self.context = ProposalContent(**self.context)
            else:
                # Force validation of context as DecisionContent or DecisionStream
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
    resolution_type: Literal["supersede", "deprecate", "abort"]
    rationale: Annotated[str, StringConstraints(min_length=15, strip_whitespace=True)]
    target_decision_ids: List[str]

class LedgermindConfig(BaseModel):
    storage_path: str = Field(default="../.ledgermind")
    ttl_days: int = Field(default=30, ge=1)
    trust_boundary: TrustBoundary = Field(default=TrustBoundary.AGENT_WITH_INTENT)
    namespace: str = Field(default="default")
    vector_model: str = Field(default="../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf")
    vector_workers: int = Field(default=0, ge=0, description="Number of workers for multi-process encoding. 0 for auto-detection.")
    enable_git: bool = Field(default=True)
    relevance_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

