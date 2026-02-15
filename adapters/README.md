# Agent Memory Adapters

LLM-specific adapters for the Agent Memory System. These adapters connect to the Agent Memory Server via MCP or can be used directly with the Core library.

## Supported Providers
- OpenAI
- Anthropic
- Google Gemini
- Ollama
- LangChain Tools
- CrewAI Tools

## Usage Example (Direct)
```python
from agent_memory_core.api.memory import Memory
from agent_memory_adapters.openai import OpenAIAdapter

memory = Memory(storage_path="./mem")
adapter = OpenAIAdapter(memory)
tools = adapter.get_tool_definitions()
```
