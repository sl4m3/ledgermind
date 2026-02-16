import json
import logging
from typing import Any, Dict, List, Optional
from agent_memory_adapters.base import BaseLLMAdapter

logger = logging.getLogger(__name__)

class GoogleAdapter(BaseLLMAdapter):
    """Adapter for Google Gemini Tool Calling."""

    def __init__(self, memory_provider: Any):
        super().__init__(provider="gemini")
        self.memory = memory_provider

    def handle_tool_calls(self, tool_calls: List[Any]) -> List[Dict[str, Any]]:
        """Processes tool calls from Gemini response."""
        results = []
        for tc in tool_calls:
            # Google Gemini tool calls have 'function_call' attribute
            fc = getattr(tc, 'function_call', None)
            if not fc: continue
            
            function_name = getattr(fc, 'name', None)
            arguments = getattr(fc, 'args', {})
            
            if not function_name: continue
            
            logger.info(f"Processing Gemini tool call: {function_name}")
            try:
                method = getattr(self.memory, function_name)
                output = method(**arguments)
                if hasattr(output, "model_dump"):
                    output = output.model_dump(mode='json')
                
                results.append({
                    "function_name": function_name,
                    "response": {"result": output}
                })
            except Exception as e:
                results.append({
                    "function_name": function_name,
                    "response": {"error": str(e)}
                })
        return results
