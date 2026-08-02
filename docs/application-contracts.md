# Application contracts (LedgerMind core)

## Терминология

- `knowledge` — агрегат текущего знания.
- `atom` — извлечённое утверждение из внешнего раунда.
- `revision` — снапшот состояния знания на момент события.
- `outbox event` — доменно-нейтральное событие для локальной проекции.

## Внешние контракты

### `IngestAtomRequest`
- `api_version`: обязательно `"1"`.
- `idempotency_key`: строка `sha256:<64 hex>`.
- `memory_space_id`: непустая строка.
- `source`: `SourceReference`.
- `extraction`: `ExtractionInfo`.
- `atom`: `AtomContent`.

### `IngestAtomResult`
- `api_version`: `"1"`.
- `atom_id`, `knowledge_id`: идентификаторы.
- `knowledge_version >= 1`.
- `phase`: `pattern|emergent|canonical`.
- `duplicate`: признак возврата из idempotency-кэша.
- `projections_pending`: всегда `True` в текущем слое ядра.

### `RetrieveContextRequest`
- `api_version`: `"1"`.
- `memory_space_id`, `query`, `limit`.
- `min_phase`: необязательный фильтр.

### `RetrieveContextResult`
- `api_version`: `"1"`.
- список `ContextItem` с `score` в диапазоне 0..1 и отфильтрованными только `is_current` знаниями.

## Команды/запросы приложения

### `IngestAtomHandler`
- **Вход:** `IngestAtomCommand`
- **Результат:** `IngestAtomResult`
- **Правила:**
  - проверяет idempotency-хранилище;
  - при конфликте `request_hash` выбрасывает `IdempotencyConflict`;
  - на дубликатах возвращает кэшированный ответ с `duplicate=True`;
  - на новом атоме создаёт `Atom`, `KnowledgeItem`, `KnowledgeEvidence`, `KnowledgeRevision`, два outbox-события и результат в idempotency-хранилище.

### `SupersedeKnowledgeHandler`
- **Вход:** `SupersedeKnowledgeCommand`:
  - `memory_space_id`
  - `old_knowledge_ids`
  - replacement поля (`title`, `target`, `statement`, `rationale`)
  - `expected_versions`
- **Результат:** `SupersedeKnowledgeResult`
- **Правила:**
  - все знания должны существовать в том же `memory_space_id`;
  - все должны быть текущими;
  - версии должны совпасть с `expected_versions`;
  - создаётся новое знание и ревизии/события для старых + нового.

### `DeleteKnowledgeHandler`
- **Вход:** `DeleteKnowledgeCommand`
  - `memory_space_id`, `knowledge_id`, `expected_version`, `cause_atom_id`
- **Результат:** `DeleteKnowledgeResult`
- **Правила:**
  - проверка существования и версии;
  - запрет повторного удаления;
  - обновление знания с `deleted_at`, инкремент `version`;
  - запись ревизии и события удаления.

### `RetrieveContextHandler`
- **Вход:** `RetrieveContextQuery`
- **Результат:** `contracts.context.RetrieveContextResult`
- **Правила:**
  - берёт hits из `KnowledgeSearch`, запрашивает знания только по заданным `knowledge_id`,
  - фильтрует по `is_current` и `min_phase`, ранжирует и возвращает `limit`.

### `GetAtomQuery`, `GetKnowledgeQuery`
- Возвращают `Atom`/`KnowledgeItem` или `None`.

## Порты

- `UnitOfWork` с секциями: `atoms`, `knowledge`, `evidence`, `revisions`, `idempotency`, `events`, `search`, `clock`, `identifiers`.
- `DomainEvent`: структура событий в outbox.
- `StoredIdempotencyResult`: запись idempotency результата.
- `SearchHit`: вход для контекста (`knowledge_id`, `lexical_score`, `vector_score`).

## Слой хранения / интеграция

- Ядро не реализует хранение. Локальная служба обязана адаптировать `ports` к SQLite/FTS/векторным индексам и транслировать их в единый `UnitOfWork`.
