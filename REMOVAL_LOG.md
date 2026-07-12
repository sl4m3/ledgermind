# LedgerMind → Hermes: Журнал удаления артефактов

## Тесты: адаптация под удалённые артефакты (ВЫПОЛНЕНО)

Все тесты, проверявшие удалённые артефакты (TrustBoundary, терминальные клиенты,
enrichment_mode, RationaleStr.min_length, мёртвый блок reflection), исправлены под
новый код. Результат прогона `tests/core/` (без test_properties — нет hypothesis):
**209 passed, 3 failed (pre-existing, падают и на main)**.

### Исправлено:
- `tests/core/reasoning/test_epistemic_enrichment.py` — `LLMEnricher()` без mode,
  патч `base_client.BaseURLClient.call` вместо `clients.CloudLLMClient.call`.
- `tests/core/reasoning/test_llm_enrichment_full.py` — убраны `mode="optimal"/"rich"`,
  патч `base_client.BaseURLClient.call` (вместо LocalLLMClient/CloudLLMClient).
- `tests/core/reasoning/enrichment/test_enrichment_transaction.py` — `LLMEnricher(enrichment_language=...)`,
  `test_nested_transaction_not_needed` адаптирован под per-proposal транзакции
  (mock возвращает объект с evidence_event_ids == исходным → 1 транзакция).
- `tests/core/reasoning/enrichment/test_evidence_inheritance.py` — `LLMEnricher(enrichment_language=...)`.
- `tests/core/audit/test_api_boundaries.py` — удалён TrustBoundary, тест проверяет
  базовый record_decision (без human/agent разделения).
- `tests/core/audit/test_hermetic.py` — убран импорт TrustBoundary + удалён
  `test_trust_boundary_bypass_attempt` (проверял удалённый артефакт).
- `tests/core/audit/test_migration.py` — убран `trust_boundary=` из SemanticStore(...),
  assert `rationale: short` (без "(Migrated content)" — блок Fix Rationale Length удалён).
- `tests/core/test_schemas.py` — `test_proposal_content_invalid_rationale_length`:
  короткий rationale теперь валиден (RationaleStr.min_length=10 удалён).
- `tests/test_verify_autonomous_heartbeat.py` — убран мёртвый импорт TrustBoundary.
- `tests/server/test_install_hermes.py` — убраны asserts на `_import_state_db`/
  `_read_state_db`/`_call_enrichment_model` (функций нет в плагине).

### Найден и исправлен баг в `reflection.py` (моя правка):
- Удаляя мёртвый блок (182-216), я случайно выпилил создание `stream`
  перед `calculate_temporal_signals(stream, ...)` → "cannot access local variable 'stream'".
- Восстановлено: `stream = DecisionStream(decision_id=..., target=..., title=...,
  rationale=..., status="draft")` перед расчётом сигналов.

### Pre-existing failures (НЕ от моих правок, падают на main):
- `tests/core/audit/test_smoke.py::test_system_wide_smoke_check` — FileNotFoundError
  `~/.ledgermind/hermes/config.json` (тестовое окружение).
- `tests/core/test_bridge.py::test_record_and_get_context` — AssertionError (pre-existing).
- `tests/core/test_advanced_reasoning.py::test_hybrid_search_rrf_and_grounding_boost` — pre-existing.
- `tests/core/audit/test_properties.py` — нет модуля `hypothesis` (зависимость не установлена).
- `tests/server/test_install_hermes.py`, `test_plugin_hermes.py` — тяжёлые
  (install CLI создаёт venv + pip install), pre-existing broken (ждут функций
  `_search`/`_read_state_db`/`_call_enrichment_model`, которых нет в плагине).

---

## Этап А: Системная чистка терминальных клиентов обогащения (ВЫПОЛНЕНО)

**Решение (Станислав):** "всё через config, через один base URL. Форматов нет.
Терминальные клиенты (Gemini CLI/Cloud Code, AI Studio, OpenRouter, local llama-cpp) — артефакты."

### УДАЛЕНО: `enrichment/clients.py` (CloudLLMClient + LocalLLMClient)
- **Файл:** `src/ledgermind/core/reasoning/enrichment/clients.py` (УДАЛЁН)
- **Артефакт:** `CloudLLMClient` = терминальный бинарь Gemini CLI
  (`shutil.which("gemini")`, `GeminiConfigManager.get_config_path`, `subprocess.Popen([self._bin,...])`)
  + SDK `google.generativeai`. `LocalLLMClient` = llama-cpp локальная модель.
- **Замена:** единый `BaseURLClient` (OpenAI-compatible `/v1/chat/completions`).

