from typing import Any, Dict, List, Optional
from schema import ToolSchemaGenerator
from api.memory import Memory
from core.schemas import KIND_DECISION

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
                # record_decision ожидает именованные аргументы, совпадающие со схемой
                result = self.core.record_decision(**arguments)
                return {
                    "status": "success",
                    "decision_id": getattr(result, "id", "unknown"),
                    "message": "Decision recorded successfully"
                }
            
            elif tool_name == "supersede_decision":
                result = self.core.supersede_decision(**arguments)
                return {
                    "status": "success",
                    "message": "Decision superseded successfully"
                }
            
            return {"status": "error", "message": f"Unknown tool: {tool_name}"}
        
        except TypeError as e:
            # Это произойдет, если LLM передаст неверные аргументы, которые не примет метод ядра
            return {"status": "error", "message": f"Invalid arguments: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}
