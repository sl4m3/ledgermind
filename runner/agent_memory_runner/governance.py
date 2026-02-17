import os
from typing import List, Optional
from functools import lru_cache
from agent_memory_core.api.memory import Memory
from agent_memory_core.stores.semantic_store.loader import MemoryLoader

class GovernanceEngine:
    INIT_PROTOCOL = """
--- [SESSION START: PERSISTENT CONTEXT ACTIVE] ---
System: Audit Layer initialized. Memory Governance: Level 3 (Dynamic).
Rule: Use the [INJECTED KNOWLEDGE] block provided in the prompt to answer questions.
-------------------------------------------------
"""

    def __init__(self, memory_path: str):
        self.memory_path = os.path.abspath(memory_path)
        self._memory_instance = None

    @property
    def memory(self):
        if self._memory_instance is None:
            self._memory_instance = Memory(storage_path=self.memory_path)
        return self._memory_instance

    def _get_file_content(self, filename: str) -> str:
        file_path = os.path.join(self.memory_path, "semantic", filename)
        if not os.path.exists(file_path):
            return ""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data, _ = MemoryLoader.parse(f.read())
                ctx = data.get("context", {})
                title = ctx.get("title", "Untitled")
                rationale = ctx.get("rationale", "")
                return f"• {title}\n  Rationale: {rationale}"
        except Exception:
            return ""

    @lru_cache(maxsize=128)
    def fetch_relevant_context(self, query: str) -> str:
        try:
            results = self.memory.search_decisions(query, limit=3, mode="balanced")
            if not results:
                return ""

            blocks = []
            for item in results:
                fid = item.get('id')
                content = self._get_file_content(fid)
                if content:
                    blocks.append(content)
            
            return "\n".join(blocks)
        except Exception:
            return ""

    def transform_input(self, user_data: bytes) -> bytes:
        try:
            query = user_data.decode('utf-8', errors='ignore').strip()
            if len(query) < 4:
                return b""
            
            context = self.fetch_relevant_context(query)
            if not context:
                return b""

            # Readable multi-line format with authoritative header
            return f"\n\n[VERIFIED KNOWLEDGE BASE]:\n{context}\n[END KNOWLEDGE BASE]\n".encode('utf-8')
        except Exception:
            return b""

    def get_init_payload(self) -> bytes:
        return self.INIT_PROTOCOL.encode('utf-8')
