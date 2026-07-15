# LedgerMind Lifecycle Pipeline Redesign

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/lifecycle-pipeline-redesign.md)

## [S1] Problem Statement

### Current Architecture Issues

**Issue 1: Parallel Execution**
```
Current: Decay and Merge run in parallel
Problem: Merge "steals" candidates that Decay should delete
Result: Weak knowledge survives because Merge processes it first
```

**Issue 2: Merge Uses Only Similarity**
```
Current: Merge threshold = 0.8 (similarity only)
Problem: No consideration of confidence, stability, phase, evidence
Result: Raw hypotheses merge with mature decisions, diluting quality
```

**Issue 3: Reflection Processes Raw Events**
```
Current: Reflection runs every 5 minutes on raw events
Problem: Calculates metrics on unprocessed data, wasteful CPU
Result: Metrics are inaccurate because they're based on raw, not enriched data
```

**Issue 4: No Minimum Retention**
```
Current: New hypotheses can be merged/deleted immediately
Problem: Hypothesis created 1 minute ago can be merged with older one
Result: Valid new knowledge lost before it has chance to be validated
```

**Issue 5: Cross-Phase Merge**
```
Current: PATTERN can merge with CANONICAL
Problem: Mature, validated knowledge merged with raw, unvalidated
Result: CANONICAL knowledge degraded by PATTERN noise
```

### Quantified Impact

- **522 decisions** currently marked as superseded (many incorrectly)
- **1070 hypotheses** in draft status (not processed)
- **Semantic drift** observed in merged decisions
- **CPU spikes** from vector similarity calculations on every merge

## [S2] Solution Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    ENRICHMENT PHASE                         │
│                                                             │
│  Raw Event ──→ Post-LLM Hook ──→ N Enriched Atoms          │
│  (agent DB)         │                                       │
│                     └───────────────────┐                   │
│                                         ▼                   │
│                                  Semantic Store             │
│                                  (proposals only)           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    LIFECYCLE PIPELINE                        │
│                    (Every 5 minutes)                         │
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   MERGE     │───→│   DECAY     │───→│  PROMOTE    │     │
│  │             │    │             │    │             │      │
│  │ Confidence  │    │ Dedup       │    │ PATTERN →   │     │
│  │ based       │    │ only        │    │ EMERGENT →  │     │
│  │ decay       │    │             │    │ CANONICAL   │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    STORAGE LAYER                            │
│                                                             │
│  Semantic Store (Git+SQLite)                                │
│  ┌─────────────────┐                                        │
│  │ proposals       │                                        │
│  │ (enriched atoms)│                                        │
│  │ with metrics    │                                        │
│  │ git commits     │                                        │
│  └─────────────────┘                                        │
│                                                             │
│  Agent DB (state.db) - raw events (у агента)                │
└─────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Enriched-First**: Raw event → LLM enriches → Enriched atom = Proposal
2. **Sequential Pipeline**: Merge → Decay → Promote (not parallel)
3. **Merge = Dedup Only**: Supersede weaker, keep stronger (no consolidation)
4. **Minimum Retention**: New proposals protected for 14 days
5. **No Episodic Store**: Raw events stay in agent DB (state.db)
6. **Self-Contained Atoms**: Enriched atoms don't reference raw events
7. **Proposal → Decision**: Evidence + Confidence thresholds (not phase-based)
8. **Single Store**: Only semantic store (proposals with metrics)

### Clean Start Decision

**Old data (pre-plugin) NOT processed:**
- 182 sessions, 22,644 messages in state.db → archive only
- Raw events stay as evidence in episodic store
- Not converted to enriched atoms
- Metrics would be meaningless (confidence=0, stability=0)

**New data (post-plugin) processed:**
- Enriched atoms created via post_llm hook
- Clean metrics from first day
- Pipeline processes only new proposals

## [S3] Knowledge Item Schema

### Key Change
**Knowledge Item** with phases (PATTERN → EMERGENT → CANONICAL). No separate proposal/decision.

### Complete Schema

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum

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
    fid: str = Field(description="Unique ID: PHASE_TIMESTAMP_HASH")
    title: str = Field(description="Clear technical title")
    target: str = Field(description="Hierarchical path (e.g., 'core/api/memory')")
    profile: str = Field(description="Workspace (hermes, openclaw)")
    
    # Content
    rationale: str = Field(description="Deep technical explanation with Markdown")
    compressive_rationale: str = Field(description="Exactly 3 sentences summarizing technical essence")
    
    # Behavioral Pattern (embedded by LLM)
    strengths: List[str] = Field(description="Advantages of this knowledge")
    objections: List[str] = Field(description="Risks or concerns")
    consequences: List[str] = Field(description="Impact if applied")
    
    # Phase (maturity level)
    phase: Phase = Field(default=Phase.PATTERN)
    vitality: Vitality = Field(default=Vitality.ACTIVE)
    
    # Metrics
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)  # Hit-count based
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
    supersedes: List[str] = Field(default_factory=list, description="FIDs this item supersedes")
    superseded_by: Optional[str] = Field(default=None, description="FID that superseded this")
    
    # Metadata
    schema_version: int = Field(default=3)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
```

### Field Calculations

**confidence** — How often this proposal was used (injected into context)?
```
confidence = min(1.0, log1p(hit_count) / 2.3)
```

**Scales:**
- hit_count = 0: confidence = 0.0
- hit_count = 1: confidence = 0.30
- hit_count = 10: confidence = 1.0 (maximum)
- hit_count = 100: confidence = 1.0 (maximum)

**Logic:** More injections = more reliable. Saturates at 10 injections.

**stability_score** — How consistent are the reinforcing events over time?
```
if total_evidence_count < 2:
    stability = 0.0  # New proposal, no intervals yet
