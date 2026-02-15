from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from manager import MemoryMultiManager

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
    manager: MemoryMultiManager = Field(exclude=True)

    def _run(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> str:
        res = self.manager.handle_tool_call("record_decision", {
            "title": title, "target": target, "rationale": rationale, "consequences": consequences
        })
        return str(res)

    async def _arun(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> str:
        """Асинхронная версия записи решения."""
        return self._run(title, target, rationale, consequences)

class SupersedeDecisionTool(BaseTool):
    name: str = "supersede_decision"
    description: str = "Заменяет устаревшие решения новым."
    args_schema: Type[BaseModel] = SupersedeDecisionInput
    manager: MemoryMultiManager = Field(exclude=True)

    def _run(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> str:
        res = self.manager.handle_tool_call("supersede_decision", {
            "title": title, "target": target, "rationale": rationale, 
            "old_decision_ids": old_decision_ids, "consequences": consequences
        })
        return str(res)

    async def _arun(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> str:
        """Асинхронная версия замены решения."""
        return self._run(title, target, rationale, old_decision_ids, consequences)

def get_langchain_tools(manager: MemoryMultiManager) -> List[BaseTool]:
    """Возвращает список инструментов для LangChain."""
    return [
        RecordDecisionTool(manager=manager),
        SupersedeDecisionTool(manager=manager)
    ]
