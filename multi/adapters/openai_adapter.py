from typing import Any, Dict, List, Optional
import json
import logging
from manager import MemoryMultiManager

logger = logging.getLogger(__name__)

class OpenAIAdapter:
    """Адаптер для взаимодействия с OpenAI Tool Calling API."""

    def __init__(self, manager: MemoryMultiManager):
        self.manager = manager

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Возвращает список инструментов в формате OpenAI."""
        return self.manager.get_tools(provider="openai")

    def process_tool_calls(self, tool_calls: List[Any]) -> List[Dict[str, Any]]:
        """
        Обрабатывает список tool_calls от OpenAI и возвращает результаты.
        
        Args:
            tool_calls: Список объектов ChatCompletionMessageToolCall.
        """
        results = []
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            logger.info(f"Processing OpenAI tool call: {function_name}")
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse arguments for {function_name}: {e}")
                results.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps({"status": "error", "message": f"Invalid JSON arguments: {str(e)}"})
                })
                continue
            
            output = self.manager.handle_tool_call(function_name, arguments)
            
            results.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": json.dumps(output)
            })
        return results