else:
    intervals = [days between consecutive reinforcing events]
    variance = variance(intervals)
    delta_stability = max(0.0, 1.0 - (variance / (lifetime_days + 1.0)))
    age_factor = min(1.0, lifetime_days / 7.0)
    stability = delta_stability * (0.5 + 0.5 × age_factor)
```

**Logic:** Regular intervals = high stability. Sporadic intervals = low stability. New proposals start at 0.

**coverage** — What fraction of observation window has this been seen?
```
coverage = lifetime_days / observation_window_days  (default: 30 days)
```

**estimated_utility** — How useful is this knowledge?
```
utility = stability × 0.3 + confidence × 0.5 + coverage × 0.2
```

**total_evidence_count** — Accumulative merge count?
```
# When A merges with B:
A.evidence_count = A.evidence_count + B.evidence_count + 1
```

**Logic:** More merges = more confirmations of this knowledge.

## [S4] Post-LLM Hook (Enrichment)

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    POST-LLM HOOK FLOW                        │
└─────────────────────────────────────────────────────────────┘

1. User/Agent sends message
   ↓
2. LLM processes message (normal flow)
   ↓
3. post_llm_hook fires (Hermes/OpenClaw)
   ├── Gets: session_id, user_message, assistant_response, history
   ├── Has: LLM context in cache (same model)
   └── Calls: LLM with enrichment prompt
   ↓
4. LLM returns JSON: { "atoms": [...] }
   ├── 1 atom per distinct topic
   ├── Each atom has: title, rationale, confidence, keywords, etc.
   └── LLM embedded behavioral patterns in rationale
   ↓
5. For each atom:
   ├── Generate unique FID
   ├── Calculate initial metrics
   ├── Save to episodic.db (raw event + enriched atom)
   └── Save to semantic store (decision with metrics)
   ↓
6. If LLM fails:
   ├── Save raw data to episodic.db
   ├── Set enrichment_status = "pending"
   └── Will be processed in next cycle
```

### LLM Prompt Template

```python
ENRICHMENT_PROMPT = """
You are a Knowledge Architect analyzing an interaction round.

### TASK: Extract knowledge atoms from this interaction.

### INPUT:
<raw_event>
{raw_event}
</raw_event>

### CONVERSATION CONTEXT:
{conversation_history}

### OUTPUT FORMAT:
Return a JSON object with an "atoms" array. Each atom:
{{
  "title": "Clear technical title (e.g., 'Background Worker Isolation')",
  "target": "Hierarchical path (e.g., 'core/api/memory')",
  "rationale": "Deep technical explanation with Markdown. Include behavioral patterns.",
  "compressive_rationale": "Exactly 3 sentences summarizing the technical essence",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "strengths": ["advantage 1", "advantage 2"],
  "objections": ["risk 1", "risk 2"],
  "consequences": ["impact 1", "impact 2"],
  "procedural": [
    {{
      "action": "What was done",
      "expected_outcome": "What should happen",
      "rationale": "Why this approach"
    }}
  ]
}}

### RULES:
1. Create SEPARATE atoms for DISTINCT topics
2. One atom per distinct technical decision/observation
3. Include behavioral patterns in rationale (e.g., "The user prefers X because Y")
4. Write as the original author (not "this event shows...")
5. If multiple topics in one event, return multiple atoms
6. Return ONLY JSON array, no explanation
"""
```

### Multi-Atom Example

**Input:** User executes refactoring plan touching frontend and backend

**LLM Response:**
```json
{
  "atoms": [
    {
      "title": "Frontend Component Refactoring",
      "target": "ui/components",
      "rationale": "Refactored Hero component to use CSS :has() for hover state persistence. Changed badge expansion to use flex-col layout with min-height. This pattern should be applied to other interactive components.",
      "compressive_rationale": "Hero component refactored for better hover state management using CSS :has(). Badge expansion now uses flex-col with min-height to prevent layout shift. Pattern applicable to other interactive components.",
      "keywords": ["react", "css", "hover", "component"],
      "strengths": ["Better UX", "No layout shift"],
      "objections": ["CSS :has() not supported in older browsers"],
      "consequences": ["Improved user experience", "Potential compatibility issues"]
    },
    {
      "title": "Database Migration Strategy",
      "target": "db/migration",
      "rationale": "Implemented zero-downtime migration strategy using shadow tables. New schema created alongside old, data synced via triggers, then atomic switch. This pattern ensures no data loss during migrations.",
      "compressive_rationale": "Zero-downtime migration using shadow tables and triggers. Data synced atomically with schema switch. Pattern ensures no data loss.",
      "keywords": ["postgresql", "migration", "zero-downtime"],
      "strengths": ["No downtime", "Data safety"],
      "objections": ["Increased storage during migration"],
      "consequences": ["Safer deployments", "Slightly more complex migration process"]
    }
  ]
}
```

### Initial Metrics Calculation

