import json
import logging
from typing import Any, Dict, List, Optional
from agent_memory_adapters.base import BaseLLMAdapter

logger = logging.getLogger(__name__)

class OllamaAdapter(BaseLLMAdapter):
    """Adapter for Ollama Tool Calling."""

    def __init__(self, memory_provider: Any):
        super().__init__(provider="ollama")
        self.memory = memory_provider

    def process_tool_calls(self, tool_calls: List[Any]) -> List[Dict[str, Any]]:
        """Processes tool calls from Ollama response."""
        results = []
        for tool_call in tool_calls:
            # Ollama tool calls usually have 'function' with 'name' and 'arguments'
            func = getattr(tool_call, 'function', None)
            if not func: continue
            
            function_name = getattr(func, 'name', None)
            arguments = getattr(func, 'arguments', {})
            
            if not function_name: continue
            
            logger.info(f"Processing Ollama tool call: {function_name}")
            try:
                method = getattr(self.memory, function_name)
                output = method(**arguments)
                if hasattr(output, "model_dump"):
                    output = output.model_dump(mode='json')
                
                results.append({
                    "status": "success",
                    "name": function_name,
                    "content": output
                })
            except Exception as e:
                results.append({
                    "status": "error",
                    "name": function_name,
                    "message": str(e)
                })
        return results
