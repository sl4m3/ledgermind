from typing import Any, Dict, List, Optional
from agent_memory_adapters.schema import ToolSchemaGenerator
from agent_memory_adapters.interfaces import MemoryProvider

class BaseLLMAdapter:
    """Base class for LLM adapters that convert memory tools to provider-specific formats."""
    
    def __init__(self, provider: str):
        self.provider = provider
        self.schema_gen = ToolSchemaGenerator()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns tool definitions for the specific LLM provider."""
        # For now, we use the schema generator. 
        # In a full MCP-client version, this would fetch tools from the MCP server.
        return [
            self.schema_gen.get_decision_tool_schema(self.provider),
            self.schema_gen.get_supersede_tool_schema(self.provider)
        ]
