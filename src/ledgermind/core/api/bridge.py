import os
import re
import logging
from typing import List, Optional, Dict, Any
from ledgermind.core.api.memory import Memory
from ledgermind.core.stores.semantic_store.loader import MemoryLoader

logger = logging.getLogger(__name__)

class IntegrationBridge:
    """
    High-level bridge for integrating LedgerMind into CLI tools (like gemini-cli).
    Provides streamlined methods for context injection and interaction recording.
    """
    
    def __init__(self, memory_path: str = ".ledgermind", relevance_threshold: float = 0.35):
        self.memory_path = os.path.abspath(memory_path)
        try:
            self._memory = Memory(storage_path=self.memory_path)
        except Exception as e:
            logger.critical(f"Failed to initialize LedgerMind Core: {e}")
            raise RuntimeError(f"Memory initialization failed. Check permissions for {memory_path}")
            
        self.relevance_threshold = relevance_threshold

    def check_health(self) -> Dict[str, Any]:
        """
        Runs a full health check on the memory system.
        Useful for diagnostic commands in CLI.
        """
        return self._memory.check_environment()

    def get_context_for_prompt(self, prompt: str, limit: int = 3) -> str:
        """
        Retrieves and formats relevant context for a given user prompt.
        Returns a structured JSON string with a prefix for agent consumption.
        """
        import json
        try:
            results = self._memory.search_decisions(prompt, limit=limit, mode="balanced")
            memories = []
            
            for item in results:
                fid = item.get('id')
                score = item.get('score', 0)
                
                if score >= self.relevance_threshold:
                    # Get additional meta from DB
                    meta = self._memory.semantic.meta.get_by_fid(fid)
                    
                    # Use formatted content to include rationale and other details
                    full_content = self._get_formatted_decision(fid)
                    
                    memories.append({
                        "id": fid,
                        "title": item.get('title'),
                        "target": item.get('target'),
                        "kind": item.get('kind'),
                        "score": round(score, 3),
                        "recency": meta.get('timestamp') if meta else None,
                        "content": full_content or item.get('preview', "")
                    })
            
            if not memories:
                return ""
            
            json_data = json.dumps({
                "source": "ledgermind",
                "memories": memories
            }, indent=2, ensure_ascii=False)
            
            return f"[LEDGERMIND KNOWLEDGE BASE ACTIVE]\n{json_data}"
            
        except Exception as e:
            logger.error(f"Error fetching context: {e}")
            return ""

    def record_interaction(self, prompt: str, response: str, success: bool = True):
        """
        Records a completed interaction (prompt and response) into episodic memory.
        
        Args:
            prompt: The user's input.
            response: The agent's output.
            success: Whether the interaction was successful.
        """
        try:
            # Record prompt
            prompt_dec = self._memory.process_event(
                source="user",
                kind="prompt",
                content=prompt
            )
            prompt_id = prompt_dec.metadata.get("event_id")
            
            # Record response
            is_error = not success or any(kw in response.lower() for kw in ["error", "failed", "exception", "traceback", "fatal"])
            
            self._memory.process_event(
                source="agent",
                kind="result",
                content=response,
                context={
                    "layer": "cli_integration",
                    "success": not is_error,
                    "parent_event_id": prompt_id
                }
            )
        except Exception as e:
            logger.error(f"Error recording interaction: {e}")

    def trigger_reflection(self):
        """
        Manually triggers the reflection process to distill episodic memories into semantic knowledge.
        """
        try:
            self._memory.run_reflection()
        except Exception as e:
            logger.error(f"Reflection error: {e}")

    def run_maintenance(self) -> Dict[str, Any]:
        """
        Runs maintenance tasks like knowledge decay and merging.
        Returns a report of the actions taken.
        """
        try:
            return self._memory.run_maintenance()
        except Exception as e:
            logger.error(f"Maintenance error: {e}")
            return {"status": "error", "message": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """
        Returns basic statistics about the memory system.
        """
        try:
            semantic_count = 0
            if os.path.exists(self._memory.semantic.repo_path):
                for root, _, filenames in os.walk(self._memory.semantic.repo_path):
                    if ".git" in root or ".tx_backup" in root: continue
                    semantic_count += len([f for f in filenames if f.endswith(".md") or f.endswith(".yaml")])

            return {
                "episodic_count": self._memory.episodic.count_events() if hasattr(self._memory.episodic, 'count_events') else "unknown",
                "semantic_count": semantic_count,
                "vector_count": len(self._memory.vector._doc_ids) if self._memory.vector else 0,
                "health": self.check_health()
            }
        except Exception as e:
            logger.error(f"Error fetching stats: {e}")
            return {"status": "error", "message": str(e)}

    def _get_formatted_decision(self, fid: str) -> Optional[str]:
        """Loads and formats a specific decision file."""
        file_path = os.path.join(self._memory.semantic.repo_path, fid)
        if not os.path.exists(file_path):
            return None
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                data, body = MemoryLoader.parse(content)
                ctx = data.get("context", {})
                title = ctx.get("title", "Document")
                rationale = ctx.get("rationale", "")
                
                formatted = f"### {title}\n"
                if rationale:
                    formatted += f"**Rationale:** {rationale}\n"
                formatted += body.strip()
                return formatted
        except Exception as e:
            logger.warning(f"Failed to load decision {fid}: {e}")
            return None

    @property
    def memory(self) -> Memory:
        return self._memory
