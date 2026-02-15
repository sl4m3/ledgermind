# Agent Memory Monorepo

Этот репозиторий содержит экосистему пакетов для управления памятью автономных агентов.

## Структура

- `core/`: Ядро системы (`agent-memory-core`). Минимальные зависимости, логика хранения и обработки.
- `multi/`: Адаптеры и интеграции (`agent-memory-multi`). Поддержка различных LLM (OpenAI, Anthropic и др.) и фреймворков (CrewAI, LangChain).

## Установка

### Только ядро
```bash
pip install ./core
```

### Всё вместе (core + multi)
```bash
pip install ./core ./multi
```

## Разработка

Для установки в режиме редактирования:
```bash
pip install -e ./core
pip install -e ./multi
```
