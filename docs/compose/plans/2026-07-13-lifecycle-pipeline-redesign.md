# Lifecycle Pipeline Redesign Implementation Plan

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/lifecycle-pipeline-redesign.md)

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the lifecycle pipeline with enriched-first architecture, confidence-based metrics, and sequential Merge → Decay → Promote flow.

**Architecture:** Single semantic store with knowledge items. No episodic store. Clean start (old data archived). Sequential pipeline: Merge → Decay → Promote.

**Tech Stack:** Python 3.10+, Pydantic, SQLite, Git, LLM (OpenAI-compatible)

## Global Constraints

- API key in `.env` file (chmod 600), NOT in config.json
- Worker simplified for Hermes — no standalone process management
- Single semantic store (Git + SQLite)
- No episodic store (raw events stay in agent DB)
- Clean start (old data archived, not processed)
- Sequential pipeline: Merge → Decay → Promote (not parallel)
- Integrity rules I1-I5 preserved

---

## Task 1: Knowledge Item Schema

**Covers:** [S3]

**Files:**
- Create: `src/ledgermind/core/core/knowledge.py`
- Test: `tests/test_knowledge.py`

**Interfaces:**
- Consumes: None
- Produces: `KnowledgeItem` class

- [ ] **Step 1: Write the failing test**

```python
# tests/test_knowledge.py
import pytest
from datetime import datetime
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality

def test_knowledge_item_creation():
    item = KnowledgeItem(
        fid="pattern_20260713_120000_000000_abc123",
        title="Test Knowledge",
        target="core/test",
        profile="hermes",
        rationale="Test rationale",
        compressive_rationale="Test summary",
        strengths=["strength1"],
        objections=["objection1"],
        consequences=["consequence1"],
    )
    assert item.fid == "pattern_20260713_120000_000000_abc123"
    assert item.phase == Phase.PATTERN
    assert item.vitality == Vitality.ACTIVE
    assert item.confidence == 0.0
    assert item.stability_score == 0.0
    assert item.total_evidence_count == 0

def test_knowledge_item_confidence_calculation():
    item = KnowledgeItem(
        fid="pattern_test_abc",
        title="Test",
        target="test",
        profile="hermes",
        rationale="test",
        compressive_rationale="test",
        strengths=[],
        objections=[],
        consequences=[],
        hit_count=10,
    )
    assert item.confidence == 1.0  # Saturated at 10 hits
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_knowledge.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'ledgermind.core.core.knowledge'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/ledgermind/core/core/knowledge.py
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
        import math
        return min(1.0, math.log1p(self.hit_count) / 2.3)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_knowledge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ledgermind/core/core/knowledge.py tests/test_knowledge.py
git commit -m "feat: add KnowledgeItem schema with phases"
```

---

## Task 2: Metrics Calculator

**Covers:** [S3, M1-M11]