```python
def create_enriched_atom(llm_response: dict, raw_event: dict) -> EnrichedAtom:
    """Create enriched atom from LLM response."""
    
    now = datetime.now()
    
    atom = EnrichedAtom(
        fid=generate_fid(),  # proposal_YYYYMMDD_HHMMSS_MICROSECONDS_HASH
        title=llm_response["title"],
        target=llm_response["target"],
        rationale=llm_response["rationale"],
        compressive_rationale=llm_response["compressive_rationale"],
        keywords=llm_response["keywords"],
        strengths=llm_response["strengths"],
        objections=llm_response["objections"],
        consequences=llm_response["consequences"],
        procedural=llm_response["procedural"],
        
        # Initial metrics
        phase=DecisionPhase.PATTERN,
        vitality=DecisionVitality.ACTIVE,
        confidence=1.0,  # New hypothesis starts at 1.0
        stability_score=0.0,
        estimated_utility=0.0,
        estimated_removal_cost=0.2,  # PATTERN phase cost
        coverage=0.0,
        
        # Evidence
        total_evidence_count=1,
        evidence_event_ids=[raw_event["event_id"]],
        
        # Temporal
        first_seen=now,
        last_seen=now,
        hit_count=0,
        last_hit_at=None,
        
        # Links
        supersedes=[],
        superseded_by=None,
        merge_status=None,
        enrichment_status="completed",
    )
    
    return atom
```

## [S5] Sequential Pipeline

### Pipeline Execution

```python
class LifecyclePipeline:
    """Sequential pipeline: Merge → Decay → Promote."""
    
    def __init__(self, memory: MemoryProtocol, config: PipelineConfig):
        self.memory = memory
        self.config = config
        self.decay_engine = DecayEngine(memory, config.decay)
        self.merge_engine = MergeEngine(memory, config.merge)
        self.promotion_engine = PromotionEngine(memory, config.promotion)
    
    def run(self):
        """Execute pipeline sequentially."""
        
        logger.info("Starting lifecycle pipeline...")
        
        # Step 1: Decay (remove weak knowledge)
        logger.info("Step 1: Running decay...")
        decay_result = self.decay_engine.run()
        logger.info(f"Decay complete: {decay_result.deleted} deleted, {decay_result.decaying} decaying")
        
        # Step 2: Merge (consolidate strong knowledge)
        logger.info("Step 2: Running merge...")
        merge_result = self.merge_engine.run()
        logger.info(f"Merge complete: {merge_result.merged} merged, {merge_result.skipped} skipped")
        
        # Step 3: Promote (advance phase maturity)
        logger.info("Step 3: Running promotion...")
        promote_result = self.promotion_engine.run()
        logger.info(f"Promotion complete: {promote_result.promoted} promoted")
        
        logger.info("Pipeline complete.")
        
        return PipelineResult(
            decay=decay_result,
            merge=merge_result,
            promote=promote_result,
        )
```

### Timing

```
Background Worker (every 5 minutes):
  0:00 - Pipeline starts
  0:00-0:30 - Decay runs (fast: confidence-based)
  0:30-4:00 - Merge runs (slow: LLM calls for consolidation)
  4:00-4:30 - Promotion runs (fast: threshold checks)
  4:30-5:00 - Buffer for next cycle
```

## [S6] Decay Engine

### Decay Formula

```python
class DecayEngine:
    """Confidence-based decay with minimum retention."""
    
    def apply_decay(self, item: KnowledgeItem) -> float:
        """Apply decay to knowledge item confidence."""
        # Skip superseded items (already merged)
        if item.superseded_by:
            return item.confidence
        
        # Minimum retention check
        if item.total_evidence_count < self.minimum_evidence:
            days_since_creation = (datetime.now() - item.first_seen).days
            if days_since_creation < self.minimum_retention_days:
                return item.confidence
        
        # Calculate decay
        rate = self.get_decay_rate(item.confidence)
        days_inactive = (datetime.now() - item.last_seen).days
        steps = days_inactive // 7
        
        new_confidence = item.confidence - (rate * steps)
        
        # Auto-reinforce CANONICAL
        if item.phase == Phase.CANONICAL and item.confidence > 0.9:
            new_confidence = min(1.0, new_confidence + 0.01)
        
        return max(0.0, new_confidence)
    
    def calculate_vitality(self, item: KnowledgeItem) -> Vitality:
        """Calculate new vitality based on confidence and activity."""
        # Skip superseded items (already merged)
        if item.superseded_by:
            return item.vitality
        
        days_since_hit = 0
        if item.last_hit_at:
            days_since_hit = (datetime.now() - item.last_hit_at).days
        
        # ACTIVE -> DECAYING
        if item.vitality == Vitality.ACTIVE:
            if item.confidence < 0.5 or days_since_hit > 30:
                return Vitality.DECAYING
        
        # DECAYING -> ACTIVE (re-activation)
        if item.vitality == Vitality.DECAYING:
            if days_since_hit < 7:
                return Vitality.ACTIVE
        
        # DECAYING -> DORMANT
        if item.vitality == Vitality.DECAYING:
            if item.confidence < 0.2:
                return Vitality.DORMANT
        
        return item.vitality
```
            
            if new_confidence != decision.confidence:
                # Update confidence
                self.memory.semantic.update_decision(
                    decision.fid,
                    {"confidence": new_confidence}
                )
                
                # Update vitality
                new_vitality = self.calculate_vitality(decision, new_confidence)
                if new_vitality != decision.vitality:
                    self.memory.semantic.update_decision(
                        decision.fid,
                        {"vitality": new_vitality}
                    )
                
                # Track changes
                result.decaying += 1
                
                # Check for deletion
                if new_vitality == DecisionVitality.DORMANT and new_confidence < 0.1:
                    days_dormant = self.calculate_days_dormant(decision)
                    if days_dormant > 7:
                        self.memory.semantic.delete_decision(decision.fid)
                        result.deleted += 1
        
        return result
    
    def calculate_vitality(self, decision: EnrichedAtom, new_confidence: float) -> DecisionVitality:
        """Calculate new vitality based on confidence and activity."""
        
        days_since_hit = 0
        if decision.last_hit_at:
            days_since_hit = (datetime.now() - decision.last_hit_at).days
        
        # ACTIVE → DECAYING
        if decision.vitality == DecisionVitality.ACTIVE:
            if new_confidence < 0.9 or days_since_hit > 30:
                return DecisionVitality.DECAYING
        
        # DECAYING → ACTIVE (re-activation)
        if decision.vitality == DecisionVitality.DECAYING:
            if days_since_hit < 7:
                return DecisionVitality.ACTIVE
        
        # DECAYING → DORMANT
        if decision.vitality == DecisionVitality.DECAYING:
            if new_confidence < 0.2:
                return DecisionVitality.DORMANT
        
        return decision.vitality
