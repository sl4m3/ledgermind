import os
import pytest
import json
from ledgermind.core.api.memory import Memory
from ledgermind.server.server import MCPServer, MCPRole
from ledgermind.server.tools.definitions import LedgerMindTools

@pytest.fixture
def temp_memory(tmp_path):
    storage_path = str(tmp_path / ".ledgermind")
    # Disable git for tests to avoid noise
    memory = Memory(storage_path=storage_path)
    return memory

@pytest.fixture
def mcp_server(temp_memory):
    server = MCPServer(
        memory=temp_memory,
        storage_path=temp_memory.storage_path,
        start_worker=False
    )
    return server

def test_repair_language_logic(mcp_server, temp_memory):
    # 1. Setup preferred language to Russian
    temp_memory.semantic.meta.set_config("preferred_language", "russian")
    
    # 2. Create mock decisions using transactions to avoid integrity triggers mid-setup
    with temp_memory.semantic.transaction():
        # Case A: Russian (Correct)
        res_ru = temp_memory.record_decision(
            title="Тестовое решение",
            target="test_ru",
            rationale="Это обоснование на русском языке с кириллицей."
        )
        fid_ru = res_ru.metadata["file_id"]
        temp_memory.semantic.update_decision(fid_ru, {"enrichment_status": "completed"}, "Mock enrichment")

        # Case B: English (Incorrect, should be reset)
        res_en = temp_memory.record_decision(
            title="English Decision",
            target="test_en",
            rationale="This is a rationale written entirely in English without any cyrillic."
        )
        fid_en = res_en.metadata["file_id"]
        temp_memory.semantic.update_decision(fid_en, {"enrichment_status": "completed"}, "Mock enrichment")

        # Case C: Pending (Should not be touched)
        res_pending = temp_memory.record_decision(
            title="Pending Decision",
            target="test_pending",
            rationale="Another text but status is pending."
        )
        fid_pending = res_pending.metadata["file_id"]

    # 3. Run repair tool
    tools = LedgerMindTools(mcp_server)
    result_json = tools.repair_language()
    result = json.loads(result_json)

    # 4. Assertions
    assert result["status"] == "success"
    
    # Verify statuses in database
    meta_ru = temp_memory.semantic.meta.get_by_fid(fid_ru)
    meta_en = temp_memory.semantic.meta.get_by_fid(fid_en)
    meta_pending = temp_memory.semantic.meta.get_by_fid(fid_pending)

    assert meta_ru["enrichment_status"] == "completed"  # Remained completed
    assert meta_en["enrichment_status"] == "pending"    # RESET TO PENDING!
    assert meta_pending["enrichment_status"] == "pending" # Remained pending

def test_repair_language_to_english(mcp_server, temp_memory):
    # Setup preferred language to English
    temp_memory.semantic.meta.set_config("preferred_language", "english")
    
    with temp_memory.semantic.transaction():
        # Create Russian decision (Incorrect for this config)
        res_ru = temp_memory.record_decision(
            title="Русский заголовок",
            target="test_ru_2",
            rationale="Текст на русском."
        )
        fid_ru = res_ru.metadata["file_id"]
        temp_memory.semantic.update_decision(fid_ru, {"enrichment_status": "completed"}, "Mock enrichment")

    tools = LedgerMindTools(mcp_server)
    tools.repair_language()

    # Verify it was reset
    meta_ru = temp_memory.semantic.meta.get_by_fid(fid_ru)
    assert meta_ru["enrichment_status"] == "pending"