**Files:**
- Create: `src/ledgermind/core/reasoning/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Consumes: `KnowledgeItem` from Task 1
- Produces: `calculate_confidence()`, `calculate_stability()`, `calculate_utility()`, `calculate_coverage()`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics.py
import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.knowledge import KnowledgeItem, Phase
from ledgermind.core.reasoning.metrics import (
    calculate_confidence,
    calculate_stability,
    calculate_utility,
    calculate_coverage,
    count_evidence,
)

def test_confidence_calculation():
    assert calculate_confidence(0) == 0.0
    assert calculate_confidence(1) == pytest.approx(0.30, abs=0.01)
    assert calculate_confidence(10) == 1.0
    assert calculate_confidence(100) == 1.0

def test_coverage_calculation():
    first_seen = datetime.now() - timedelta(days=15)
    last_seen = datetime.now()
    assert calculate_coverage(first_seen, last_seen) == pytest.approx(0.5, abs=0.01)

def test_utility_calculation():
    utility = calculate_utility(
        stability_score=0.5,
        confidence=0.7,
        coverage=0.5,
    )
    assert utility == pytest.approx(0.5 * 0.3 + 0.7 * 0.5 + 0.5 * 0.2, abs=0.01)

def test_count_evidence():
    # Mock knowledge items
    items = {
        "A": KnowledgeItem(
            fid="pattern_A_abc", title="A", target="t", profile="p", rationale="r",
            compressive_rationale="cr", strengths=[], objections=[], consequences=[],
            supersedes=["pattern_B_def", "pattern_C_ghi"],
        ),
        "B": KnowledgeItem(
            fid="pattern_B_def", title="B", target="t", profile="p", rationale="r",
            compressive_rationale="cr", strengths=[], objections=[], consequences=[],
            supersedes=[],
        ),
        "C": KnowledgeItem(
            fid="pattern_C_ghi", title="C", target="t", profile="p", rationale="r",
            compressive_rationale="cr", strengths=[], objections=[], consequences=[],
            supersedes=[],
        ),
    }
    assert count_evidence(items["A"], items) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_metrics.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# src/ledgermind/core/reasoning/metrics.py
import math
from datetime import datetime
from typing import Dict, List, Optional

def calculate_confidence(hit_count: int) -> float:
    """Calculate confidence from hit_count."""
    return min(1.0, math.log1p(hit_count) / 2.3)

def calculate_stability(
    total_evidence_count: int,
    intervals: List[float],
    lifetime_days: float,
) -> float:
    """Calculate stability score from evidence intervals."""
    if total_evidence_count < 2:
        return 0.0
    
    if len(intervals) < 2:
        return 0.0
    
    import statistics
    variance = statistics.variance(intervals)
    delta_stability = max(0.0, 1.0 - (variance / (lifetime_days + 1.0)))
    age_factor = min(1.0, lifetime_days / 7.0)
    
    return delta_stability * (0.5 + 0.5 * age_factor)

def calculate_coverage(first_seen: datetime, last_seen: datetime) -> float:
    """Calculate coverage from temporal boundaries."""
    observation_window_days = 30.0
    lifetime_days = (last_seen - first_seen).total_seconds() / 86400
    return min(1.0, lifetime_days / observation_window_days)

def calculate_utility(
    stability_score: float,
    confidence: float,
    coverage: float,
) -> float:
    """Calculate utility from metrics."""
    return min(1.0, max(0.0, stability_score * 0.3 + confidence * 0.5 + coverage * 0.2))

def count_evidence(item_fid: str, items: Dict[str, any]) -> int:
    """Count evidence using accumulative merge count."""
    item = items.get(item_fid)
    if not item:
        return 0
    
    count = len(item.supersedes)
    for fid in item.supersedes:
        if fid in items:
            count += count_evidence(fid, items)
    
    return count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_metrics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ledgermind/core/reasoning/metrics.py tests/test_metrics.py
git commit -m "feat: add metrics calculator with confidence, stability, utility, coverage"
```

---

## Task 3: Decay Engine

**Covers:** [S6]

**Files:**
- Create: `src/ledgermind/core/reasoning/decay.py`
- Test: `tests/test_decay.py`

**Interfaces:**
- Consumes: `KnowledgeItem` from Task 1, `calculate_confidence()` from Task 2
- Produces: `DecayEngine` class

- [ ] **Step 1: Write the failing test**