```

### Decay Configuration

```python
class DecayConfig(BaseModel):
    """Configuration for decay engine."""
    
    confidence_thresholds: dict = {
        "fast": 0.3,
        "medium": 0.7
    }
    
    decay_rates: dict = {
        "fast": 0.15,      # confidence < 0.3
        "medium": 0.05,    # confidence 0.3-0.7
        "slow": 0.01       # confidence > 0.7
    }
    
    minimum_retention_days: int = 14
    minimum_evidence: int = 5
    dormant_to_delete_days: int = 7
```

### Decay Flow

```
For each decision:
  1. Check minimum retention
     ├── If evidence < 5 AND days_since_creation < 14: SKIP
     └── Otherwise: continue
  
  2. Calculate decay rate
     ├── confidence > 0.7: rate = 0.01/day
     ├── confidence 0.3-0.7: rate = 0.05/day
     └── confidence < 0.3: rate = 0.15/day
  
  3. Apply decay
     ├── days_inactive = (now - last_seen).days
     ├── steps = days_inactive // 7
     └── new_confidence = confidence - (rate × steps)
  
  4. Auto-reinforce CANONICAL
     ├── If phase == CANONICAL AND confidence > 0.9
     └── new_confidence = min(1.0, new_confidence + 0.01)
  
  5. Update vitality
     ├── ACTIVE → DECAYING: confidence < 0.5 OR last_hit > 30 days
     ├── DECAYING → ACTIVE: last_hit < 7 days
     └── DECAYING → DORMANT: confidence < 0.2
  
  6. Check deletion
     ├── If vitality == DORMANT AND confidence < 0.1
     ├── AND days_dormant > 7
     └── DELETE decision
```

## [S7] Merge Pipeline (Dedup Only)

### Key Change
**Merge = Dedup only** (no consolidation). Supersede weaker proposal, keep stronger.

### Overview

```
Merge Pipeline = Similarity Check → Dedup Gate → Supersede Weaker
```

### Step 1: Similarity Check

```python
def find_similar_decisions(decision: EnrichedAtom) -> List[EnrichedAtom]:
    """Find similar decisions using vector search."""
    
    # Get embedding for decision
    embedding = vector_store.get_embedding(decision.fid)
    
    # Search for similar
    candidates = vector_store.search(
        embedding,
        top_k=10,
        threshold=0.8
    )
    
    # Filter out self and already-merged
    candidates = [
        c for c in candidates
        if c.fid != decision.fid
        and c.merge_status != "pending"
    ]
    
    return candidates
```

### Step 2: Dedup Gate

```python
def should_merge(candidate: EnrichedAtom, target: EnrichedAtom) -> bool:
    """Check if two decisions should be merged."""
    
    # Phase compatibility
    if not phases_compatible(candidate.phase, target.phase):
        return False
    
    # Evidence gate
    if candidate.total_evidence_count < 5 or target.total_evidence_count < 5:
        return False
    
    # Confidence gate
    avg_confidence = (candidate.confidence + target.confidence) / 2
    if avg_confidence < 0.5:
        return False
    
    # Stability gate
    avg_stability = (candidate.stability_score + target.stability_score) / 2
    if avg_stability < 0.3:
        return False
    
    # Vitality gate
    if candidate.vitality == DecisionVitality.DORMANT or target.vitality == DecisionVitality.DORMANT:
        return False
    
    # Temporal gate
    days_diff = abs((candidate.first_seen - target.first_seen).days)
    if days_diff > 30:
        return False
    
    return True

def phases_compatible(phase1: DecisionPhase, phase2: DecisionPhase) -> bool:
    """Only merge within same phase tier."""
    tier_map = {
        DecisionPhase.PATTERN: 1,
        DecisionPhase.EMERGENT: 2,
        DecisionPhase.CANONICAL: 3
    }
    return tier_map[phase1] == tier_map[phase2]
```

### Step 3: Conflict Detection

```python
def detect_conflict(candidate: EnrichedAtom, target: EnrichedAtom) -> Optional[ConflictResult]:
    """Check if decisions contradict each other."""
    
    # Quick check: keyword overlap
    kw_overlap = len(set(candidate.keywords) & set(target.keywords))
    if kw_overlap < 2:
        return None  # No conflict
    
    # LLM-based conflict detection
    prompt = f"""
    Are these two decisions CONTRADICTING each other?
    
    Decision 1: {candidate.title}
    Rationale: {candidate.rationale[:200]}
    
    Decision 2: {target.title}
    Rationale: {target.rationale[:200]}
    
    Return JSON: {{"conflict": true/false, "reason": "...", "severity": "low/medium/high"}}
    """
    
    response = llm.call(prompt)
    result = parse_json(response)
    
    if result and result.get("conflict"):
        return ConflictResult(
            conflict=True,
            reason=result["reason"],
            severity=result.get("severity", "medium")
        )
    
    return None

@dataclass
class ConflictResult:
    conflict: bool
    reason: str
    severity: str  # low, medium, high
