# ADR 0003: Core владеет knowledge.db

- **Статус:** accepted
- **Дата:** 2026-08-03

## Решение

Закрытый Rust Core владеет каталогом данных Core и базой SQLite `knowledge.db`.
Core открывает только эту базу и применяет все SQL-миграции самостоятельно.

SQL разрешён только в инфраструктурном crate хранения Rust Core. Domain и application crates не содержат SQL.

Local никогда не открывает `knowledge.db`; Integrations не открывает ни одну LedgerMind-базу.
Local хранит свои данные в отдельной `rounds.db`.

## Следствия

- KnowledgeItem, ревизии, evidence, фазы, идемпотентность Core и внутренние ModelTask принадлежат Core.
- Local получает знания только через Core IPC и безопасные projection events.
- Права каталога Core и файла базы устанавливаются как `0700` и `0600` соответственно.
- Никакой Python backend или migration fallback не входит в текущую поставку.