### УДАЛЕНО: `enrichment/aistudio_client.py` (AIStudioClient)
- **Файл:** `src/ledgermind/core/reasoning/enrichment/aistudio_client.py` (УДАЛЁН)
- **Артефакт:** Google AI Studio API клиент (терминальная эпоха).

### УДАЛЕНО: `enrichment/openrouter_client.py` (OpenRouterClient)
- **Файл:** `src/ledgermind/core/reasoning/enrichment/openrouter_client.py` (УДАЛЁН)
- **Артефакт:** OpenRouter API клиент (терминальная эпоха).

### УДАЛЕНО: `utils/gemini_config.py` (GeminiConfigManager)
- **Файл:** `src/ledgermind/core/utils/gemini_config.py` (УДАЛЁН)
- **Артефакт:** управление `~/.gemini/settings.json`, `GEMINI_CONFIG_PATH`,
  `LEDGERMIND_BYPASS_HOOKS`. Только для CloudLLMClient.

### ПЕРЕПИСАНО: `enrichment/config.py` (EnrichmentConfig)
- Убран `provider`/`client` как параметры выбора терминального клиента.
- Добавлен единый пайплайн: `base_url` + `model_name` + `api_key` (OpenAI-compatible).
- `from_memory` читает (приоритет):
  1. `LedgermindConfig.enrichment_base_url` / `.enrichment_model` / `.enrichment_api_key`
  2. `~/.hermes/plugins/ledgermind/config.json` (base_url, model)
     + `~/.hermes/plugins/ledgermind/.env` (LEDGERMIND_API_KEY)
  3. `meta.get_config("enrichment_*")` (legacy)
  4. `ENRICHMENT_DEFAULTS[provider]` (openrouter/nvidia/aistudio/custom)
- Добавлено в `LedgermindConfig` (schemas.py): `enrichment_provider`,
  `enrichment_base_url`, `enrichment_api_key` (Optional, с дефолтами).

### СОЗДАНО: `enrichment/base_client.py` (BaseURLClient)
- Единый OpenAI-compatible клиент (POST `{base_url}/chat/completions`, Bearer key).
- Заменяет CloudLLMClient/LocalLLMClient/AIStudioClient/OpenRouterClient.

### ИЗМЕНЕНО: `enrichment/facade.py`
- `_get_client` → всегда `BaseURLClient` (убрано ветвление по provider).
- Убран импорт `clients`, мёртвые `self._local_client`/`_openrouter_client`/`_aistudio_client`.
- Убраны `client=` из всех `EnrichmentConfig.from_memory(...)` (6 мест).

### ИЗМЕНЕНО: `enrichment/__init__.py`
- Экспорт: убраны CloudLLMClient/LocalLLMClient/OpenRouterClient/AIStudioClient,
  добавлен BaseURLClient.

---

## Этап Б: server/tools/ (ПРОВЕРЕНО — чистое)

- `server/tools/definitions.py` (15 MCP-инструментов): нет Gemini CLI / Cloud Code /
  CLI-флагов / Termux / hermes-openclaw клиентов. Чисто.
- `server/tools/environment.py`, `scanner.py`: чисто (grep 0 артефактов).
- Примечание: `sync_git_history` / `visualize_graph` / `bootstrap_project_context` /
  `get_environment_health` помечены в плане кейса как "вырезать" (server-слой для плагина) —
  НЕ тронуты (это отдельная задача вырезания server-слоя, не ядро).

---

Цель: адаптация ядра LedgerMind под пайплайн Hermes. Убираем артефакты старой
архитектуры (CLI-бинарь, терминальные агенты Gemini/Cloud Code/AI Studio,
мобильные/lite-оптимизации, "⚡ Bolt" микро-оптимизации, сырые вещи).

Каждое удаление фиксируется здесь с причиной, чтобы в остальных файлах
можно было связно убирать зависимости (импорты, проверки, конфиги).

---

## enrichment_mode (Enrichment Mode) — артефакт терминальной эпохи

### УДАЛЕНО: `enrichment_mode` как параметр выбора формата
- **Решение (Станислав):** "Enrichment Mode — это артефакт. У нас нет rich.
  Это было через терминал. Всё идёт через config, через один base URL.
  Форматов нет." → убрать концепцию выбора формата (rich/optimal/lite).