```python
# tests/test_decay.py
import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality
from ledgermind.core.reasoning.decay import DecayEngine

def test_decay_rate_calculation():
    engine = DecayEngine()
    
    # Fast decay (confidence < 0.3)
    assert engine.get_decay_rate(0.2) == 0.15
    
    # Medium decay (confidence 0.3-0.7)
    assert engine.get_decay_rate(0.5) == 0.05
    
    # Slow decay (confidence > 0.7)
    assert engine.get_decay_rate(0.8) == 0.01

def test_decay_application():
    engine = DecayEngine()
    item = KnowledgeItem(
        fid="pattern_test_abc",
        title="test",
        target="test",
        profile="hermes",
        rationale="test",
        compressive_rationale="test",
        strengths=[],
        objections=[],
        consequences=[],
        confidence=0.8,
        last_seen=datetime.now() - timedelta(days=14),
    )
    
    new_confidence = engine.apply_decay(item)
    assert new_confidence < 0.8

def test_vitality_transitions():
    engine = DecayEngine()
    
    # ACTIVE -> DECAYING
    item = KnowledgeItem(
        fid="pattern_test_abc",
        title="test",
        target="test",
        profile="hermes",
        rationale="test",
        compressive_rationale="test",
        strengths=[],
        objections=[],
        consequences=[],
        confidence=0.5,
        last_hit_at=datetime.now() - timedelta(days=40),
    )
    assert engine.calculate_vitality(item) == Vitality.DECAYING
    
    # DECAYING -> ACTIVE
    item.last_hit_at = datetime.now() - timedelta(days=5)
    assert engine.calculate_vitality(item) == Vitality.ACTIVE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_decay.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# src/ledgermind/core/reasoning/decay.py
from datetime import datetime
from ledgermind.core.core.knowledge import KnowledgeItem, Vitality

class DecayEngine:
    """Confidence-based decay engine."""
    
    def __init__(
        self,
        fast_threshold: float = 0.3,
        medium_threshold: float = 0.7,
        fast_rate: float = 0.15,
        medium_rate: float = 0.05,
        slow_rate: float = 0.01,
        minimum_retention_days: int = 14,
        minimum_evidence: int = 5,
    ):
        self.fast_threshold = fast_threshold
        self.medium_threshold = medium_threshold
        self.fast_rate = fast_rate
        self.medium_rate = medium_rate
        self.slow_rate = slow_rate
        self.minimum_retention_days = minimum_retention_days
        self.minimum_evidence = minimum_evidence
    
    def get_decay_rate(self, confidence: float) -> float:
        """Get decay rate based on confidence."""
        if confidence < self.fast_threshold:
            return self.fast_rate
        elif confidence < self.medium_threshold:
            return self.medium_rate
        else:
            return self.slow_rate
    
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
        from ledgermind.core.core.knowledge import Phase
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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_decay.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ledgermind/core/reasoning/decay.py tests/test_decay.py
git commit -m "feat: add confidence-based decay engine"
```

---

## Task 4: Multi-Criteria Merge Engine

**Covers:** [S7]

**Files:**
- Create: `src/ledgermind/core/reasoning/merge.py`
- Test: `tests/test_merge.py`

**Interfaces:**
- Consumes: `KnowledgeItem` from Task 1
- Produces: `MergeEngine` class

- [ ] **Step 1: Write the failing test**

