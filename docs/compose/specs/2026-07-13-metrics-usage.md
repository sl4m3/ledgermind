# Как метрики используются в LedgerMind

> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/lifecycle-pipeline-redesign.md)

## Обзор

Этот документ описывает как каждая метрика используется в пайплайне и на что она влияет.

---

## Confidence (hit_count based)

### Как считается
```python
confidence = min(1.0, log1p(hit_count) / 2.3)
```

### Где используется

| Место использования | Как влияет |
|---------------------|------------|
| **Decay rate** | confidence < 0.3 → быстрый decay (0.15/день) |
| **Decay rate** | confidence 0.3-0.7 → средний decay (0.05/день) |
| **Decay rate** | confidence > 0.7 → медленный decay (0.01/день) |
| **Merge gate** | confidence < 0.5 → пропустить merge |
| **Proposal → Decision** | confidence >= 0.7 обязательна |
| **Vitality** | confidence < 0.5 → ACTIVE → DECAYING |
| **Vitality** | confidence < 0.2 → DECAYING → DORMANT |

### Примеры

```
hit_count = 0:   confidence = 0.0 → быстрый decay, пропустить merge
hit_count = 1:   confidence = 0.30 → средний decay
hit_count = 5:   confidence = 0.73 → медленный decay, может стать decision
hit_count = 10:  confidence = 1.0 → максимально медленный decay
```

---

## Stability Score (variance-based)

### Как считается
```python
if total_evidence_count < 2:
    stability = 0.0
else:
    intervals = [дни между merge]
    variance = variance(intervals)
    stability = max(0.0, 1.0 - (variance / (lifetime + 1.0))) × age_factor
```

### Где используется

| Место использования | Как влияет |
|---------------------|------------|
| **Phase promotion** |稳定性 >= 0.7 обязательна для CANONICAL |
| **Merge gate** |稳定性 < 0.3 → пропустить merge |
| **Utility** |稳定性 × 0.3 в формуле utility |

### Примеры

```
stability = 0.0:  новый proposal, нельзя в CANONICAL, нельзя мержить
stability = 0.3:  можно мержить, но нельзя в CANONICAL
stability = 0.7:  можно в CANONICAL
stability = 1.0:  максимальная стабильность
```

---

## Total Evidence Count (accumulative merge count)

### Как считается
```python
# При merge A сливает B:
A.evidence_count = A.evidence_count + B.evidence_count + 1
```

### Где используется

| Место использования | Как влияет |
|---------------------|------------|
| **Phase promotion** | evidence >= 50 → EMERGENT |
| **Phase promotion** | evidence >= 150 → CANONICAL |
| **Proposal → Decision** | evidence >= 50 обязательна |
| **Merge gate** | evidence < 5 → пропустить merge |
| **Minimum retention** | evidence < 5 → защищено от decay (14 дней) |

### Примеры

```
evidence = 0:   новый proposal, защищён от decay 14 дней
evidence = 3:   защищён от decay, нельзя мержить
evidence = 10:  можно мержить
evidence = 50:  можно в EMERGENT
evidence = 150: можно в CANONICAL
```

---

## Hit Count

### Как считается
```python
hit_count += 1  # Каждый раз когда proposal используется
```

### Где используется

| Место использования | Как влияет |
|---------------------|------------|
| **Confidence** | hit_count → confidence = log1p(hit_count) / 2.3 |
| **Utility** | hit_count → bonus = min(0.4, log1p(hit_count) / 10.0) |

### Примеры

```
hit_count = 0:   confidence = 0.0, utility низкий
hit_count = 1:   confidence = 0.30
hit_count = 10:  confidence = 1.0 (максимум)
```

---

## Last Hit At

### Как считается
```python
last_hit_at = datetime.now()  # Каждый раз когда proposal используется
```

### Где используется

| Место использования | Как влияет |
|---------------------|------------|
| **Vitality** | last_hit > 30 дней → ACTIVE → DECAYING |
| **Vitality** | last_hit < 7 дней → DECAYING → ACTIVE (реактивация) |
| **Utility** | last_hit > 7 дней → recency penalty |

### Примеры

```
last_hit = сегодня:     vitality = ACTIVE, utility высокий
last_hit = 10 дней:     vitality = DECAYING, utility средний
last_hit = 40 дней:     vitality = DECAYING, utility низкий
last_hit = 60 дней:     vitality = DORMANT, может быть удалён
```

