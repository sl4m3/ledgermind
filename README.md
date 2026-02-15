# Agent Memory Monorepo

Экосистема пакетов для управления долгосрочной и краткосрочной памятью автономных агентов. Система спроектирована для обеспечения "объяснимости" (explainability) и аудируемости действий ИИ.

## Структура проекта

### 1. Core (`agent-memory-core`)
Ядро системы, отвечающее за логику хранения, обработку конфликтов и эволюцию знаний.

*   **Episodic Memory (SQLite):** Хранит поток событий, логов и краткосрочных данных. Поддерживает автоматическое затухание (decay) и очистку старых записей.
*   **Semantic Memory (Git + Markdown):** Хранит важные решения и знания в виде Markdown-файлов в Git-репозитории. Это обеспечивает:
    *   **Аудируемость:** Каждое изменение — это коммит.
    *   **Версионирование:** Можно отследить, как менялись взгляды агента.
    *   **Безопасность:** Механизм `TrustBoundary` контролирует, что агент может менять сам, а что — только человек.
*   **Reasoning Engines:** Включает модули для обнаружения конфликтов в решениях и их автоматического или управляемого разрешения.

### 2. Multi (`agent-memory-multi`)
Универсальный мост между ядром памяти и современными LLM/фреймворками.

*   **Адаптеры для LLM:** Готовые интеграции для **Google Gemini**, **OpenAI**, **Anthropic** и **Ollama**. Автоматически генерирует JSON-схемы инструментов (Tool/Function Calling).
*   **Интеграция с фреймворками:** Поддержка **LangChain** и **CrewAI** (экспортирует память как стандартные инструменты/tools).
*   **Менеджер вызовов:** Упрощает обработку ответов от моделей, транслируя их в вызовы API ядра.

## Установка

### Базовая установка (ядро)
```bash
pip install ./core
```

### Полная установка (с поддержкой LLM)
```bash
pip install ./core ./multi
```

## Использование с Google Gemini

```python
from agent_memory_core.api.memory import Memory
from agent_memory_multi.manager import MemoryMultiManager
from agent_memory_multi.adapters.google_adapter import GoogleAdapter

# Инициализация
core = Memory(storage_path="./mem_data")
manager = MemoryMultiManager(core)
adapter = GoogleAdapter(manager)

# Получение инструментов для модели
tools = adapter.get_tool_definitions()
# ... передайте tools в genai.GenerativeModel
```

## Разработка и Тестирование

Для установки в режиме редактирования:
```bash
pip install -e ./core -e ./multi
```

Запуск всех тестов:
```bash
make test
```
