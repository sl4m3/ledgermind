# Invariants LedgerMind core

## Доменные инварианты

### SourceReference
- `source_system`, `source_instance_id`, `source_profile_id`, `source_session_id`, `source_round_id`, `source_digest` — непустые строки.
- `source_digest` строго соответствует шаблону `sha256:<64 hex>`.
- `source_schema_version >= 1`.
- `resolver_version >= 1`.

### AtomContent
- `title`, `target`, `statement` — не пустые (после trim).
- `title`, `target` не длиннее 240 символов.
- `rationale`, `result` не `None`.
- `artifacts` приводятся к `tuple[str, ...]`.

### ExtractionInfo
- `host` не пустой.
- `prompt_version >= 1`.
- `schema_version >= 1`.
- `provider` и `model` допускаются пустыми строками (но не `None`).

### Atom
- `atom_id`, `memory_space_id` не пустые.
- `created_at` должен быть timezone-aware.
- `supersedes_atom_id` не может совпадать с `atom_id`.

### KnowledgeItem
- `knowledge_id`, `memory_space_id` не пустые.
- `version >= 1`.
- `created_at`, `updated_at` timezone-aware и `updated_at >= created_at`.
- `superseded_by_id` не равен самому `knowledge_id`.
- `deleted_at` (если указан) timezone-aware.
- `is_current` истинно только при `superseded_by_id is None` и `deleted_at is None`.

### KnowledgeRevision
- `revision_id`, `knowledge_id` не пустые.
- `version >= 1`.
- `event_type` не пуст.
- `snapshot_json` валидный JSON.
- `created_at` timezone-aware.

### KnowledgeEvidence
- `knowledge_id`, `atom_id` не пустые.
- `created_at` timezone-aware.

## Бизнес-инварианты приложения

- Все операции выполняются атомарно через `UnitOfWork` (один `commit` на успешный сценарий).
- Идентичные idempotency-запросы с тем же `request_hash` возвращают закешированный ответ.
- Идентичный `idempotency_key` с другим `request_hash` вызывает `IdempotencyConflict`.
- `GetAtom`, `GetKnowledge`, `RetrieveContext` не создают новых записей.
- Удаление знания помечает `deleted_at`, увеличивает `version` и пишет ревизию/событие.
- Ручное замещение:
  - принимает только знания текущего пространства памяти;
  - все исходные знания должны существовать и быть текущими;
  - проверяются ожидаемые версии;
  - создаётся замещающее знание и ревизии/события.

## Инварианты портов

- `UnitOfWork` обязан вызывать `rollback` при исключении внутри контекста.
- Репозитории должны поддерживать подготовительную (`begin`) и фиксационную (`commit`) стадию или эквивалентную транзакционную семантику.
- `idempotency`, `events`, `search`, `evidence`, `revisions`, `knowledge` и `atoms` в сценарии не должны оставлять частичные изменения после ошибки.
