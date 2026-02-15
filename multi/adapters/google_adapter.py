from typing import Any, Dict, List, Optional
import logging
from manager import MemoryMultiManager

logger = logging.getLogger(__name__)

class GoogleAdapter:
    """Адаптер для взаимодействия с Google Gemini API."""

    def __init__(self, manager: MemoryMultiManager):
        self.manager = manager

    def get_tool_definitions(self) -> Dict[str, Any]:
        """
        Возвращает инструменты в формате Google Generative AI.
        Gemini ожидает структуру {"function_declarations": [...]}.
        """
        return {
            "function_declarations": self.manager.get_tools(provider="gemini")
        }

    def process_function_calls(self, part: Any) -> List[Dict[str, Any]]:
        """
        Обрабатывает части ответа Gemini (parts), содержащие function_call.
        
        Args:
            part: Объект part из ответа Gemini (candidate.content.parts[0]).
        """
        results = []
        if hasattr(part, 'function_call'):
            call = part.function_call
            function_name = getattr(call, 'name', None)
            
            if not function_name:
                logger.warning("Gemini function call missing name")
                return results

            logger.info(f"Processing Gemini function call: {function_name}")
            # Превращаем Google-специфичные аргументы в обычный дикт
            arguments = {k: v for k, v in getattr(call, 'args', {}).items()}
            
            output = self.manager.handle_tool_call(function_name, arguments)
            
            # Формат ответа для Gemini (записывается в контент следующего хода)
            results.append({
                "function_response": {
                    "name": function_name,
                    "response": output
                }
            })
        return results