- **Удалено:**
  - `enrichment/config.py`: поле `EnrichmentConfig.mode` (было `mode: str = "rich"`);
    параметр `mode` из `EnrichmentConfig.from_memory(...)`; строка
    `config.mode = meta.get_config("enrichment_mode") or config.mode`.
    (Сохранены: `provider`, `max_tokens`, `retry_attempts`, `retry_delay`, `timeout`,
    `enrichment_language`, `model_name` — нужные поля.)
  - `enrichment/facade.py`: `self.mode` (из `__init__`, `run_auto_enrichment`, лога);
    `mode=` из всех 6 вызовов `EnrichmentConfig.from_memory(...)` (строки ~190, 308, 417, 716, 888, 1162);
    ветвление `if config.mode == "rich":` в `_get_client` заменено на
    `if config.provider != "local":` (provider остался, local = llama-cpp;
    терминальная логика клиентов — отдельный этап чистки, см. ниже).
  - `reasoning/reflection.py`: переменная `enrichment_mode` (строка 61);
    параметр `enrichment_mode` из `_create_pattern_stream(...)` (сигнатура + вызов).
    Ранее переименован `arbitration_mode`→`enrichment_mode` — теперь убран совсем.
- **Проверка:** `grep` на `enrichment_mode|self.mode|config.mode|, mode=` → 0
  (кроме `model_dump(mode="json")` и `journal_mode` — не наш параметр);
  `py_compile` config/facade/reflection/lifecycle → OK.
- **НЕ ТРОНУТО (следующий этап — системная чистка подсистемы обогащения):**
  Терминальные клиенты и провайдеры: `CloudLLMClient` (Gemini CLI + SDK,
  `shutil.which("gemini")`, `GeminiConfigManager`), `gemini_config.py` (весь файл),
  `LocalLLMClient` (llama-cpp через `LEDGERMIND_LOCAL_LLM_PATH`), `OpenRouterClient`,
  `AIStudioClient`, `provider`/`client` логика выбора модели в `config.py`/`facade.py`.
  По директиве "всё через config + base URL" эта подсистема — артефакт,
  подлежит переписыванию (отдельный проход, НЕ в рамках текущей чистки ядра).

### УДАЛЕНО: мёртвый `default_cli` в `bridge.py`
- **Файл:** `src/ledgermind/core/api/bridge.py`
- **Что:** параметр `default_cli: Optional[List[str]] = None` в `__init__`
  (строка 20) и `self.default_cli = default_cli or ["hermes"]` (строка 35).
  `hermes` как CLI-клиент — артефакт терминальной эпохи; поле **не используется**
  нигде в файле (мёртвое). `Bridge(...)` в server.py:133 вызывается без `default_cli`.
- **Проверка:** `grep` на `default_cli` → только определение+строка 35 (убраны);
  `py_compile` bridge.py → OK.

## schemas.py (src/ledgermind/core/core/schemas.py)

### УДАЛЕНО: `RationaleStr` ограничение `min_length=10`
- **Где:** строка 41, тип `RationaleStr` (используется в `BaseSemanticContent.rationale`, строка 80)
- **Было:** `RationaleStr = Annotated[str, StringConstraints(min_length=10, strip_whitespace=True)]`
- **Стало:** `RationaleStr = str`
- **Причина:** Hermes-пайплайн пишет короткие авто-генерируемые rationale
  (напр. "Auto-generated during lifecycle processing"). Жёсткий `min_length=10`
  ломал запись таких гипотез. Ограничение — артефакт старой архитектуры,
  где rationale писал внешний LLM-клиент длинными текстами.
- **Связанные точки для проверки:** только schemas.py (поле `rationale`).
  Других использований `RationaleStr` нет — чисто.

### УДАЛЕНО: CLI-конфигурация из `LedgermindConfig`
- **Где:** строки 174-178 (`cli_binary_path`, `cli_global_config_path`,
  `cli_project_config_path`, `cli_config_mode`)
- **Причина:** это конфигурация под отдельный CLI-бинарь LedgerMind
  (автономная программа). В плагине Hermes пайплайн живёт внутри агента,
  CLI-бинарь не используется. Чистый артефакт.
- **Связанные точки для проверки:** только schemas.py. Поиск по репо
  (`cli_binary_path|cli_global_config_path|cli_project_config_path|cli_config_mode`)
  не нашёл использований вне schemas.py — чисто.

---

## migration.py (src/ledgermind/core/core/migration.py)

