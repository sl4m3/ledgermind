from typing import Any, Dict, List, Optional
import json
import logging
from agent_memory_adapters.base import BaseLLMAdapter
from agent_memory_adapters.interfaces import MemoryProvider

logger = logging.getLogger(__name__)

class OpenAIAdapter(BaseLLMAdapter):
    """Adapter for interacting with OpenAI Tool Calling API."""

    def __init__(self, memory_provider: MemoryProvider):
        """
        Args:
            memory_provider: An object implementing memory methods (Memory instance or MCP Client).
        """
        super().__init__(provider="openai")
        self.memory = memory_provider

    def process_tool_calls(self, tool_calls: List[Any]) -> List[Dict[str, Any]]:
        results = []
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            logger.info(f"Processing OpenAI tool call: {function_name}")
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps({"status": "error", "message": f"Invalid JSON: {str(e)}"})
                })
                continue
            
            # Direct call to memory object (duck typing)
            try:
                method = getattr(self.memory, function_name)
                output = method(**arguments)
                # Convert MemoryDecision or other objects to dict
                if hasattr(output, "model_dump"):
                    output = output.model_dump(mode='json')
                
                results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps({"status": "success", "data": output} if isinstance(output, dict) else output)
                })
            except Exception as e:
                results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps({"status": "error", "message": str(e)})
                })
        return results