```python
# tests/test_merge.py
import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality
from ledgermind.core.reasoning.merge import MergeEngine

def test_similarity_scoring():
    engine = MergeEngine()
    
    # Same target, same phase, same profile
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="ui/hero", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN,
    )
    target = KnowledgeItem(
        fid="pattern_B_def", title="B", target="ui/hero", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN,
    )
    similarity = engine.calculate_similarity(candidate, target)
    assert similarity > 0.6  # Same target, same phase

def test_profile_gate():
    engine = MergeEngine()
    
    # Different profiles → SKIP
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN,
    )
    target = KnowledgeItem(
        fid="pattern_B_def", title="B", target="t", profile="openclaw", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN,
    )
    assert engine.should_merge(candidate, target) == False

def test_session_boost():
    engine = MergeEngine()
    
    # Same session + high similarity → boost
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="ui/hero", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, session_id="session_123",
    )
    target = KnowledgeItem(
        fid="pattern_B_def", title="B", target="ui/hero", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, session_id="session_123",
    )
    similarity = engine.calculate_similarity(candidate, target)
    # Should have session boost because similarity > 0.6
    assert similarity > 0.8

def test_quality_assessment():
    engine = MergeEngine()
    
    item = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        confidence=0.7, stability_score=0.5, total_evidence_count=5,
        first_seen=datetime.now() - timedelta(days=15),
    )
    quality = engine.assess_quality(item)
    assert 0.3 < quality < 0.8  # Reasonable quality

def test_merge_decision_pattern():
    engine = MergeEngine()
    
    # PATTERN: easy merge (threshold 0.5)
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, confidence=0.3, stability_score=0.0,
        first_seen=datetime.now(),
    )
    target = KnowledgeItem(
        fid="pattern_B_def", title="B", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, confidence=0.4, stability_score=0.0,
        first_seen=datetime.now(),
    )
    assert engine.should_merge(candidate, target) == True

def test_merge_decision_canonical():
    engine = MergeEngine()
    
    # CANONICAL: hard merge (threshold 0.7)
    candidate = KnowledgeItem(
        fid="canonical_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.CANONICAL, confidence=0.6, stability_score=0.5,
        first_seen=datetime.now() - timedelta(days=30),
    )
    target = KnowledgeItem(
        fid="canonical_B_def", title="B", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.CANONICAL, confidence=0.7, stability_score=0.6,
        first_seen=datetime.now() - timedelta(days=30),
    )
    assert engine.should_merge(candidate, target) == True

def test_merge_dormant_revival():
    engine = MergeEngine()
    
    # DORMANT: revive through merge (threshold 0.5)
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, confidence=0.3, vitality=Vitality.ACTIVE,
        first_seen=datetime.now(),
    )
    target = KnowledgeItem(
        fid="pattern_B_def", title="B", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, confidence=0.2, vitality=Vitality.DORMANT,
        first_seen=datetime.now(),
    )
    assert engine.should_merge(candidate, target) == True

def test_supersede_with_phase_inheritance():
    engine = MergeEngine()
    
    candidate = KnowledgeItem(
        fid="pattern_A_abc", title="A", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.PATTERN, confidence=0.7,
    )
    target = KnowledgeItem(
        fid="emergent_B_def", title="B", target="t", profile="hermes", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        phase=Phase.EMERGENT, confidence=0.5,
    )
    
    stronger, weaker = engine.choose_stronger(candidate, target)
    engine.execute_supersede(stronger, weaker)
    
    # Phase should be inherited from stronger (EMERGENT)
    assert stronger.phase == Phase.EMERGENT
    assert weaker.superseded_by == "pattern_A_abc"
    assert stronger.total_evidence_count == 1  # 0 + 0 + 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_merge.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# src/ledgermind/core/reasoning/merge.py
import math
from datetime import datetime
from typing import Tuple
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality

class MergeEngine:
    """Multi-criteria merge engine with phase-aware thresholds."""
    
    def __init__(self):
        # Phase-aware thresholds
        self.thresholds = {
            Phase.PATTERN: 0.5,
            Phase.EMERGENT: 0.6,
            Phase.CANONICAL: 0.7,
        }
        self.dormant_threshold = 0.5
    
    def calculate_similarity(self, candidate: KnowledgeItem, target: KnowledgeItem) -> float:
        """Calculate comprehensive similarity score."""
        # Semantic similarity (simplified: same target = 1.0, else 0.5)
        target_score = 1.0 if candidate.target == target.target else 0.5
        
        # Phase compatibility
        phase_score = 1.0 if candidate.phase == target.phase else 0.5
        
        # Temporal proximity
        days_diff = abs((candidate.first_seen - target.first_seen).days)
        temporal_score = max(0.0, 1.0 - (days_diff / 30.0))
        
        # Weighted average
        similarity = (
            target_score * 0.4 +
            phase_score * 0.3 +
            temporal_score * 0.3
        )
        
        return similarity
    
    def assess_quality(self, item: KnowledgeItem) -> float:
        """Assess quality of knowledge item."""
        # Confidence (hit_count based)
        confidence_score = item.confidence
        
        # Stability (phase-aware)
        if item.phase == Phase.PATTERN:
            stability_score = 0.0  # Not a factor for PATTERN
        else:
            age_days = (datetime.now() - item.first_seen).days
            age_factor = min(1.0, age_days / 30.0)
            hit_factor = min(1.0, item.hit_count / 10.0)
            evidence_factor = min(1.0, item.total_evidence_count / 10.0)
            stability_score = age_factor * 0.3 + hit_factor * 0.3 + evidence_factor * 0.4
        
        # Evidence
        evidence_score = min(1.0, item.total_evidence_count / 10.0)
        
        # Age
        age_days = (datetime.now() - item.first_seen).days
        age_score = min(1.0, age_days / 30.0)
        
        # Weighted quality
        quality = (
            confidence_score * 0.3 +
            stability_score * 0.3 +
            evidence_score * 0.2 +
            age_score * 0.2
        )
        
        return quality
    
    def get_threshold(self, phase: Phase) -> float:
        """Get merge threshold for phase."""
        return self.thresholds.get(phase, 0.6)
    
    def should_merge(self, candidate: KnowledgeItem, target: KnowledgeItem) -> bool:
        """Multi-criteria merge decision."""
        # Profile gate: different profiles → SKIP
        if candidate.profile != target.profile:
            return False
        
        # Calculate similarity
        similarity = self.calculate_similarity(candidate, target)
        
        # Calculate quality
        candidate_quality = self.assess_quality(candidate)
        target_quality = self.assess_quality(target)
        avg_quality = (candidate_quality + target_quality) / 2
        
        # Calculate base merge score
        base_score = similarity * 0.5 + avg_quality * 0.5
        
        # Session boost: only if similarity > 0.6
        if (candidate.session_id == target.session_id and 
            candidate.session_id and
            similarity > 0.6):
            session_boost = similarity * 0.15
        else:
            session_boost = 0
        
        merge_score = min(1.0, base_score + session_boost)
        
        # Get threshold based on higher phase
        phase_order = {Phase.PATTERN: 1, Phase.EMERGENT: 2, Phase.CANONICAL: 3}
        higher_phase = max(candidate.phase, target.phase, key=lambda p: phase_order[p])
        threshold = self.get_threshold(higher_phase)
        
        # DORMANT: lower threshold (revive through merge)
        if candidate.vitality == Vitality.DORMANT or \
           target.vitality == Vitality.DORMANT:
            threshold = self.dormant_threshold
        
        return merge_score >= threshold
    
    def choose_stronger(self, candidate: KnowledgeItem, target: KnowledgeItem) -> Tuple[KnowledgeItem, KnowledgeItem]:
        """Choose stronger knowledge item for merge."""
        if candidate.confidence >= target.confidence:
            return candidate, target
        else:
            return target, candidate
    
    def execute_supersede(self, stronger: KnowledgeItem, weaker: KnowledgeItem) -> None:
        """Execute supersede: mark weaker as superseded."""
        weaker.superseded_by = stronger.fid
        stronger.supersedes.append(weaker.fid)
        
        # Update evidence count (accumulative)
        stronger.total_evidence_count = (
            stronger.total_evidence_count + 
            weaker.total_evidence_count + 1
        )
        
        # Update phase (take higher)
        phase_order = {Phase.PATTERN: 1, Phase.EMERGENT: 2, Phase.CANONICAL: 3}
        if phase_order[weaker.phase] > phase_order[stronger.phase]:
            stronger.phase = weaker.phase
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_merge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ledgermind/core/reasoning/merge.py tests/test_merge.py
git commit -m "feat: add multi-criteria merge engine with phase-aware thresholds"
```