```

### Step 4: Resolution

```python
def resolve(candidate: EnrichedAtom, target: EnrichedAtom, conflict: Optional[ConflictResult]) -> str:
    """Resolve merge or conflict."""
    
    if conflict and conflict.conflict:
        # Conflict: use LLM to decide
        action = resolve_conflict(candidate, target, conflict)
    else:
        # No conflict: merge
        action = "merge"
    
    return action

def resolve_conflict(candidate: EnrichedAtom, target: EnrichedAtom, conflict: ConflictResult) -> str:
    """Use LLM to resolve conflict."""
    
    prompt = f"""
    These two decisions CONFLICT:
    
    Decision 1: {candidate.title}
    Rationale: {candidate.rationale[:200]}
    
    Decision 2: {target.title}
    Rationale: {target.rationale[:200]}
    
    Conflict: {conflict.reason}
    Severity: {conflict.severity}
    
    How should we resolve this?
    - "merge": Combine both into one consolidated decision
    - "separate": Keep both, they're different aspects
    - "supersede": One replaces the other
    
    Return JSON: {{"action": "merge/separate/supersede", "reason": "..."}}
    """
    
    response = llm.call(prompt)
    result = parse_json(response)
    
    return result.get("action", "separate")
```

### Step 5: Execution

```python
def execute_merge(candidate: EnrichedAtom, target: EnrichedAtom, action: str):
    """Execute dedup: supersede weaker, keep stronger."""
    
    # Choose stronger proposal
    if candidate.confidence >= target.confidence:
        stronger, weaker = candidate, target
    else:
        stronger, weaker = target, candidate
    
    # Mark weaker as superseded
    self.memory.semantic.update_decision(
        weaker.fid,
        {"status": "superseded", "superseded_by": stronger.fid}
    )
    
    # Update stronger's supersedes list
    self.memory.semantic.update_decision(
        stronger.fid,
        {"supersedes": stronger.supersedes + [weaker.fid]}
    )
```

## [S8] Promotion Engine

### Phase Transition Rules

```python
class PromotionEngine:
    """Promote decisions through phases."""
    
    def __init__(self, memory: MemoryProtocol, config: PromotionConfig):
        self.memory = memory
        self.config = config
    
    def promote(self, decision: EnrichedAtom) -> Optional[DecisionPhase]:
        """Check if decision should be promoted."""
        
        current = decision.phase
        
        if current == DecisionPhase.PATTERN:
            return self.check_pattern_to_emergent(decision)
        elif current == DecisionPhase.EMERGENT:
            return self.check_emergent_to_canonical(decision)
        
        return None  # Already CANONICAL
    
    def check_pattern_to_emergent(self, decision: EnrichedAtom) -> Optional[DecisionPhase]:
        """Check if PATTERN → EMERGENT."""
        
        # Standard path
        if (decision.total_evidence_count >= self.config.pattern_to_emergent.evidence and
            decision.coverage >= self.config.pattern_to_emergent.coverage):
            return DecisionPhase.EMERGENT
        
        # Alternative path
        if (decision.confidence >= self.config.pattern_to_emergent.alt_confidence and
            decision.total_evidence_count >= self.config.pattern_to_emergent.alt_evidence):
            return DecisionPhase.EMERGENT
        
        return None
    
    def check_emergent_to_canonical(self, decision: EnrichedAtom) -> Optional[DecisionPhase]:
        """Check if EMERGENT → CANONICAL."""
        
        # Standard path
        if (decision.total_evidence_count >= self.config.emergent_to_canonical.evidence and
            decision.stability_score >= self.config.emergent_to_canonical.stability and
            decision.coverage >= self.config.emergent_to_canonical.coverage):
            return DecisionPhase.CANONICAL
        
        # Alternative path
        if (decision.confidence >= self.config.emergent_to_canonical.alt_confidence and
            decision.stability_score >= self.config.emergent_to_canonical.stability):
            return DecisionPhase.CANONICAL
        
        return None
    
    def run(self) -> PromotionResult:
        """Run promotion on all decisions."""
        
        result = PromotionResult()
        decisions = self.memory.semantic.get_all_active()
        
        for decision in decisions:
            new_phase = self.promote(decision)
            
            if new_phase:
                # Validate phase inheritance
                validated_phase = self.validate_phase(decision, new_phase)
                
                if validated_phase != decision.phase:
                    self.memory.semantic.update_decision(
                        decision.fid,
                        {"phase": validated_phase}
                    )
                    result.promoted += 1
        
        return result
    
    def validate_phase(self, decision: EnrichedAtom, target_phase: DecisionPhase) -> DecisionPhase:
        """Validate phase against minimum thresholds."""
        
        if target_phase == DecisionPhase.EMERGENT:
            if decision.total_evidence_count < 5 or decision.stability_score < 0.5:
                return DecisionPhase.PATTERN
        
        elif target_phase == DecisionPhase.CANONICAL:
            if decision.total_evidence_count < 15 or decision.stability_score < 0.7:
                return DecisionPhase.EMERGENT
        
        return target_phase
```

### Phase Inheritance (during consolidation)

```python
def inherit_phase(source_decisions: List[EnrichedAtom]) -> DecisionPhase:
    """Consolidated decision gets max phase from sources."""
    
    phases = [d.phase for d in source_decisions]
    
    tier_map = {
        DecisionPhase.PATTERN: 1,
        DecisionPhase.EMERGENT: 2,
        DecisionPhase.CANONICAL: 3
    }
    
    max_phase = max(phases, key=lambda p: tier_map[p])
    
    # Validate against minimum thresholds
    total_evidence = sum(d.total_evidence_count for d in source_decisions)
    avg_stability = sum(d.stability_score for d in source_decisions) / len(source_decisions)
    
    if max_phase == DecisionPhase.CANONICAL:
        if total_evidence < 15 or avg_stability < 0.7:
            return DecisionPhase.EMERGENT
    
    if max_phase == DecisionPhase.EMERGENT:
        if total_evidence < 5 or avg_stability < 0.5:
            return DecisionPhase.PATTERN
    
    return max_phase
