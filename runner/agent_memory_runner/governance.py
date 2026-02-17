import os
from typing import List, Optional
from functools import lru_cache
from agent_memory_core.api.memory import Memory
from agent_memory_core.stores.semantic_store.loader import MemoryLoader

class GovernanceEngine:
    INIT_PROTOCOL = """
--- [SESSION START: PERSISTENT CONTEXT ACTIVE] ---
System: Audit Layer initialized. Memory Governance: Level 3 (Dynamic).
Rule 1: Use the [VERIFIED KNOWLEDGE BASE] block to ensure consistency with past decisions.
Rule 2: If you encounter new patterns or reach a significant conclusion NOT in the knowledge base, 
        PROACTIVELY use 'record_decision' to persist it for future sessions.
Rule 3: Avoid repeating information already present in the [VERIFIED KNOWLEDGE BASE].
-------------------------------------------------
"""

    def __init__(self, memory_path: str, cooldown_limit: int = 15):
        self.memory_path = os.path.abspath(memory_path)
        self._memory_instance = None
        self.cooldown_limit = cooldown_limit

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

    def _is_on_cooldown(self, fid: str) -> bool:
        """Checks if this knowledge was recently injected using episodic memory."""
        try:
            recent = self.memory.get_recent_events(limit=self.cooldown_limit)
            for ev in recent:
                if ev.get('kind') == "context_injection" and ev.get('content') == fid:
                    return True
        except Exception: pass
        return False

    def _record_injection(self, fid: str):
        """Records the injection event to manage cooldown."""
        try:
            # We add a timestamp to content to bypass the duplicate check if needed,
            # though for cooldown the duplicate check actually helps us 
            # (if it's a duplicate, it's definitely on cooldown).
            self.memory.process_event(
                source="runner",
                kind="context_injection",
                content=fid,
                context={"layer": "governance"}
            )
        except Exception: pass

    @lru_cache(maxsize=128)
    def fetch_relevant_context(self, query: str) -> str:
        try:
            results = self.memory.search_decisions(query, limit=5, mode="balanced")
            if not results:
                return ""

            blocks = []
            injected_ids = []
            
            for item in results:
                fid = item.get('id')
                if self._is_on_cooldown(fid):
                    continue
                
                content = self._get_file_content(fid)
                if content:
                    blocks.append(content)
                    injected_ids.append(fid)
                
                if len(blocks) >= 3: # Keep injection concise
                    break
            
            if not blocks:
                return ""

            # Mark as injected to trigger cooldown
            for fid in injected_ids:
                self._record_injection(fid)
                
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
                # If no context found, occasionally nudge the agent to create some
                import random
                if random.random() < 0.1: # 10% chance to nudge
                    return b"\n\n[SYSTEM NOTE]: No relevant verified knowledge found for this query. If this leads to a new insight, please 'record_decision'.\n"
                return b""

            # Readable multi-line format with authoritative header
            header = "\n\n[VERIFIED KNOWLEDGE BASE]:\n"
            footer = "\n[END KNOWLEDGE BASE]\n"
            return (header + context + footer).encode('utf-8')
        except Exception:
            return b""

    def get_init_payload(self) -> bytes:
        return self.INIT_PROTOCOL.encode('utf-8')