### УДАЛЕНО: Termux/Android-ветки в `vector.py`
- **Файл:** `src/ledgermind/core/stores/vector.py`
- **Что убрано (мобильный мусор под Termux, не нужен для Hermes):**
  - `_is_annoy_available()` (строки ~49-52): `if os.path.exists("/data/data/com.termux") or platform.system() == "Android": return False` → Annoy теперь доступен всегда (если импортируется).
  - `GguFEmbeddingAdapter.__init__` (строки ~85-100): `is_android` проверка и `use_mmap=not is_android` → стало `use_mmap=True`. Убраны комменты про SIGSEGV/Android.
  - docstring `VectorStore` (строка ~233): убрано "in environments like Termux".
  - `_resolve_workers` (строки ~337-340): убран коммент "safety in constrained environments like Termux" (логика та же: workers>0 → workers, иначе 1).
  - `_get_pool` (строки ~444-452): убрана `is_android`/Termux ветка `target_devices=["cpu"]*workers` → стало `target_devices=None` всегда.
- **Оставлено:** `KMP_DUPLICATE_LIB_OK` / `TOKENIZERS_PARALLELISM` env-хаки в `model` property (нужны для llama-cpp в многопотоке на десктопе тоже, не мобильные).
- **Проверка:** `grep` на `termux|Termux|Android|is_android` → 0; `py_compile` → OK; `os`/`platform` ещё используются (не висят мёртвыми).

- **Где:** строки 75-79 (внутри `migrate_to_v1_22`)
- **Было:**
  ```python
  # 3. Fix Rationale Length
  rationale = ctx.get("rationale", "")
  if len(rationale) < 10:
      ctx["rationale"] = f"{rationale} (Migrated content)"
      changed = True
  ```
- **Причина:** тот же артефакт `min_length=10`, что убран из `RationaleStr`
  (schemas.py). Миграция дописывала "(Migrated content)" к коротким
  rationale, ломая Hermes-пайплайн (короткие авто-rationale снова
  раздувались до ≥10). В новом пайплайне короткий rationale валиден.
- **Оставлено:** блоки #1 (kind), #2 (target ≥3), #4 (namespace) —
  валидные нормализаторы формата, не связаны с ограничением длины.
- **Связанные точки:** только migration.py.

### ИСПРАВЛЕНО: условие индексации векторов в `reindex_missing()`
- **Где:** строка 399 (внутри `reindex_missing`)
- **Было:** `if ctx.get("enrichment_status") == "completed" or ctx.get("rationale"):`
- **Стало:** `if ctx.get("enrichment_status") == "completed":`
- **Причина (баг):** `or ctx.get("rationale")` индексировал ЛЮБУЮ запись с
  `rationale`, включая `pending`-гипотезы на этапе обогащения (у них rationale
  уже заполнен LLM, но `enrichment_status` ещё `pending`). Результат: векторы
  считались для незавершённых гипотез → лишняя нагрузка на процессор.
  Гипотезы индексируются только когда `completed` (они инъекцируются в контекст
  после завершения). Зрелые решения (`decision`/`constraint`/`assumption`)
  индексируются при создании, не зависят от этого условия.
- **Примечание:** диагностика указывала на `decision_command.update_decision`,
  но авто-обогащение туда не заходит (facade.py вызывает низкоуровневый
  `semantic.update_decision`). Реальный источник — `reindex_missing`.

---

## TrustBoundary (УДАЛЕНО полностью)

- **Решение:** убрать разделение human/agent (Станислав: "не имеет значения,
  кто пишет"). Сам класс и все проверки доверия выпилены.
- **Удалено:**
  - `schemas.py`: класс `TrustBoundary` (enum agent/human), поле
    `LedgermindConfig.trust_boundary`.
  - `stores/semantic.py`: импорт, параметр `trust_boundary` в `__init__`,
    `self.trust_boundary`, метод `_enforce_trust` (и его вызовы в `save`/`update_decision`).
  - `api/context.py`: импорт, поле `MemoryContext.trust_boundary`.
  - `api/services/health.py`: импорт, блок
    `if results["errors"] and self.context.trust_boundary == ...`.
  - `api/services/event_processing.py`: импорт, блок
    "Trust Boundary Violation" (возврат `should_persist=False`).
  - `api/memory.py`: импорт, параметр `trust_boundary` в `__init__`,
    строка доки, передача в `LedgermindConfig`, `self.trust_boundary`,
    аргументы в `SemanticStore(...)` и `MemoryContext(...)`.
  - `server/server.py`: импорт, аргумент `trust_boundary=TrustBoundary.AGENT_WITH_INTENT`.
- **Причина:** в новом пайплайне агент = ты (Станислав); разделение
  human/agent-доверия не нужно. Логика была артефактом старой
  автономной архитектуры (кто пишет в память — пользователь или агент).
- **Проверка:** `grep` по `src/` — 0 ссылок; `py_compile` всех 7 файлов — OK.
