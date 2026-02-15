# Agent Memory Multi v1.1.1

Универсальный мост (Bridge) между ядром памяти `agent-memory-core` и различными LLM-провайдерами.

## 🚀 Основные возможности

- **MCP (Model Context Protocol)**: Полноценный сервер памяти для Claude Desktop и других MCP-клиентов.
- **Мульти-провайдерная поддержка**: Адаптеры для OpenAI, Anthropic, Google (Gemini) и Ollama.
- **Resilient Embeddings**: Отказоустойчивая система эмбеддингов с автоматическим переключением (например, OpenAI -> Ollama -> Mock).
- **Environment Context**: Инструменты для захвата снимков окружения (файлы, Git, переменные) в эпизодическую память.
- **Интеграция с фреймворками**: Готовые инструменты для LangChain и CrewAI (теперь это **опциональные зависимости**, пакет не падает при их отсутствии).

## 📂 Структура проекта

- `adapters/`: Адаптеры для API провайдеров и MCP сервер.
- `frameworks/`: Обертки для AI-фреймворков и сборщик контекста окружения.
- `embeddings.py`: Логика работы с векторными вложениями и Fallback-система.
- `manager.py`: Центральный контроллер `MemoryMultiManager`.

## 🛠 Использование

### Запуск MCP Сервера
```python
from manager import MemoryMultiManager
from adapters import MCPMemoryAdapter
from api.memory import Memory

core = Memory("./storage")
manager = MemoryMultiManager(core)
mcp_server = MCPMemoryAdapter(manager)

if __name__ == "__main__":
    mcp_server.run()
```

### Использование контекста окружения
```python
# Агент может вызвать этот инструмент перед выполнением задачи
manager.handle_tool_call("capture_context", {"label": "before_migration"})
```

### Настройка Fallback Embeddings
```python
from embeddings import FallbackEmbeddingProvider, OpenAIEmbeddingProvider, OllamaEmbeddingProvider

provider = FallbackEmbeddingProvider([
    OpenAIEmbeddingProvider(),
    OllamaEmbeddingProvider()
])
memory = Memory(storage_path="./mem", embedding_provider=provider)
```

## 🧪 Тестирование

```bash
pytest multi/tests/
```

## 📝 Лицензия
MIT
