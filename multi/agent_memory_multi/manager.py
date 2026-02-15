from typing import Any, Dict, List, Optional
from agent_memory_multi.schema import ToolSchemaGenerator
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.schemas import KIND_DECISION
from agent_memory_multi.frameworks.environment_context import EnvironmentContext

class MemoryMultiManager:
    """Менеджер для работы с памятью в мульти-модельной среде."""

    def __init__(self, core_memory: Optional[Memory] = None):
        """
        Args:
            core_memory: Экземпляр ядра памяти (agent-memory-core).
        """
        self.core = core_memory
        self.schema_gen = ToolSchemaGenerator()
        self.env_context = EnvironmentContext(self) if self.core else None

    def get_tools(self, provider: str = "openai") -> List[Dict[str, Any]]:
        """Возвращает список инструментов в формате конкретного провайдера."""
        tools = [
            self.schema_gen.get_decision_tool_schema(provider),
            self.schema_gen.get_supersede_tool_schema(provider)
        ]
        # Добавляем инструмент захвата контекста (в будущем можно вынести схему в schema.py)
        tools.append({
            "name": "capture_context",
            "description": "Сделать снимок текущего окружения (файлы, git) и сохранить в эпизодическую память.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Метка для снимка (например, 'before_fix')."}
                }
            }
        } if provider != "anthropic" else {
            "name": "capture_context",
            "description": "Сделать снимок текущего окружения (файлы, git) и сохранить в эпизодическую память.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Метка для снимка (например, 'before_fix')."}
                }
            }
        })
        return tools

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

            elif tool_name == "capture_context":
                if not self.env_context:
                    self.env_context = EnvironmentContext(self)
                return self.env_context.capture_context(**arguments)
            
            return {"status": "error", "message": f"Unknown tool: {tool_name}"}
        
        except TypeError as e:
            # Это произойдет, если LLM передаст неверные аргументы, которые не примет метод ядра
            return {"status": "error", "message": f"Invalid arguments: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}
