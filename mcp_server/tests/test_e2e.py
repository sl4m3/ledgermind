import pytest
import os
import json
from agent_memory_server.server import MCPServer, MCPRole
from agent_memory_core.api.memory import Memory
from agent_memory_core.core.schemas import EmbeddingProvider
from agent_memory_server.contracts import RecordDecisionRequest, SearchDecisionsRequest

class SimpleMockProvider(EmbeddingProvider):
    def get_embedding(self, text: str):
        return [0.1] * 1536

@pytest.fixture
def real_memory(tmp_path):
    storage = str(tmp_path / "e2e_storage")
    return Memory(storage_path=storage, embedding_provider=SimpleMockProvider())

@pytest.fixture(autouse=True)
def set_auth_token():
    os.environ["AGENT_MEMORY_SECRET"] = "e2e-test-secret"
    yield
    os.environ.pop("AGENT_MEMORY_SECRET", None)

def test_e2e_record_and_search(real_memory):
    """E2E: Запись через сервер и поиск результата."""
    server = MCPServer(memory=real_memory, default_role=MCPRole.ADMIN)
    
    # 1. Записываем решение
    req = RecordDecisionRequest(
        title="E2E Strategy",
        target="testing_area",
        rationale="Testing real integration between MCP and Core layers."
    )
    resp = server.handle_record_decision(req)
    assert resp.status == "success"
    doc_id = resp.decision_id
    assert doc_id.endswith(".md")
    
    # 2. Ищем его
    search_req = SearchDecisionsRequest(query="integration")
    search_resp = server.handle_search(search_req)
    
    assert search_resp.status == "success"
    assert len(search_resp.results) > 0
    assert search_resp.results[0].id == doc_id
    assert "E2E Strategy" in search_resp.results[0].preview

def test_e2e_supersede_workflow(real_memory):
    """E2E: Полный цикл вытеснения знаний через сервер."""
    server = MCPServer(memory=real_memory, default_role=MCPRole.ADMIN)
    
    # Записываем v1
    r1 = server.handle_record_decision(RecordDecisionRequest(
        title="v1", target="target_area", rationale="Initial version of knowledge base"
    ))
    id1 = r1.decision_id
    
    # Вытесняем v2 (через MCP инструменты используют [via MCP] метку автоматически)
    from agent_memory_server.contracts import SupersedeDecisionRequest
    r2 = server.handle_supersede_decision(SupersedeDecisionRequest(
        title="v2", target="target_area", rationale="Improved version of knowledge base information",
        old_decision_ids=[id1]
    ))
    assert r2.status == "success"
    id2 = r2.decision_id
    
    # Проверяем поиск
    search_resp = server.handle_search(SearchDecisionsRequest(query="knowledge", mode="strict"))
    assert len(search_resp.results) == 1
    assert search_resp.results[0].id == id2
    assert search_resp.results[0].status == "active"
