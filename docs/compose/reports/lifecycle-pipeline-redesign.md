---
feature: lifecycle-pipeline-redesign
status: delivered
specs:
  - docs/compose/specs/2026-07-13-lifecycle-pipeline-redesign.md
  - docs/compose/specs/2026-07-13-metrics-reference.md
  - docs/compose/specs/2026-07-13-metrics-reference-ru.md
  - docs/compose/specs/2026-07-13-metrics-usage.md
  - docs/compose/specs/2026-07-13-merge-system-design.md
plans:
  - docs/compose/plans/2026-07-13-lifecycle-pipeline-redesign.md
branch: main
commits: 30ed580..db1fd6e
---

# Lifecycle Pipeline Redesign — Final Report

## What Was Built

Полностью переработан lifecycle pipeline для управления знаниями в LedgerMind. Новая архитектура заменяет систему "proposals + decisions" на единую модель "KnowledgeItem" с фазами зрелости (PATTERN → EMERGENT → CANONICAL).

**Ключевые изменения:**
- Единая схема KnowledgeItem вместо Proposal + Decision
- Sequential pipeline: Merge → Decay → Promote (вместо параллельного)
- Multi-criteria merge engine с profile gate, session boost, phase-aware thresholds
- Confidence-based decay с защитой от удаления merged proposals
- Integrity rules I1-I5 для защиты семантического хранилища

## Architecture

### Компоненты

```
src/ledgermind/core/
├── core/
│   └── knowledge.py          # KnowledgeItem schema (Phase, Vitality)
├── reasoning/
│   ├── metrics.py            # calculate_confidence, calculate_stability, calculate_utility, calculate_coverage, count_evidence
│   ├── decay.py              # NewDecayEngine (confidence-based decay)
│   ├── merge.py              # MergeEngine (multi-criteria merge)
│   ├── promotion.py          # PromotionEngine (PATTERN → EMERGENT → CANONICAL)
│   └── pipeline.py           # LifecyclePipeline (Merge → Decay → Promote)
```

### Data Flow

```
1. POST-LLM HOOK → N knowledge items (enriched atoms)
2. PIPELINE (каждые 5 минут):
   ├── MERGE: find similar items, claim candidates, execute supersede
   ├── DECAY: update confidence, vitality, delete DORMANT
   └── PROMOTE: advance phase (PATTERN → EMERGENT → CANONICAL)
```

### Design Decisions

1. **Единая схема KnowledgeItem** — Proposal и Decision объединены в одну схему. Фаза определяет зрелость, а не статус.

2. **Merge → Decay → Promote** — Merge выполняется первым, чтобы "зарезервировать" candidates до decay. Это предотвращает удаление proposals, которые должны быть смержены.

3. **Profile gate** — Items из разных профилей (hermes/openclaw) НЕ мержатся. Это обеспечивает изоляцию между workspace.

4. **Session boost** — Items из одной сессии получают boost к similarity (только если similarity > 0.6). Это учитывает контекст сессии.

5. **Phase-aware thresholds** — PATTERN merge легко (0.5), CANONICAL merge сложно (0.7). Это защищает зрелые знания от слияния с сырыми.

## Usage

### Создание KnowledgeItem

```python
from ledgermind.core.core.knowledge import KnowledgeItem, Phase, Vitality

item = KnowledgeItem(
    fid="pattern_20260713_143025_123456_abc123",
    title="Fix Hero component animation bug",
    target="ui/hero",
    profile="hermes",
    rationale="Fixed animation bug where badge expansion caused layout shift.",
    compressive_rationale="Hero component animation bug fixed.",
    strengths=["Better UX", "No layout shift"],
    objections=["CSS :has() not supported in older browsers"],
    consequences=["Improved user experience"],
)
```

### Запуск Pipeline

```python
from ledgermind.core.reasoning.pipeline import LifecyclePipeline

pipeline = LifecyclePipeline()
result = pipeline.run(items)

print(f"Merged: {result.merge_count}")
print(f"Decayed: {result.decay_count}")
print(f"Promoted: {result.promote_count}")
```

### Пороги

| Порог | Значение | Описание |
|-------|----------|----------|
| PATTERN merge | 0.5 | Лёгкий merge для сырых знаний |
| EMERGENT merge | 0.6 | Средний merge для проверенных знаний |
| CANONICAL merge | 0.7 | Сложный merge для зрелых знаний |
| DORMANT merge | 0.5 | Revive через merge |
| ACTIVE → DECAYING | confidence < 0.5 | Decay开始 |
| PATTERN → EMERGENT | evidence >= 20 | Promotion |
| EMERGENT → CANONICAL | evidence >= 50 | Promotion |

## Verification

**Все 25 тестов проходят:**

```
tests/test_knowledge.py: 2 tests ✓
tests/test_metrics.py: 4 tests ✓
tests/test_decay.py: 4 tests ✓
tests/test_merge.py: 8 tests ✓
tests/test_promotion.py: 3 tests ✓
tests/test_pipeline.py: 2 tests ✓
tests/test_integration.py: 2 tests ✓
```

**Тесты покрывают:**
- Создание KnowledgeItem
- Расчёт метрик (confidence, stability, utility, coverage)
- Decay engine (rates, vitality transitions, superseded protection)
- Merge engine (similarity, quality, profile gate, session boost, phase inheritance)
- Promotion engine (PATTERN → EMERGENT, EMERGENT → CANONICAL)
- Pipeline orchestrator (Merge → Decay → Promote)
- Integration tests (full pipeline, phase transitions)

## Journey Log

- [pivot] Initially planned Proposal + Decision schemas, but unified into KnowledgeItem after realizing phases already indicate maturity
- [lesson] Session boost must be conditional on similarity > 0.6 to prevent merging unrelated topics from same session
- [lesson] Decay must skip superseded items to prevent deleting proposals that were just merged
- [lesson] Profile gate is essential for isolating workspaces (hermes/openclaw)
- [lesson] Merge-first pipeline order prevents race conditions between merge and decay

## Source Materials

| File | Role | Notes |
|------|------|-------|
| `docs/compose/specs/2026-07-13-lifecycle-pipeline-redesign.md` | Main spec | Updated with KnowledgeItem schema |
| `docs/compose/specs/2026-07-13-metrics-reference.md` | Metrics reference (EN) | Updated thresholds |
| `docs/compose/specs/2026-07-13-metrics-reference-ru.md` | Metrics reference (RU) | Updated thresholds |
| `docs/compose/specs/2026-07-13-metrics-usage.md` | Metrics usage guide | Updated vitality threshold |
| `docs/compose/specs/2026-07-13-merge-system-design.md` | Merge system design | Multi-criteria merge |
| `docs/compose/plans/2026-07-13-lifecycle-pipeline-redesign.md` | Implementation plan | Complete |