```

### Promotion Configuration

```python
class PromotionConfig(BaseModel):
    """Configuration for promotion engine."""
    
    pattern_to_emergent: dict = {
        "evidence": 50,
        "coverage": 0.2,
        "alt_evidence": 30,
        "alt_confidence": 0.5
    }
    
    emergent_to_canonical: dict = {
        "evidence": 150,
        "stability": 0.7,
        "coverage": 0.3,
        "alt_confidence": 0.75
    }
```

## [S8.5] Phase Transitions

### Key Change
**Phase = maturity level** (PATTERN → EMERGENT → CANONICAL). No separate proposal/decision.

### Phase Transition Rules

```python
def check_promotion(item: KnowledgeItem) -> Optional[Phase]:
    """Check if item should be promoted to next phase."""
    
    if item.phase == Phase.PATTERN:
        return check_pattern_to_emergent(item)
    elif item.phase == Phase.EMERGENT:
        return check_emergent_to_canonical(item)
    return None

def check_pattern_to_emergent(item: KnowledgeItem) -> Optional[Phase]:
    """Check PATTERN → EMERGENT."""
    # Standard path
    if item.total_evidence_count >= 20 and item.coverage >= 0.2:
        return Phase.EMERGENT
    
    # Alternative path
    if item.confidence >= 0.5 and item.total_evidence_count >= 10:
        return Phase.EMERGENT
    
    return None

def check_emergent_to_canonical(item: KnowledgeItem) -> Optional[Phase]:
    """Check EMERGENT → CANONICAL."""
    # Standard path
    if (item.total_evidence_count >= 50 and
        item.stability_score >= 0.5 and
        item.coverage >= 0.2):
        return Phase.CANONICAL
    
    # Alternative path
    if item.confidence >= 0.75 and item.stability_score >= 0.5:
        return Phase.CANONICAL
    
    return None
```

### Phase Thresholds

| Transition | Standard Path | Alternative Path |
|------------|---------------|------------------|
| PATTERN → EMERGENT | evidence >= 20 AND coverage >= 0.2 | confidence >= 0.5 AND evidence >= 10 |
| EMERGENT → CANONICAL | evidence >= 50 AND stability >= 0.5 AND coverage >= 0.2 | confidence >= 0.75 AND stability >= 0.5 |

### Phase Characteristics

| Phase | Stability | Merge Threshold | Characteristics |
|-------|-----------|-----------------|-----------------|
| PATTERN | 0.0 | 0.5 | Raw knowledge, easy merge |
| EMERGENT | age + hits + evidence | 0.6 | Validated knowledge, medium merge |
| CANONICAL | age + hits + evidence | 0.7 | Mature knowledge, hard merge |

## [S9] Single Store (Semantic Only)

### Architecture

```
Agent DB (state.db) → post_llm hook → Enriched Atom → Semantic Store
                          │
                          └──→ Raw events stay in agent DB (not copied)
```

### Semantic Store (Proposals)

```python
class SemanticStore:
    """Stores proposals (enriched atoms) with metrics."""
    
    def save_proposal(self, atom: EnrichedAtom):
        """Save enriched atom as proposal."""
        
        # Save to SQLite
        self.meta.upsert(
            fid=atom.fid,
            title=atom.title,
            target=atom.target,
            content=atom.rationale,
            status="draft",
            kind="proposal",
            confidence=atom.confidence,
            stability_score=atom.stability_score,
            phase=atom.phase.value,
            vitality=atom.vitality.value,
            # ... other fields
        )
        
        # Commit to Git
        self.git.commit(
            file_path=f"proposals/{atom.fid}.md",
            content=render_proposal_md(atom),
            message=f"Add proposal: {atom.title}"
        )
```

### LLM Failure Handling

```python
def handle_llm_failure(self, raw_event: dict, error: str):
    """Handle LLM failure during enrichment."""
    
    # Raw event stays in agent DB (state.db)
    # No need to save to our store
    
    # Log error
    logger.error(f"LLM enrichment failed: {error}")
    
    # Will be retried in next cycle
```

## [S10] Configuration

### Full Config Schema

```python
class PipelineConfig(BaseModel):
    """Full pipeline configuration."""
    
    decay: DecayConfig = DecayConfig()
    merge: MergeConfig = MergeConfig()
    promotion: PromotionConfig = PromotionConfig()
    
    # Execution
    cycle_interval_seconds: int = 300  # 5 minutes
    max_merge_batch_size: int = 100
    max_decay_batch_size: int = 100

class DecayConfig(BaseModel):
    confidence_thresholds: dict = {"fast": 0.3, "medium": 0.7}
    decay_rates: dict = {"fast": 0.15, "medium": 0.05, "slow": 0.01}
    minimum_retention_days: int = 14
    minimum_evidence: int = 5
    dormant_to_delete_days: int = 7

class MergeConfig(BaseModel):
    similarity_threshold: float = 0.8
    minimum_confidence: float = 0.5
    minimum_stability: float = 0.3
    minimum_evidence: int = 5
    maximum_temporal_gap_days: int = 30
    enable_conflict_detection: bool = True

class PromotionConfig(BaseModel):
    pattern_to_emergent: dict = {"evidence": 50, "coverage": 0.2, "alt_evidence": 30, "alt_confidence": 0.5}
    emergent_to_canonical: dict = {"evidence": 150, "stability": 0.7, "coverage": 0.3, "alt_confidence": 0.75}
