# agent-memory-core v1.3.0-evolution

Универсальный модуль долгосрочной памяти для ИИ-агентов с гарантированной целостностью.

## Гарантии целостности

- **ACID на уровне файлов**: Файловые блокировки предотвращают Race Condition, а Git обеспечивает атомарность и версионирование.
- **Моногенные связи**: Каждая ссылка (`supersedes` / `superseded_by`) проверяется в обе стороны при каждом запуске. Битая ссылка = System Halt.
- **Бессмертные доказательства**: Эпизоды (Episodic Memory), послужившие основой для семантических решений, защищены от удаления Decay Engine (I6 Invariant).
- **Полная воспроизводимость**: Состояние системы (DAG решений) полностью определяется Markdown-файлами в репозитории.
- **Recovery Engine**: Автоматическое обнаружение и фиксация (stage/commit) файлов, оставшихся после системных сбоев.

## Установка
```bash
pip install agent-memory-core
```

## Быстрый старт
```python
from api.memory import Memory

memory = Memory(storage_path="./my_agent_memory")

# Запись решения
memory.record_decision(
    title="Use PostgreSQL",
    target="database",
    rationale="Need ACID and scaling"
)

# Эволюция знаний
memory.supersede_decision(
    title="Use PostgreSQL with Citus",
    target="database",
    rationale="Sharding required",
    old_decision_ids=["decision_2026...md"]
)
```

## Архитектура
- **Semantic Store**: Markdown + YAML Frontmatter, хранится в Git.
- **Episodic Store**: SQLite, append-only лог событий.
- **Conflict Engine**: Детектор логических противоречий.
- **Decay Engine**: Управление жизненным циклом (Archive -> Prune).