---

## Task 5: Promotion Engine

**Covers:** [S8]

**Files:**
- Create: `src/ledgermind/core/reasoning/promotion.py`
- Test: `tests/test_promotion.py`

**Interfaces:**
- Consumes: `KnowledgeItem` from Task 1
- Produces: `PromotionEngine` class

- [ ] **Step 1: Write the failing test**

```python
# tests/test_promotion.py
import pytest
from ledgermind.core.core.knowledge import KnowledgeItem, Phase
from ledgermind.core.reasoning.promotion import PromotionEngine

def test_pattern_to_emergent():
    engine = PromotionEngine()
    
    # Standard path
    item = KnowledgeItem(
        fid="pattern_test_abc", title="test", target="t", profile="p", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        total_evidence_count=20, coverage=0.2,
    )
    assert engine.check_promotion(item) == Phase.EMERGENT
    
    # Alternative path
    item2 = KnowledgeItem(
        fid="pattern_test2_def", title="test", target="t", profile="p", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        confidence=0.5, total_evidence_count=10,
    )
    assert engine.check_promotion(item2) == Phase.EMERGENT

def test_emergent_to_canonical():
    engine = PromotionEngine()
    
    item = KnowledgeItem(
        fid="emergent_test_abc", title="test", target="t", profile="p", rationale="r",
        compressive_rationale="cr", strengths=[], objections=[], consequences=[],
        total_evidence_count=50, stability_score=0.5, coverage=0.2,
        phase=Phase.EMERGENT,
    )
    assert engine.check_promotion(item) == Phase.CANONICAL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_promotion.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# src/ledgermind/core/reasoning/promotion.py
from typing import Optional
from ledgermind.core.core.knowledge import KnowledgeItem, Phase

class PromotionEngine:
    """Phase promotion engine."""
    
    def __init__(
        self,
        pattern_to_emergent_evidence: int = 20,
        pattern_to_emergent_coverage: float = 0.2,
        pattern_to_emergent_alt_evidence: int = 10,
        pattern_to_emergent_alt_confidence: float = 0.5,
        emergent_to_canonical_evidence: int = 50,
        emergent_to_canonical_stability: float = 0.5,
        emergent_to_canonical_coverage: float = 0.2,
        emergent_to_canonical_alt_confidence: float = 0.75,
    ):
        self.pattern_to_emergent_evidence = pattern_to_emergent_evidence
        self.pattern_to_emergent_coverage = pattern_to_emergent_coverage
        self.pattern_to_emergent_alt_evidence = pattern_to_emergent_alt_evidence
        self.pattern_to_emergent_alt_confidence = pattern_to_emergent_alt_confidence
        self.emergent_to_canonical_evidence = emergent_to_canonical_evidence
        self.emergent_to_canonical_stability = emergent_to_canonical_stability
        self.emergent_to_canonical_coverage = emergent_to_canonical_coverage
        self.emergent_to_canonical_alt_confidence = emergent_to_canonical_alt_confidence
    
    def check_promotion(self, item: KnowledgeItem) -> Optional[Phase]:
        """Check if item should be promoted."""
        if item.phase == Phase.PATTERN:
            return self._check_pattern_to_emergent(item)
        elif item.phase == Phase.EMERGENT:
            return self._check_emergent_to_canonical(item)
        return None
    
    def _check_pattern_to_emergent(self, item: KnowledgeItem) -> Optional[Phase]:
        """Check PATTERN -> EMERGENT."""
        # Standard path
        if (item.total_evidence_count >= self.pattern_to_emergent_evidence and
            item.coverage >= self.pattern_to_emergent_coverage):
            return Phase.EMERGENT
        
        # Alternative path
        if (item.confidence >= self.pattern_to_emergent_alt_confidence and
            item.total_evidence_count >= self.pattern_to_emergent_alt_evidence):
            return Phase.EMERGENT
        
        return None
    
    def _check_emergent_to_canonical(self, item: KnowledgeItem) -> Optional[Phase]:
        """Check EMERGENT -> CANONICAL."""
        # Standard path
        if (item.total_evidence_count >= self.emergent_to_canonical_evidence and
            item.stability_score >= self.emergent_to_canonical_stability and
            item.coverage >= self.emergent_to_canonical_coverage):
            return Phase.CANONICAL
        
        # Alternative path
        if (item.confidence >= self.emergent_to_canonical_alt_confidence and
            item.stability_score >= self.emergent_to_canonical_stability):
            return Phase.CANONICAL
        
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_promotion.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ledgermind/core/reasoning/promotion.py tests/test_promotion.py
git commit -m "feat: add phase promotion engine"
```