```

### Config File

```json
{
  "pipeline": {
    "cycle_interval_seconds": 300,
    "decay": {
      "confidence_thresholds": {"fast": 0.3, "medium": 0.7},
      "decay_rates": {"fast": 0.15, "medium": 0.05, "slow": 0.01},
      "minimum_retention_days": 14,
      "minimum_evidence": 5
    },
    "merge": {
      "similarity_threshold": 0.8,
      "minimum_confidence": 0.5,
      "minimum_stability": 0.3,
      "minimum_evidence": 5,
      "maximum_temporal_gap_days": 30
    },
    "promotion": {
      "pattern_to_emergent": {"evidence": 50, "coverage": 0.2},
      "emergent_to_canonical": {"evidence": 150, "stability": 0.7, "coverage": 0.3}
    }
  }
}
```

## [S11] Error Handling

### LLM Failure

```python
def handle_llm_failure(raw_event: dict, error: Exception):
    """Handle LLM failure during enrichment."""
    
    logger.error(f"LLM enrichment failed: {error}")
    
    # Save raw data to episodic
    episodic_store.save_fallback(raw_event, str(error))
    
    # Don't create enriched atom
    # Will be processed in next cycle
    
    # Alert if repeated failures
    if consecutive_failures > 3:
        alert_user(f"LLM enrichment failing repeatedly: {error}")
```

### Merge Failure

```python
def handle_merge_failure(candidate: EnrichedAtom, target: EnrichedAtom, error: Exception):
    """Handle merge failure."""
    
    logger.error(f"Merge failed for {candidate.fid} + {target.fid}: {error}")
    
    # Keep both decisions separate
    # Don't mark as merged
    
    # Reset merge status
    memory.semantic.update_decision(candidate.fid, {"merge_status": None})
    memory.semantic.update_decision(target.fid, {"merge_status": None})
    
    # Will retry in next cycle
```

### Database Failure

```python
def handle_db_error(operation: str, error: Exception):
    """Handle database error."""
    
    logger.error(f"Database error during {operation}: {error}")
    
    # Try to recover
    try:
        db.reconnect()
        logger.info("Database reconnected")
    except:
        logger.critical("Database recovery failed")
        raise
```

## [S11.5] Integrity Rules (I1-I5)

### I1: Required Fields Check

```python
REQUIRED_FIELDS = ["fid", "title", "target", "profile", "rationale", "phase", "vitality"]

def check_required_fields(item: KnowledgeItem):
    """Validate required fields exist."""
    for field in REQUIRED_FIELDS:
        if not hasattr(item, field) or getattr(item, field) is None:
            raise IntegrityViolation(f"Missing required field: {field}", fid=item.fid)
```

### I2: Target Uniqueness

```python
def check_target_uniqueness(items: List[KnowledgeItem]):
    """No two active items with same target in same profile."""
    active_items = [i for i in items if i.vitality == Vitality.ACTIVE and not i.superseded_by]
    
    seen = {}
    for item in active_items:
        key = (item.target, item.profile)
        if key in seen:
            raise IntegrityViolation(
                f"Multiple active items with target '{item.target}' in profile '{item.profile}'",
                fid=item.fid
            )
        seen[key] = item.fid
```

### I3: Reference Integrity

```python
def check_references(items: List[KnowledgeItem]):
    """No dangling references."""
    all_fids = {item.fid for item in items}
    
    for item in items:
        # Check superseded_by
        if item.superseded_by and item.superseded_by not in all_fids:
            raise IntegrityViolation(
                f"Dangling reference: superseded_by = {item.superseded_by}",
                fid=item.fid
            )
        
        # Check supersedes
        for fid in item.supersedes:
            if fid not in all_fids:
                raise IntegrityViolation(
                    f"Dangling reference: supersedes = {fid}",
                    fid=item.fid
                )
```

### I4: Cycle Detection

```python
def check_cycles(items: List[KnowledgeItem]):
    """No circular references."""
    item_map = {item.fid: item for item in items}
    visited = set()
    
    def dfs(fid: str, path: set):
        if fid in path:
            raise IntegrityViolation(f"Cycle detected: {fid}")
        if fid in visited:
            return
        visited.add(fid)
        path.add(fid)
        
        item = item_map.get(fid)
        if item:
            for supersedes_fid in item.supersedes:
                dfs(supersedes_fid, path.copy())
    
    for item in items:
        dfs(item.fid, set())
```

### I5: Valid Status Transitions

```python
VALID_PHASE_TRANSITIONS = {
    (Phase.PATTERN, Phase.EMERGENT): True,   # Promotion
    (Phase.EMERGENT, Phase.CANONICAL): True,  # Promotion
}

VALID_VITALITY_TRANSITIONS = {
    (Vitality.ACTIVE, Vitality.DECAYING): True,    # Decay
    (Vitality.DECAYING, Vitality.ACTIVE): True,     # Re-activation
    (Vitality.DECAYING, Vitality.DORMANT): True,    # Decay
    (Vitality.DORMANT, Vitality.ACTIVE): True,      # Re-activation via merge
}

def check_status_transitions(old_item: KnowledgeItem, new_item: KnowledgeItem):
    """Validate status transitions."""
    # Phase transition
    if old_item.phase != new_item.phase:
        if (old_item.phase, new_item.phase) not in VALID_PHASE_TRANSITIONS:
            raise IntegrityViolation(
                f"Invalid phase transition: {old_item.phase} → {new_item.phase}",
                fid=new_item.fid
            )
    
    # Vitality transition
    if old_item.vitality != new_item.vitality:
        if (old_item.vitality, new_item.vitality) not in VALID_VITALITY_TRANSITIONS:
            raise IntegrityViolation(
                f"Invalid vitality transition: {old_item.vitality} → {new_item.vitality}",
                fid=new_item.fid
            )
