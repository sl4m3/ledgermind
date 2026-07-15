# Multi-Criteria Merge System Design

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/lifecycle-pipeline-redesign.md)

## [S1] Problem

Current merge system is too simple (similarity threshold only). Need smart merge that:
- Deduplicates similar proposals
- Consolidates knowledge
- Protects mature knowledge (CANONICAL)
- Revives DORMANT proposals through merge

## [S2] Solution Overview

Multi-criteria merge with:
1. Similarity Scoring (semantic, target, phase, temporal)
2. Quality Assessment (confidence, stability, evidence, age)
3. Phase-Aware Thresholds (PATTERN easy, CANONICAL hard)
4. DORMANT Revival through merge

## [S3] Similarity Scoring

### Formula
```python
similarity = (
    semantic_score × 0.4 +    # Vector similarity
    target_score × 0.2 +      # Same target path
    phase_score × 0.2 +       # Phase compatibility
    temporal_score × 0.2      # Created close in time
)
```

### Components

**Semantic Score (40%):**
- Vector similarity between proposals
- Range: 0.0 (different) - 1.0 (identical)

**Target Score (20%):**
- 1.0 if same target path
- 0.0 if different target path

**Phase Score (20%):**
- 1.0 if same phase
- 0.5 if different phase (still possible to merge)

**Temporal Score (20%):**
- 1.0 if created same day
- 0.0 if created 30+ days apart
- Formula: `max(0.0, 1.0 - (days_diff / 30.0))`

## [S4] Quality Assessment

### Formula
```python
quality = (
    confidence × 0.3 +    # Hit count based
    stability × 0.3 +     # Age + hits + evidence
    evidence × 0.2 +      # Merge count
    age × 0.2             # Days since creation
)
```

### Components

**Confidence (30%):**
- Formula: `min(1.0, log1p(hit_count) / 2.3)`
- Range: 0.0 (never used) - 1.0 (used 10+ times)

**Stability (30%):**
- Phase-aware formula:
  - PATTERN: 0.0 (not a factor)
  - EMERGENT: `age × 0.3 + hits × 0.3 + evidence × 0.4`
  - CANONICAL: `age × 0.3 + hits × 0.3 + evidence × 0.4`

**Evidence (20%):**
- Formula: `min(1.0, total_evidence_count / 10.0)`
- Range: 0.0 (no merges) - 1.0 (10+ merges)

**Age (20%):**
- Formula: `min(1.0, age_days / 30.0)`
- Range: 0.0 (just created) - 1.0 (30+ days old)

## [S5] Merge Decision

### Formula
```python
merge_score = similarity × 0.5 + quality × 0.5
```

### Thresholds

| Phase | Threshold | Behavior |
|-------|-----------|----------|
| PATTERN | 0.5 | Easy merge |
| EMERGENT | 0.6 | Medium merge |
| CANONICAL | 0.7 | Hard merge |
| DORMANT | 0.5 | Revive through merge |

### Decision Logic

```python
def should_merge(candidate, target):
    similarity = calculate_similarity(candidate, target)
    quality = (assess_quality(candidate) + assess_quality(target)) / 2
    merge_score = similarity × 0.5 + quality × 0.5
    
    # Get threshold based on higher phase
    threshold = get_threshold(max(candidate.phase, target.phase))
    
    # DORMANT: lower threshold
    if candidate.vitality == DORMANT or target.vitality == DORMANT:
        threshold = 0.5
    
    return merge_score >= threshold
```

## [S6] Merge Execution

### Steps

1. **Choose stronger:** higher confidence wins
2. **Supersede weaker:** weaker.superseded_by = stronger.fid
3. **Update evidence:** stronger.evidence += weaker.evidence + 1
4. **Update phase:** take higher phase

### Phase Inheritance

```
PATTERN + PATTERN → PATTERN
PATTERN + EMERGENT → EMERGENT (higher)
PATTERN + CANONICAL → SKIP (CANONICAL protected)
EMERGENT + EMERGENT → EMERGENT
EMERGENT + CANONICAL → SKIP (CANONICAL protected)
CANONICAL + CANONICAL → CANONICAL
ANY + DORMANT → MERGE (revive, keep higher phase)
```

## [S7] Examples

### Example 1: PATTERN + PATTERN
```
Candidate: "Fix Hero bug", confidence=0.3, stability=0.0
Target: "Refactor Hero", confidence=0.4, stability=0.0

Similarity: 0.75
Quality: 0.35
Merge score: 0.75 × 0.5 + 0.35 × 0.5 = 0.55
Threshold: 0.5
Result: MERGE ✓
```

### Example 2: EMERGENT + EMERGENT
```
Candidate: "Optimize DB", confidence=0.5, stability=0.4
Target: "DB performance", confidence=0.6, stability=0.5

Similarity: 0.8
Quality: 0.5
Merge score: 0.8 × 0.5 + 0.5 × 0.5 = 0.65
Threshold: 0.6
Result: MERGE ✓
```

### Example 3: CANONICAL + CANONICAL
```
Candidate: "Auth system", confidence=0.7, stability=0.6
Target: "Authentication", confidence=0.8, stability=0.7

Similarity: 0.9
Quality: 0.75
Merge score: 0.9 × 0.5 + 0.75 × 0.5 = 0.825
Threshold: 0.7
Result: MERGE ✓
```

### Example 4: PATTERN + CANONICAL
```
Candidate: "Fix bug", confidence=0.3, stability=0.0
Target: "Auth system", confidence=0.7, stability=0.6

Similarity: 0.8
Quality: 0.45
Merge score: 0.8 × 0.5 + 0.45 × 0.5 = 0.625
Threshold: SKIP (CANONICAL protected)
Result: SKIP ✗
```

### Example 5: ANY + DORMANT
```
Candidate: "Fix bug", confidence=0.3, stability=0.0
Target: "Old feature", confidence=0.1, vitality=DORMANT

Similarity: 0.7
Quality: 0.3
Merge score: 0.7 × 0.5 + 0.3 × 0.5 = 0.5
Threshold: 0.5 (DORMANT)
Result: MERGE ✓ (revive)
```

## [S8] Metrics Used

| Metric | Used in Merge | Purpose |
|--------|---------------|---------|
| Confidence | ✅ Yes | Quality assessment (30%) |
| Stability | ✅ Yes | Quality assessment (30%) |
| Evidence | ✅ Yes | Stability calculation (40%) |
| Hit Count | ✅ Yes | Confidence calculation |
| Last Hit At | ✅ Yes | Vitality transitions |
| Phase | ✅ Yes | Merge thresholds |
| Vitality | ✅ Yes | DORMANT check |
| Coverage | ❌ No | Phase promotion only |
| Utility | ❌ No | Search ranking only |
