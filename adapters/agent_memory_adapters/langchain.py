from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field

try:
    from langchain_core.tools import BaseTool
    LANGCHAIN_AVAILABLE = True
except ImportError:
    class BaseTool: pass
    LANGCHAIN_AVAILABLE = False

class RecordDecisionInput(BaseModel):
    title: str = Field(description="Краткий заголовок решения.")
    target: str = Field(description="Область применения решения.")
    rationale: str = Field(description="Обоснование решения.")
    consequences: Optional[List[str]] = Field(default=None, description="Список последствий.")

class SupersedeDecisionInput(BaseModel):
    title: str = Field(description="Заголовок нового решения.")
    target: str = Field(description="Область применения.")
    rationale: str = Field(description="Причина пересмотра.")
    old_decision_ids: List[str] = Field(description="ID устаревших решений.")
    consequences: Optional[List[str]] = Field(default=None, description="Новые последствия.")

class RecordDecisionTool(BaseTool):
    name: str = "record_decision"
    description: str = "Записывает стратегическое решение в долгосрочную память."
    args_schema: Type[BaseModel] = RecordDecisionInput
    memory: Any = Field(exclude=True)

    def _run(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> str:
        res = self.memory.record_decision(
            title=title, target=target, rationale=rationale, consequences=consequences
        )
        return str(res)

class SupersedeDecisionTool(BaseTool):
    name: str = "supersede_decision"
    description: str = "Заменяет устаревшие решения новым."
    args_schema: Type[BaseModel] = SupersedeDecisionInput
    memory: Any = Field(exclude=True)

    def _run(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> str:
        res = self.memory.supersede_decision(
            title=title, target=target, rationale=rationale, 
            old_decision_ids=old_decision_ids, consequences=consequences
        )
        return str(res)

def get_langchain_tools(memory_provider: Any) -> List[BaseTool]:
    """Returns a list of tools for LangChain."""
    if not LANGCHAIN_AVAILABLE:
        return []
    return [
        RecordDecisionTool(memory=memory_provider),
        SupersedeDecisionTool(memory=memory_provider)
    ]
