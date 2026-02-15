from typing import Any, Dict, List, Optional
import json
import logging
from manager import MemoryMultiManager

logger = logging.getLogger(__name__)

class OllamaAdapter:
    """Адаптер для взаимодействия с Ollama Tool Calling (v0.3.0+)."""

    def __init__(self, manager: MemoryMultiManager):
        self.manager = manager

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Возвращает список инструментов в формате Ollama (аналогично OpenAI)."""
        return self.manager.get_tools(provider="openai")

    def process_tool_calls(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Обрабатывает tool_calls из сообщения Ollama.
        
        Args:
            message: Сообщение из ответа Ollama ('message' в ответе чата).
        """
        results = []
        tool_calls = message.get("tool_calls", [])
        
        for tool_call in tool_calls:
            function_info = tool_call.get("function", {})
            function_name = function_info.get("name")
            arguments = function_info.get("arguments", {})
            
            if not function_name:
                logger.warning("Ollama tool call missing function name")
                results.append({
                    "role": "tool",
                    "content": json.dumps({"status": "error", "message": "Missing function name"})
                })
                continue

            logger.info(f"Processing Ollama tool call: {function_name}")
            # В Ollama аргументы иногда приходят уже как dict, иногда как строка
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse Ollama arguments for {function_name}")
                    results.append({
                        "role": "tool",
                        "content": json.dumps({"status": "error", "message": "Invalid JSON arguments"})
                    })
                    continue
            
            output = self.manager.handle_tool_call(function_name, arguments)
            
            results.append({
                "role": "tool",
                "content": json.dumps(output)
            })
        return results
