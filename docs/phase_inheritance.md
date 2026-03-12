# Наследование фаз при слиянии гипотез

## Архитектурное решение

При консолидации нескольких гипотез в одно решение, **фаза результирующего решения определяется на основе максимальной фазы исходных гипотез с валидацией по метрикам**.

## Принцип работы

### 1. Определение максимальной фазы

Система определяет максимальную фазу среди всех исходных гипотез:
```
PATTERN < EMERGENT < CANONICAL
```

### 2. Валидация метриками

Максимальная фаза **понижается** если метрики не дотягивают до пороговых значений:

| Фаза | Min evidence_count | Min stability_score |
|------|-------------------|---------------------|
| **PATTERN** | 0 | 0.0 |
| **EMERGENT** | 5 | 0.5 |
| **CANONICAL** | 15 | 0.7 |

### 3. Алгоритм

```python
def _inherit_phase_with_validation(source_phases, total_evidence_count, stability_score):
    # 1. Найти максимальную фазу
    max_phase = max(source_phases)
    
    # 2. Понизить фазу если метрики не дотягивают
    for phase in [CANONICAL, EMERGENT, PATTERN]:
        if max_phase >= phase:
            if (evidence >= MIN_EVIDENCE[phase] and 
                stability >= MIN_STABILITY[phase]):
                return phase
    
    return PATTERN
```

## Примеры

### Пример 1: Недостаточно evidence
```
Исходные фазы: [PATTERN, EMERGENT]
total_evidence_count: 3  (< 5 для EMERGENT)
stability_score: 0.6     (≥ 0.5 для EMERGENT)

Результат: PATTERN  (понижено из-за недостатка evidence)
```

### Пример 2: Достаточно метрик
```
Исходные фазы: [PATTERN, EMERGENT]
total_evidence_count: 10  (≥ 5 для EMERGENT)
stability_score: 0.6      (≥ 0.5 для EMERGENT)

Результат: EMERGENT  (подтверждено)
```

### Пример 3: CANONICAL с низкими метриками
```
Исходные фазы: [EMERGENT, CANONICAL]
total_evidence_count: 10  (< 15 для CANONICAL)
stability_score: 0.8      (≥ 0.7 для CANONICAL)

Результат: EMERGENT  (понижено из-за недостатка evidence)
```

### Пример 4: CANONICAL с достаточными метриками
```
Исходные фазы: [EMERGENT, CANONICAL]
total_evidence_count: 20  (≥ 15 для CANONICAL)
stability_score: 0.8      (≥ 0.7 для CANONICAL)

Результат: CANONICAL  (подтверждено)
```

## Реализация

### Файлы

- `src/ledgermind/core/reasoning/enrichment/facade.py` — `_inherit_phase_with_validation()`
- `src/ledgermind/core/api/services/decision_command.py` — `supersede_decision(phase=...)`

### Тесты

- `tests/core/reasoning/enrichment/test_phase_inheritance.py` — 10 тестов на все сценарии

## Обоснование

### Почему максимальная фаза?

Консолидация объединяет знания из нескольких источников. Если хотя бы одна гипотеза достигла зрелости (EMERGENT/CANONICAL), это означает что знание прошло достаточную проверку.

### Почему валидация?

Простое наследование максимальной фазы может привести к завышению статуса. Валидация по `evidence_count` и `stability_score` гарантирует что результирующее решение действительно заслуживает эту фазу.

### Почему такие пороги?

- **EMERGENT (5 evidence, 0.5 stability)**: Знание набрало достаточно подтверждений и показывает стабильность
- **CANONICAL (15 evidence, 0.7 stability)**: Знание прошло обширную проверку и высокостабильно

## Влияние на другие компоненты

### accept_proposal()

При принятии proposal фаза наследуется:
```python
proposal (phase=EMERGENT) → decision (phase=EMERGENT)
```

### supersede_decision()

Поддерживает явное указание фазы:
```python
memory.supersede_decision(
    title="...", 
    phase=DecisionPhase.EMERGENT  # ← Явное указание
)
```
