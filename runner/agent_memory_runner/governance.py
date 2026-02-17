import os
from typing import List, Optional
from functools import lru_cache
from agent_memory_core.api.memory import Memory
from agent_memory_core.stores.semantic_store.loader import MemoryLoader

class GovernanceEngine:
    INIT_PROTOCOL = """
--- [SESSION START: PERSISTENT CONTEXT ACTIVE] ---
System: Audit Layer initialized. Memory Governance: Level 3 (Dynamic).
Rule 1: Use the [VERIFIED KNOWLEDGE BASE] block to maintain consistency with established project decisions.
Rule 2: If you reach a significant, non-obvious conclusion or establish a new architectural pattern that should persist across sessions, use 'record_decision'. Avoid recording trivial or temporary information.
Rule 3: Do not repeat information already present in the [VERIFIED KNOWLEDGE BASE].
-------------------------------------------------
"""

    def __init__(self, memory_path: str, cooldown_limit: int = 100):
        self.memory_path = os.path.abspath(memory_path)
        self._memory_instance = None
        # Cooldown period in seconds (6 hours)
        self.cooldown_seconds = 6 * 3600
        self.relevance_threshold = 0.55  # Filter out low-relevance results
        self._session_injected = set() # Track what we injected this session

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
        """Checks if this knowledge was recently injected (6h window)."""
        # Session reset: if we haven't injected it THIS session, we might allow it
        # even if it's in episodic memory (if user restarted the client).
        if fid in self._session_injected:
            return True

        try:
            from datetime import datetime
            # We check recent events to see if it was injected in the last 6 hours
            recent = self.memory.get_recent_events(limit=50) # Look back far enough
            now = datetime.now()
            
            for ev in recent:
                if ev.get('kind') == "context_injection":
                    ctx = ev.get('context', {})
                    if ctx.get('fid') == fid:
                        # Extract timestamp from content: "fid @ ISO_TIMESTAMP"
                        content = ev.get('content', "")
                        if "@" in content:
                            ts_str = content.split("@")[1].strip()
                            ts = datetime.fromisoformat(ts_str)
                            if (now - ts).total_seconds() < self.cooldown_seconds:
                                return True
        except Exception: pass
        return False

    def _record_injection(self, fid: str):
        """Records the injection event to manage cooldown."""
        try:
            from datetime import datetime
            self._session_injected.add(fid)
            self.memory.process_event(
                source="runner",
                kind="context_injection",
                content=f"{fid} @ {datetime.now().isoformat()}",
                context={"layer": "governance", "fid": fid}
            )
        except Exception: pass

    def fetch_relevant_context(self, query: str) -> str:
        try:
            results = self.memory.search_decisions(query, limit=5, mode="balanced")
            if not results:
                return ""

            blocks = []
            injected_ids = []
            
            for item in results:
                fid = item.get('id')
                score = item.get('score', 0)
                
                # Relevance threshold check
                if score < self.relevance_threshold:
                    continue

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
            # Threshold increased to 20 and must contain a space to avoid 
            # injecting during interactive selections/short answers.
            if len(query) < 20 or " " not in query:
                return b""
            
            context = self.fetch_relevant_context(query)
            
            if not context:
                return b""

            # Readable multi-line format with authoritative header
            header = "\n\n[VERIFIED KNOWLEDGE BASE]:\n"
            footer = "\n[END KNOWLEDGE BASE]\n"
            return (header + context + footer).encode('utf-8')
        except Exception:
            return b""

    def get_init_payload(self) -> bytes:
        return self.INIT_PROTOCOL.encode('utf-8')
