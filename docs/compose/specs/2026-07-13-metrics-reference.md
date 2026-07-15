# LedgerMind Metrics Reference

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/lifecycle-pipeline-redesign.md)

## Overview

This document describes all metrics used in the LedgerMind lifecycle pipeline. Each metric is defined with:
- **Purpose**: What this metric measures
- **Calculation**: How it's computed
- **Range**: Valid values
- **Update triggers**: When this metric changes
- **Influences**: What decisions this metric affects

---

## [M1] Confidence (0.0 - 1.0)

### Purpose
How often this proposal was used (injected into context). Higher = more reliable.

### Calculation
```python
confidence = min(1.0, log1p(hit_count) / 2.3)
```

### Scales
- 0 hits → 0.0
- 1 hit → 0.30
- 10 hits → 1.0 (maximum)
- 100 hits → 1.0 (maximum)

### Logic
More injections = more reliable. Saturates at 10 injections.

### Update Triggers
- Hit recorded (search/inject)

### Influences
- **Decay rate**: Low confidence → fast decay
- **Merge gate**: Confidence < 0.5 → skip merge
- **Proposal → Decision**: Confidence > 0.7 required
- **Vitality transitions**: Confidence < 0.9 → DECAYING

---

## [M2] Stability Score (0.0 - 1.0)

### Purpose
Measures how consistent evidence is over time. Higher = more consistent.

### Calculation
```python
if total_evidence_count < 2:
    stability = 0.0

elif total_evidence_count >= 2:
    intervals = [days between consecutive reinforcements]
    variance = variance(intervals)
    delta_stability = max(0.0, 1.0 - (variance / (lifetime_days + 1.0)))
    age_factor = min(1.0, lifetime_days / 7.0)
    stability = delta_stability * (0.5 + 0.5 × age_factor)
```

### Interpretation
- High stability: Evidence arrives at regular intervals
- Low stability: Evidence arrives sporadically
- Age factor: New decisions can't have high stability (need 7+ days)

### Update Triggers
- Pipeline tick (recalculation)
- New evidence added (interval changes)

### Influences
- **Confidence**: 40% weight
- **Phase promotion**: Stability >= 0.7 required for CANONICAL
- **Merge gate**: Stability < 0.3 → skip merge

---

## [M3] Total Evidence Count

### Purpose
Recursive count of merged proposals.

### Calculation
```python
def count_evidence(proposal):
    """Recursively count all merged proposals."""
    count = len(proposal.supersedes)
    for fid in proposal.supersedes:
        merged = get_proposal(fid)
        if merged:
            count += count_evidence(merged)
    return count
```

### Logic
More merges = more confirmations of this knowledge.

### Update Triggers
- Proposal merges with another proposal

### Influences
- **Phase promotion**: evidence >= 50 for EMERGENT, >= 150 for CANONICAL
- **Proposal → Decision**: evidence >= 50 required
- **Merge gate**: evidence < 5 → skip merge

---

## [M4] Hit Count

### Purpose
Number of times this decision was used (searched, injected into context).

### Calculation
```python
hit_count += 1  # Each time decision is retrieved/used
```

### Update Triggers
- Vector search returns this decision
- Decision injected into LLM context
- Manual retrieval

### Influences
- **Confidence**: Usage component (20% weight)
- **Utility**: usage_bonus = min(0.4, log1p(hit_count) / 10.0)

---

## [M5] Last Hit At

### Purpose
Timestamp of most recent usage.

### Calculation
```python
last_hit_at = datetime.now()  # Each time decision is used
```

### Update Triggers
- Vector search returns this decision
- Decision injected into LLM context

### Influences
- **Vitality**: last_hit > 30 days → DECAYING
- **Vitality re-activation**: last_hit < 7 days → ACTIVE
- **Utility**: recency penalty if last_hit > 7 days

---

## [M6] Coverage (0.0 - 1.0)

### Purpose
What fraction of the observation window this decision has been seen.

### Calculation
```python
coverage = lifetime_days / observation_window_days  (default: 30 days)
```

### Interpretation
- 0.0: Just created (0 days)
- 0.5: Seen for 15 days
- 1.0: Seen for 30+ days

### Update Triggers
- Pipeline tick (recalculation)

### Influences
- **Phase promotion**: coverage >= 0.2 for EMERGENT, >= 0.3 for CANONICAL

---

## [M7] Estimated Utility (0.0 - 1.0)

### Purpose
How useful this knowledge is expected to be.

### Calculation
```python
utility = stability × 0.3 + confidence × 0.5 + coverage × 0.2
```

### Update Triggers
- Pipeline tick (recalculation)
- Hit recorded
- Evidence added

### Influences
- **Context injection**: Higher utility → higher rank
- **Search ranking**: Higher utility → higher relevance

---

## [M8] Phase (PATTERN → EMERGENT → CANONICAL)

### Purpose
Maturity level of knowledge.

### Values
- **PATTERN**: Raw hypothesis, just created
- **EMERGENT**: Validated, has evidence
- **CANONICAL**: Fully mature, authoritative

