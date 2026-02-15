from typing import Any, Dict, List, Optional
import json
import logging
from manager import MemoryMultiManager

logger = logging.getLogger(__name__)

class AnthropicAdapter:
    """Адаптер для взаимодействия с Anthropic (Claude) Tool Use API."""

    def __init__(self, manager: MemoryMultiManager):
        self.manager = manager

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Возвращает список инструментов в формате Anthropic."""
        return self.manager.get_tools(provider="anthropic")

    def process_tool_use(self, content_blocks: List[Any]) -> List[Dict[str, Any]]:
        """
        Обрабатывает блоки контента от Claude и находит tool_use.
        
        Args:
            content_blocks: Список блоков из сообщения Claude (message.content).
        """
        results = []
        for block in content_blocks:
            if getattr(block, 'type', None) == 'tool_use':
                tool_use_id = getattr(block, 'id', None)
                function_name = getattr(block, 'name', None)
                arguments = getattr(block, 'input', {})
                
                if not tool_use_id or not function_name:
                    logger.warning(f"Incomplete tool_use block skipped: id={tool_use_id}, name={function_name}")
                    continue
                
                logger.info(f"Processing Anthropic tool use: {function_name} ({tool_use_id})")
                output = self.manager.handle_tool_call(function_name, arguments)
                
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(output)
                })
        return results
