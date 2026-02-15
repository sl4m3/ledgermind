from typing import Any, Dict, List, Optional, Type

try:
    from crewai.tools import BaseTool
    CREWAI_AVAILABLE = True
except ImportError:
    class BaseTool: pass
    CREWAI_AVAILABLE = False

class RecordDecisionTool(BaseTool):
    name: str = "record_decision"
    description: str = "Записывает стратегическое решение в долгосрочную память."
    memory: Any = None

    def _run(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> str:
        res = self.memory.record_decision(
            title=title, target=target, rationale=rationale, consequences=consequences
        )
        return str(res)

class SupersedeDecisionTool(BaseTool):
    name: str = "supersede_decision"
    description: str = "Заменяет устаревшие решения новым."
    memory: Any = None

    def _run(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> str:
        res = self.memory.supersede_decision(
            title=title, target=target, rationale=rationale, 
            old_decision_ids=old_decision_ids, consequences=consequences
        )
        return str(res)

def get_crewai_tools(memory_provider: Any) -> List[BaseTool]:
    """Returns a list of tools for CrewAI."""
    if not CREWAI_AVAILABLE:
        return []
    return [
        RecordDecisionTool(memory=memory_provider),
        SupersedeDecisionTool(memory=memory_provider)
    ]
