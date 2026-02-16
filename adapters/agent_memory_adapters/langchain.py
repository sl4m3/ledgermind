from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field

try:
    from langchain_core.tools import BaseTool
    from langchain_core.vectorstores import VectorStore
    from langchain_core.documents import Document
    from langchain_core.embeddings import Embeddings
    LANGCHAIN_AVAILABLE = True
except ImportError:
    class BaseTool:
        def __init__(self, **kwargs): pass
    class VectorStore:
        def __init__(self, **kwargs): pass
    class Document:
        def __init__(self, **kwargs):
            for k, v in kwargs.items(): setattr(self, k, v)
    class Embeddings:
        def __init__(self, **kwargs): pass
    LANGCHAIN_AVAILABLE = False

# ... (rest of tools code)

class AgentMemoryVectorStore(VectorStore):
    """
    LangChain VectorStore wrapper for Agent Memory System.
    Uses the underlying MemoryProvider (MCP or Core) for retrieval.
    """
    def __init__(self, memory_provider: Any, embeddings: Optional[Embeddings] = None):
        self.memory = memory_provider
        self.embeddings = embeddings

    def add_texts(self, texts: List[str], metadatas: Optional[List[dict]] = None, **kwargs: Any) -> List[str]:
        ids = []
        for i, text in enumerate(texts):
            meta = metadatas[i] if metadatas else {}
            res = self.memory.record_decision(
                title=meta.get("title", text[:50]),
                target=meta.get("target", "langchain_import"),
                rationale=text
            )
            # Handle both direct object and dict responses
            doc_id = res.metadata.get("file_id") if hasattr(res, "metadata") else res.get("decision_id")
            ids.append(doc_id)
        return ids

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> List[Document]:
        results = self.memory.search_decisions(query=query, limit=k)
        docs = []
        for res in results:
            docs.append(Document(
                page_content=res.get("preview", ""),
                metadata={
                    "id": res.get("id"),
                    "status": res.get("status"),
                    "target": res.get("target")
                }
            ))
        return docs

    @classmethod
    def from_texts(cls, texts: List[str], embedding: Embeddings, metadatas: Optional[List[dict]] = None, **kwargs: Any) -> 'AgentMemoryVectorStore':
        raise NotImplementedError("Use constructor with memory_provider instead.")

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
