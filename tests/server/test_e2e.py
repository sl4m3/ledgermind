import pytest
import os
import json
import unittest.mock
from ledgermind.server.server import MCPServer
from ledgermind.core.api.memory import Memory
from ledgermind.server.contracts import RecordDecisionRequest, SearchDecisionsRequest
from ledgermind.server.background import BackgroundWorker

@pytest.fixture
def real_memory(tmp_path):
    storage = str(tmp_path / "e2e_storage")
    return Memory(vector_model="v5-small-text-matching-Q4_K_M.gguf", storage_path=storage)

def test_e2e_record_and_search(real_memory):
    """E2E: Запись через сервер и поиск результата."""
    with unittest.mock.patch.object(BackgroundWorker, "start"):
        server = MCPServer(memory=real_memory)
        
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
        search_req = SearchDecisionsRequest(query="Strategy")
        search_resp = server.handle_search(search_req)
        
        assert search_resp.status == "success"
        assert len(search_resp.results) > 0
        assert search_resp.results[0].id == doc_id
        assert "E2E Strategy" in search_resp.results[0].preview

def test_e2e_supersede_workflow(real_memory):
    """E2E: Полный цикл вытеснения знаний через сервер."""
    with unittest.mock.patch.object(BackgroundWorker, "start"):
        server = MCPServer(memory=real_memory)
    
        # Записываем v1
        r1 = server.handle_record_decision(RecordDecisionRequest(
            title="Knowledge Base v1", target="target_area", rationale="Initial version with proper length"
        ))
        id1 = r1.decision_id
    
        # Вытесняем v2
        from ledgermind.server.contracts import SupersedeDecisionRequest
        r2 = server.handle_supersede_decision(SupersedeDecisionRequest(
            title="Knowledge Base v2", target="target_area", rationale="Improved version with proper length",
            old_decision_ids=[id1]
        ))
        assert r2.status == "success"
        id2 = r2.decision_id
    
        # Проверяем поиск
        search_resp = server.handle_search(SearchDecisionsRequest(query="knowledge", mode="strict"))
        assert len(search_resp.results) == 1
        assert search_resp.results[0].id == id2
        assert search_resp.results[0].status == "active"


