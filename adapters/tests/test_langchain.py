import pytest
from unittest.mock import MagicMock
from agent_memory_adapters.langchain import AgentMemoryVectorStore, Document

def test_langchain_vector_store_search():
    mock_memory = MagicMock()
    mock_memory.search_decisions.return_value = [
        {"id": "doc1", "preview": "Content 1", "status": "active", "target": "T1"},
        {"id": "doc2", "preview": "Content 2", "status": "active", "target": "T2"}
    ]
    
    vs = AgentMemoryVectorStore(mock_memory)
    docs = vs.similarity_search("query", k=2)
    
    assert len(docs) == 2
    assert docs[0].page_content == "Content 1"
    assert docs[0].metadata["id"] == "doc1"
    assert docs[1].page_content == "Content 2"
    
    mock_memory.search_decisions.assert_called_once_with(query="query", limit=2)

def test_langchain_vector_store_add_texts():
    mock_memory = MagicMock()
    # Mocking response from record_decision
    # It can be a dict or an object with metadata attribute
    mock_res = MagicMock()
    mock_res.metadata = {"file_id": "new_doc.md"}
    mock_memory.record_decision.return_value = mock_res
    
    vs = AgentMemoryVectorStore(mock_memory)
    ids = vs.add_texts(["text content"], metadatas=[{"title": "Title", "target": "Target"}])
    
    assert ids == ["new_doc.md"]
    mock_memory.record_decision.assert_called_once_with(
        title="Title",
        target="Target",
        rationale="text content"
    )