---

## Task 6: Pipeline Orchestrator

**Covers:** [S5]

**Files:**
- Create: `src/ledgermind/core/reasoning/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `DecayEngine` from Task 3, `MergeEngine` from Task 4, `PromotionEngine` from Task 5
- Produces: `LifecyclePipeline` class

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
import pytest
from ledgermind.core.reasoning.pipeline import LifecyclePipeline

def test_pipeline_creation():
    pipeline = LifecyclePipeline()
    assert pipeline.decay_engine is not None
    assert pipeline.merge_engine is not None
    assert pipeline.promotion_engine is not None

def test_pipeline_run():
    pipeline = LifecyclePipeline()
    result = pipeline.run([])
    assert result.decay_count >= 0
    assert result.merge_count >= 0
    assert result.promote_count >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# src/ledgermind/core/reasoning/pipeline.py
from dataclasses import dataclass
from typing import List
from ledgermind.core.core.knowledge import KnowledgeItem
from ledgermind.core.reasoning.decay import DecayEngine
from ledgermind.core.reasoning.merge import MergeEngine
from ledgermind.core.reasoning.promotion import PromotionEngine

@dataclass
class PipelineResult:
    merge_count: int
    decay_count: int
    promote_count: int

class LifecyclePipeline:
    """Sequential pipeline: Merge -> Decay -> Promote."""
    
    def __init__(self):
        self.decay_engine = DecayEngine()
        self.merge_engine = MergeEngine()
        self.promotion_engine = PromotionEngine()
    
    def run(self, items: List[KnowledgeItem]) -> PipelineResult:
        """Run pipeline on knowledge items."""
        merge_count = 0
        decay_count = 0
        promote_count = 0
        
        # Step 1: Merge (first - claim candidates)
        claimed = set()  # Track claimed proposals
        for i, candidate in enumerate(items):
            if candidate.fid in claimed:
                continue
            
            for j, target in enumerate(items[i+1:], i+1):
                if target.fid in claimed:
                    continue
                
                if self.merge_engine.should_merge(candidate, target):
                    # Claim both candidates
                    claimed.add(candidate.fid)
                    claimed.add(target.fid)
                    
                    # Execute merge
                    stronger, weaker = self.merge_engine.choose_stronger(candidate, target)
                    self.merge_engine.execute_supersede(stronger, weaker)
                    merge_count += 1
        
        # Step 2: Decay (second - after merge)
        for item in items:
            new_confidence = self.decay_engine.apply_decay(item)
            if new_confidence != item.confidence:
                item.confidence = new_confidence
                decay_count += 1
            
            new_vitality = self.decay_engine.calculate_vitality(item)
            if new_vitality != item.vitality:
                item.vitality = new_vitality
        
        # Step 3: Promote (last)
        for item in items:
            new_phase = self.promotion_engine.check_promotion(item)
            if new_phase:
                item.phase = new_phase
                promote_count += 1
        
        return PipelineResult(
            merge_count=merge_count,
            decay_count=decay_count,
            promote_count=promote_count,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ledgermind/core/reasoning/pipeline.py tests/test_pipeline.py
git commit -m "feat: add sequential lifecycle pipeline orchestrator"
```