### Promotion Rules

#### PATTERN → EMERGENT
```python
# Standard path
if evidence >= 50 AND coverage >= 0.2:
    promote()

# Alternative path
if confidence >= 0.5 AND evidence >= 30:
    promote()
```

#### EMERGENT → CANONICAL
```python
# Standard path
if evidence >= 150 AND stability >= 0.7 AND coverage >= 0.3:
    promote()

# Alternative path
if confidence >= 0.75 AND stability >= 0.7:
    promote()
```

### Update Triggers
- Pipeline tick (promotion check)
- Evidence added

### Influences
- **Merge gate**: Same phase required for merge
- **Context injection**: Higher phase → higher priority

---

## [M9] Vitality (ACTIVE → DECAYING → DORMANT)

### Purpose
Whether this knowledge is still relevant.

### Values
- **ACTIVE**: Currently relevant, recently used
- **DECAYING**: Losing relevance, not used recently
- **DORMANT**: May be obsolete, very low confidence

### Transition Rules

#### ACTIVE → DECAYING
```python
if confidence < 0.9 OR last_hit > 30 days:
    vitality = DECAYING
```

#### DECAYING → ACTIVE (re-activation)
```python
if last_hit < 7 days:
    vitality = ACTIVE
```

#### DECAYING → DORMANT
```python
if confidence < 0.2:
    vitality = DORMANT
```

#### DORMANT → DELETE
```python
if confidence < 0.1 AND days_dormant > 7:
    delete()
```

### Update Triggers
- Pipeline tick (vitality check)
- Hit recorded
- Confidence change

### Influences
- **Decay rate**: DORMANT → faster decay
- **Merge gate**: DORMANT → skip merge
- **Deletion**: DORMANT + low confidence → delete

---

## [M10] Lifetime Days

### Purpose
How long this knowledge has existed.

### Calculation
```python
lifetime_days = (last_seen - first_seen).total_seconds() / 86400
```

### Update Triggers
- Pipeline tick (recalculation)

### Influences
- **Coverage**: coverage = lifetime_days / 30
- **Stability**: age_factor = min(1.0, lifetime_days / 7.0)

---

## [M11] First Seen / Last Seen

### Purpose
Temporal boundaries of this knowledge.

### Calculation
```python
first_seen = min(reinforcement_dates)
last_seen = max(reinforcement_dates)
```

### Update Triggers
- Creation: first_seen = now, last_seen = now
- New evidence: first_seen/last_seen updated
- Hit: last_seen updated

### Influences
- **Lifetime**: lifetime_days = last_seen - first_seen
- **Stability**: intervals between reinforcements

---

## Relationships Between Metrics

```
                    ┌─────────────┐
                    │   Evidence   │
                    │    Count     │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐
        │Confidence│  │ Stability│  │ Coverage │
        │  (40%)   │  │  (40%)  │  │         │
        └────┬────┘  └────┬────┘  └────┬────┘
             │            │            │
             ▼            ▼            ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐
        │  Decay   │  │  Phase  │  │  Phase  │
        │  Rate    │  │Promotion│  │Promotion│
        └─────────┘  └─────────┘  └─────────┘

        ┌─────────┐
        │Hit Count│
        └────┬────┘
             │
             ▼
        ┌─────────┐
        │Confidence│
        │  (20%)   │
        └────┬────┘
             │
             ▼
        ┌─────────┐
        │  Decay   │
        │  Rate    │
        └─────────┘
```

---

## Metric Dependencies

| Metric | Depends On | Used By |
|--------|------------|---------|
| Confidence | Hit Count | Decay, Merge, Vitality, Decision |
| Stability | Evidence intervals, Lifetime | Phase, Merge |
| Evidence Count | Recursive merge count | Phase, Proposal → Decision, Merge |
| Hit Count | Usage | Confidence, Utility |
| Last Hit At | Usage | Vitality, Utility |
| Coverage | Lifetime | Phase |
| Utility | Stability, Evidence, Hits, Last Hit | Search ranking, Context injection |
| Phase | Evidence, Stability, Coverage | — |
| Vitality | Confidence, Last Hit | Decay, Merge, Deletion |

---

## Decision Thresholds Summary

| Transition | Required Metrics |
|------------|------------------|
| Proposal → Decision | confidence > 0.7 AND evidence >= 50 |
| PATTERN → EMERGENT | evidence >= 50 OR (confidence >= 0.5 AND evidence >= 30) |
| EMERGENT → CANONICAL | evidence >= 150 AND stability >= 0.7 AND coverage >= 0.3 |
| ACTIVE → DECAYING | confidence < 0.5 OR last_hit > 30 days |
| DECAYING → DORMANT | confidence < 0.2 |
| DORMANT → DELETE | confidence < 0.1 AND days_dormant > 7 |
| Skip Merge | confidence < 0.5 OR stability < 0.3 OR evidence < 5 |
| Minimum Retention | evidence < 5 AND days_since_creation < 14 |