---

## Coverage

### Как считается
```python
coverage = lifetime_days / 30  # 30 дней observation window
```

### Где используется

| Место использования | Как влияет |
|---------------------|------------|
| **Phase promotion** | coverage >= 0.2 для EMERGENT |
| **Phase promotion** | coverage >= 0.3 для CANONICAL |
| **Utility** | coverage × 0.2 в формуле utility |

### Примеры

```
coverage = 0.0:  только создано (0 дней)
coverage = 0.5:  существует 15 дней
coverage = 1.0:  существует 30+ дней
```

---

## Utility

### Как считается
```python
utility = stability × 0.3 + confidence × 0.5 + coverage × 0.2
```

### Где используется

| Место использования | Как влияет |
|---------------------|------------|
| **Search ranking** | utility → relevance score |
| **Context injection** | utility → priority в контексте |

### Примеры

```
utility = 0.0:   низкий приоритет в поиске
utility = 0.5:   средний приоритет
utility = 1.0:   максимальный приоритет
```

---

## Phase (PATTERN → EMERGENT → CANONICAL)

### Как считается
```python
# PATTERN → EMERGENT
if evidence >= 50 OR (confidence >= 0.5 AND evidence >= 30):
    phase = EMERGENT

# EMERGENT → CANONICAL
if evidence >= 150 AND stability >= 0.7 AND coverage >= 0.3:
    phase = CANONICAL
```

### Где используется

| Место использования | Как влияет |
|---------------------|------------|
| **Merge gate** | Та же фаза обязательна для merge |
| **Context injection** | Высокая фаза → высокий приоритет |
| **Proposal → Decision** | CANONICAL phase не требуется, только evidence + confidence |

### Примеры

```
PATTERN:    сырая гипотеза, низкий приоритет
EMERGENT:   проверенная, средний приоритет
CANONICAL:  зрелая, высокий приоритет
```

---

## Vitality (ACTIVE → DECAYING → DORMANT)

### Как считается
```python
# ACTIVE → DECAYING
if confidence < 0.5 OR last_hit > 30 дней:
    vitality = DECAYING

# DECAYING → ACTIVE
if last_hit < 7 дней:
    vitality = ACTIVE

# DECAYING → DORMANT
if confidence < 0.2:
    vitality = DORMANT

# DORMANT → DELETE
if confidence < 0.1 AND days_dormant > 7:
    delete()
```

### Где используется

| Место использования | Как влияет |
|---------------------|------------|
| **Decay rate** | DORMANT → быстрый decay |
| **Merge gate** | DORMANT → пропустить merge |
| **Deletion** | DORMANT + low confidence → удалить |

### Примеры

```
ACTIVE:     актуально, используется
DECAYING:   теряет актуальность
DORMANT:    может быть устаревшим, готов к удалению
```

---

## Сводка: что на что влияет

```
┌─────────────────────────────────────────────────────────────┐
│                    METRICS FLOW                              │
└─────────────────────────────────────────────────────────────┘

hit_count ─────────→ confidence ─────────→ decay rate
                         │                      │
                         │                      ▼
                         │               vitality transitions
                         │
                         ├──→ merge gate
                         │
                         └──→ proposal → decision

stability ─────────→ phase promotion
    │
    └──→ merge gate

evidence ──────────→ phase promotion
    │
    ├──→ merge gate
    │
    └──→ minimum retention

coverage ──────────→ phase promotion
    │
    └──→ utility

last_hit ──────────→ vitality
    │
    └──→ utility

utility ───────────→ search ranking
                     context injection
```

---

## Ключевые связи

| Метрика | Влияет на | Зависит от |
|---------|-----------|------------|
| Confidence | Decay, Merge, Vitality, Decision | Hit Count |
| Stability | Phase, Merge, Utility | Evidence intervals, Lifetime |
| Evidence | Phase, Merge, Retention | Merge count |
| Hit Count | Confidence, Utility | Usage |
| Last Hit | Vitality, Utility | Usage |
| Coverage | Phase, Utility | Lifetime |
| Utility | Search, Context | Stability, Confidence, Coverage |
| Phase | Merge, Context | Evidence, Stability, Coverage |
| Vitality | Decay, Merge, Deletion | Confidence, Last Hit |