---

## Task 7: Integration Tests

**Covers:** [S13]

**Files:**
- Create: `tests/test_integration.py`

**Interfaces:**
- Consumes: All previous tasks
- Produces: Integration test suite

- [ ] **Step 1: Write the failing test**

```python
# tests/test_integration.py
import pytest
from datetime import datetime, timedelta
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality
from ledgermind.core.reasoning.pipeline import LifecyclePipeline

def test_full_pipeline():
    pipeline = LifecyclePipeline()
    
    # Create test knowledge items
    items = [
        KnowledgeItem(
            fid=f"pattern_item_{i}_abc",
            title=f"Knowledge {i}",
            target=f"target/{i}",
            profile="hermes",
            rationale=f"Rationale {i}",
            compressive_rationale=f"Summary {i}",
            strengths=[],
            objections=[],
            consequences=[],
            confidence=i * 0.1,
            total_evidence_count=i * 5,
        )
        for i in range(10)
    ]
    
    result = pipeline.run(items)
    
    assert result.decay_count >= 0
    assert result.merge_count >= 0
    assert result.promote_count >= 0

def test_phase_transitions():
    from ledgermind.core.reasoning.promotion import PromotionEngine
    
    engine = PromotionEngine()
    
    # PATTERN -> EMERGENT
    item = KnowledgeItem(
        fid="pattern_test_abc",
        title="Test",
        target="test",
        profile="hermes",
        rationale="test",
        compressive_rationale="test",
        strengths=[],
        objections=[],
        consequences=[],
        total_evidence_count=20,
        coverage=0.2,
    )
    assert engine.check_promotion(item) == Phase.EMERGENT
    
    # EMERGENT -> CANONICAL
    item2 = KnowledgeItem(
        fid="emergent_test_def",
        title="Test",
        target="test",
        profile="hermes",
        rationale="test",
        compressive_rationale="test",
        strengths=[],
        objections=[],
        consequences=[],
        total_evidence_count=50,
        stability_score=0.5,
        coverage=0.2,
        phase=Phase.EMERGENT,
    )
    assert engine.check_promotion(item2) == Phase.CANONICAL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py -v`
Expected: FAIL (if any dependency missing)

- [ ] **Step 3: Run test to verify it passes**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration tests for lifecycle pipeline"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Knowledge Item Schema | knowledge.py, test_knowledge.py |
| 2 | Metrics Calculator | metrics.py, test_metrics.py |
| 3 | Decay Engine | decay.py, test_decay.py |
| 4 | Multi-Criteria Merge Engine | merge.py, test_merge.py |
| 5 | Promotion Engine | promotion.py, test_promotion.py |
| 6 | Pipeline Orchestrator | pipeline.py, test_pipeline.py |
| 7 | Integration Tests | test_integration.py |

**Total:** 7 tasks, 14 files (7 source + 7 test)
