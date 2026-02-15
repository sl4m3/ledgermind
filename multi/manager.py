from typing import Any, Dict, List, Optional
from .schema import ToolSchemaGenerator

# Попробуем импортировать Memory для типизации, но не падаем, если пакета еще нет в среде
try:
    from api.memory import Memory
except ImportError:
    Memory = Any

class MemoryMultiManager:
    """Менеджер для работы с памятью в мульти-модельной среде."""

    def __init__(self, core_memory: Optional[Memory] = None):
        """
        Args:
            core_memory: Экземпляр ядра памяти (agent-memory-core).
        """
        self.core = core_memory
        self.schema_gen = ToolSchemaGenerator()

    def get_tools(self, provider: str = "openai") -> List[Dict[str, Any]]:
        """Возвращает список инструментов в формате конкретного провайдера."""
        return [
            self.schema_gen.get_decision_tool_schema(provider),
            self.schema_gen.get_supersede_tool_schema(provider)
        ]

    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполняет команду, полученную от LLM, через ядро памяти.
        Возвращает результат в формате, пригодном для ответа модели.
        """
        if not self.core:
            return {"status": "error", "message": "Core memory not initialized"}

        try:
            if tool_name == "record_decision":
                required = {"title", "target", "rationale"}
                missing = required - set(arguments.keys())
                if missing:
                    return {"status": "error", "message": f"Missing required parameters: {missing}"}
                
                result = self.core.record_decision(**arguments)
                return {
                    "status": "success",
                    "decision_id": getattr(result, "id", "unknown"),
                    "message": "Decision recorded successfully"
                }
            
            elif tool_name == "supersede_decision":
                required = {"title", "target", "rationale", "old_decision_ids"}
                missing = required - set(arguments.keys())
                if missing:
                    return {"status": "error", "message": f"Missing required parameters: {missing}"}

                result = self.core.supersede_decision(**arguments)
                return {
                    "status": "success",
                    "message": "Decision superseded successfully"
                }
            
            return {"status": "error", "message": f"Unknown tool: {tool_name}"}
        
        except TypeError as e:
            return {"status": "error", "message": f"Invalid argument types: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}
