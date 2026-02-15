from typing import Any, Dict, List, Optional
import json
import logging
from agent_memory_adapters.base import BaseLLMAdapter

logger = logging.getLogger(__name__)

class AnthropicAdapter(BaseLLMAdapter):
    """Adapter for interacting with Anthropic (Claude) Tool Use API."""

    def __init__(self, memory_provider: Any):
        super().__init__(provider="anthropic")
        self.memory = memory_provider

    def process_tool_use(self, content_blocks: List[Any]) -> List[Dict[str, Any]]:
        results = []
        for block in content_blocks:
            if getattr(block, 'type', None) == 'tool_use':
                tool_use_id = getattr(block, 'id', None)
                function_name = getattr(block, 'name', None)
                arguments = getattr(block, 'input', {})
                
                if not tool_use_id or not function_name:
                    continue
                
                logger.info(f"Processing Anthropic tool use: {function_name} ({tool_use_id})")
                
                try:
                    method = getattr(self.memory, function_name)
                    output = method(**arguments)
                    if hasattr(output, "model_dump"):
                        output = output.model_dump(mode='json')
                    
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(output)
                    })
                except Exception as e:
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps({"status": "error", "message": str(e)}),
                        "is_error": True
                    })
        return results
