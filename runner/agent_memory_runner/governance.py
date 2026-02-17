import os
from typing import List, Optional
from agent_memory_core.api.memory import Memory

class GovernanceEngine:
    INIT_PROTOCOL = """
--- [SESSION START: PERSISTENT CONTEXT ACTIVE] ---
System: Audit Layer initialized. Memory Governance: Level 3 (Dynamic).
Rule: Formalize key findings with MEMORY: {{json}} marker.
-------------------------------------------------
"""

    TURN_PROTOCOL = """
[MEMORY SNAPSHOT (Relevant to your next task)]:
{context}
[USER QUERY]: """

    def __init__(self, memory_path: str):
        self.memory_path = os.path.abspath(memory_path)
        self._memory_instance = None

    @property
    def memory(self):
        if self._memory_instance is None:
            self._memory_instance = Memory(storage_path=self.memory_path)
        return self._memory_instance

    def fetch_relevant_context(self, query: str) -> str:
        """Perform semantic search based on user input."""
        try:
            results = self.memory.search_decisions(query, limit=5, mode="balanced")
            if not results:
                return "No specific related records found. Maintain general consistency."

            lines = []
            for item in results:
                lines.append(f"• {item.preview} (ID: {item.id}, Score: {item.score:.2f})")
            return "\n".join(lines)
        except Exception as e:
            return f"Memory retrieval paused: {e}"

    def transform_input(self, user_data: bytes) -> bytes:
        """Transforms user input by injecting relevant memory context."""
        try:
            query = user_data.decode('utf-8', errors='ignore').strip()
            if len(query) < 3:
                return user_data
            
            context = self.fetch_relevant_context(query)
            full_payload = self.TURN_PROTOCOL.format(context=context) + query + "\n"
            return full_payload.encode('utf-8')
        except Exception:
            return user_data

    def get_init_payload(self) -> bytes:
        return self.INIT_PROTOCOL.encode('utf-8')