```

## [S12] Migration Plan

### Phase 1: Core Pipeline (Week 1)

1. Implement EnrichedAtom schema
2. Update post_llm hook to return N atoms
3. Implement sequential pipeline (decay → merge → promote)
4. Add metrics gates to merge
5. Implement confidence-based decay

### Phase 2: Integration (Week 2)

1. Update context injection to use new metrics
2. Update search to use new metrics
3. Remove episodic store code
4. Remove reflection engine code

### Phase 3: Cleanup (Week 3)

1. Remove old merge (without gates)
2. Remove old decay (without confidence-based)
3. Remove old reflection engine
4. Update tests

### Data Migration

**Clean Start:** No migration of old data. Start fresh.

```python
def clean_start():
    """Clean start with new schema."""
    
    # Clear old data
    semantic_store.clear_all()
    
    # Remove episodic store
    remove_episodic_store()
    
    # Start fresh
    logger.info("Clean start: old data archived, new schema ready")
```

## [S13] Testing Strategy

### Unit Tests

```python
# Test metrics calculation
def test_confidence_calculation():
    """Confidence = log1p(hit_count) / 2.3"""
    proposal = EnrichedAtom(hit_count=10)
    confidence = calculate_confidence(proposal)
    assert confidence == 1.0  # Saturated at 10 hits

def test_confidence_zero_hits():
    """Confidence = 0 when no hits"""
    proposal = EnrichedAtom(hit_count=0)
    confidence = calculate_confidence(proposal)
    assert confidence == 0.0

def test_stability_calculation():
    """Stability = variance-based when evidence >= 2"""
    proposal = EnrichedAtom(total_evidence_count=5, lifetime_days=14)
    stability = calculate_stability(proposal)
    assert 0.0 <= stability <= 1.0

def test_stability_new_proposal():
    """Stability = 0 for new proposals (evidence < 2)"""
    proposal = EnrichedAtom(total_evidence_count=1)
    stability = calculate_stability(proposal)
    assert stability == 0.0

def test_decay_formula():
    """Decay rate depends on confidence"""
    proposal = EnrichedAtom(confidence=0.8, last_seen=datetime.now() - timedelta(days=14))
    new_confidence = calculate_decay(proposal)
    assert new_confidence < 0.8

def test_merge_gate():
    """Merge gate checks confidence, stability, evidence"""
    candidate = EnrichedAtom(confidence=0.7, stability_score=0.5, total_evidence_count=10)
    target = EnrichedAtom(confidence=0.6, stability_score=0.4, total_evidence_count=8)
    assert should_merge(candidate, target) == True

def test_proposal_to_decision():
    """Proposal becomes decision when evidence >= 50 AND confidence >= 0.7"""
    proposal = EnrichedAtom(total_evidence_count=50, confidence=0.7)
    assert check_proposal_to_decision(proposal) == True
```

### Integration Tests

```python
def test_full_pipeline():
    # Create test proposals
    proposals = create_test_proposals(100)
    
    # Run pipeline
    pipeline = LifecyclePipeline(memory, config)
    result = pipeline.run()
    
    # Verify
    assert result.decay.deleted > 0
    assert result.merge.merged > 0
    assert result.promote.promoted >= 0

def test_no_episodic_store():
    """Verify no episodic store is used"""
    # Create enriched atom
    atom = create_enriched_atom(raw_event)
    
    # Save to semantic store only
    semantic_store.save_proposal(atom)
    
    # Verify episodic store not used
    assert not episodic_store.exists()
        atom = create_enriched_atom(raw_event)
        
        # Verify fallback
        assert episodic_store.get_fallback(raw_event["event_id"]) is not None
```

### Performance Tests

```python
def test_1000_decisions():
    # Create 1000 decisions
    decisions = create_test_decisions(1000)
    
    # Run pipeline
    start = time.time()
    pipeline.run()
    elapsed = time.time() - start
    
    assert elapsed < 300  # 5 minutes

def test_memory_usage():
    # Monitor memory
    process = psutil.Process()
    start_memory = process.memory_info().rss
    
    pipeline.run()
    
    end_memory = process.memory_info().rss
    assert (end_memory - start_memory) < 500 * 1024 * 1024  # 500MB
```

## [S14] Success Criteria

1. **Clean start**: No old data processed, metrics trustworthy from day 1
2. **Decay-first**: Weak proposals removed before merge
3. **Dedup only**: Merge supersedes weaker, keeps stronger (no consolidation)
4. **Minimum retention**: New proposals protected for 14 days
5. **Phase preservation**: CANONICAL never downgraded to PATTERN
6. **No episodic store**: Only semantic store (proposals with metrics)
7. **Performance**: Pipeline completes within 5-minute cycle
8. **Metrics accuracy**: Confidence (hit_count), stability (variance) reflect true quality
9. **Proposal → Decision**: evidence >= 50 AND confidence >= 0.7

## [S15] Open Questions

1. **LLM Prompt Optimization**: How to phrase enrichment prompt for best results?
2. **Similarity Threshold**: Is 0.8 optimal? Should it be configurable per phase?
3. **Decay Rates**: Are 0.01/0.05/0.15 rates optimal? Need tuning.
4. **Promotion Thresholds**: Are 50/150 evidence thresholds realistic?
5. **Hit Count Saturation**: Is 10 hits the right saturation point for confidence?
