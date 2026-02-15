from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING
from pydantic import BaseModel, Field

try:
    from crewai.tools import BaseTool
    CREWAI_AVAILABLE = True
except ImportError:
    class BaseTool: pass
    CREWAI_AVAILABLE = False

if TYPE_CHECKING:
    from manager import MemoryMultiManager

# Используем те же схемы Pydantic, что и для LangChain
from .langchain_tool import RecordDecisionInput, SupersedeDecisionInput

class CrewRecordDecisionTool(BaseTool):
    name: str = "record_decision"
    description: str = "Записывает стратегическое решение в долгосрочную память для всей команды агентов."
    args_schema: Type[BaseModel] = RecordDecisionInput
    manager: 'MemoryMultiManager' = Field(exclude=True)

    def _run(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> str:
        return str(self.manager.handle_tool_call("record_decision", {
            "title": title, "target": target, "rationale": rationale, "consequences": consequences
        }))

class CrewSupersedeDecisionTool(BaseTool):
    name: str = "supersede_decision"
    description: str = "Обновляет или заменяет устаревшее командное решение."
    args_schema: Type[BaseModel] = SupersedeDecisionInput
    manager: 'MemoryMultiManager' = Field(exclude=True)

    def _run(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> str:
        return str(self.manager.handle_tool_call("supersede_decision", {
            "title": title, "target": target, "rationale": rationale, 
            "old_decision_ids": old_decision_ids, "consequences": consequences
        }))

def get_crewai_tools(manager: 'MemoryMultiManager') -> List[BaseTool]:
    """Возвращает список инструментов, специально обернутых для CrewAI."""
    if not CREWAI_AVAILABLE:
        return []
    return [
        CrewRecordDecisionTool(manager=manager),
        CrewSupersedeDecisionTool(manager=manager)
    ]
