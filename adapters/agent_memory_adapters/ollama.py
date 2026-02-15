from typing import Any, Dict, List, Optional
from agent_memory_adapters.base import BaseLLMAdapter

class OllamaAdapter(BaseLLMAdapter):
    """Adapter for Ollama Tool Calling."""

    def __init__(self, memory_provider: Any):
        super().__init__(provider="ollama")
        self.memory = memory_provider
