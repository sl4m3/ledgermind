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

    def record_interaction(self, prompt: str, response: str, success: bool = True, metadata: Optional[Dict[str, Any]] = None):
        """
        Records a completed interaction (prompt and response) into episodic memory.
        
        Args:
            prompt: The user's input.
            response: The agent's output.
            success: Whether the interaction was successful.
            metadata: Optional additional context (e.g. model name, latency).
        """
        try:
            # Record prompt
            prompt_dec = self._memory.process_event(
                source="user",
                kind="prompt",
                content=prompt,
                context=metadata or {}
            )
            prompt_id = prompt_dec.metadata.get("event_id")
            
            # Record response
            is_error = not success or any(kw in response.lower() for kw in ["error", "failed", "exception", "traceback", "fatal"])
            
            ctx = {
                "layer": "cli_integration",
                "success": not is_error,
                "parent_event_id": prompt_id
            }
            if metadata:
                ctx.update(metadata)

            self._memory.process_event(
                source="agent",
                kind="result",
                content=response,
                context=ctx
            )
        except Exception as e:
            logger.error(f"Error recording interaction: {e}")

    def arbitrate_with_cli(self, cli_command: List[str], new_proposal: Dict[str, Any], old_decision: Dict[str, Any]) -> str:
        """
        Uses the provided CLI to decide if a new proposal should supersede an old decision.
        Returns: "SUPERSEDE", "CONFLICT", or "UNKNOWN"
        """
        import subprocess
        
        prompt = (
            "You are a knowledge evolution arbiter. Determine if the NEW PROPOSAL "
            "should supersede (replace) the OLD DECISION or if they are distinct (conflict).\n\n"
            f"OLD DECISION:\nTitle: {old_decision.get('title')}\nRationale: {old_decision.get('rationale')}\n\n"
            f"NEW PROPOSAL:\nTitle: {new_proposal.get('title')}\nRationale: {new_proposal.get('rationale')}\n\n"
            "Rule: If the new proposal is an update, refinement, or replacement of the same logic, return 'SUPERSEDE'. "
            "If they describe different things or have a fundamental contradiction that needs human eyes, return 'CONFLICT'.\n"
            "Respond ONLY with the word 'SUPERSEDE' or 'CONFLICT'."
        )
        
        try:
            # We use a short timeout for arbitration
            result = subprocess.run(
                cli_command + [prompt], 
                capture_output=True, text=True, encoding='utf-8', timeout=30
            )
            response = result.stdout.strip().upper()
            if "SUPERSEDE" in response: return "SUPERSEDE"
            if "CONFLICT" in response: return "CONFLICT"
            return "UNKNOWN"
        except Exception as e:
            logger.error(f"Arbitration failed: {e}")
            return "ERROR"

    def execute_with_memory(self, command_args: List[str], user_prompt: str, stream: bool = True) -> str:
        """
        High-level orchestration:
        1. Injects context from LedgerMind.
        2. Executes the external CLI command with real-time streaming.
        3. Records everything to episodic memory.
        """
        import subprocess
        import sys
        from ledgermind.core.core.exceptions import ConflictError
        
        # 1. Get Context
        context = self.get_context_for_prompt(user_prompt)
        
        # 2. Prepare Augmented Prompt
        augmented_prompt = f"{context}\n\n{user_prompt}" if context else user_prompt
        
        # 3. Execute CLI with Streaming
        cmd = command_args + [augmented_prompt]
        start_time = __import__("time").time()
        
        full_response = []
        try:
            # Use Popen to allow real-time output
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                encoding='utf-8',
                bufsize=1 # Line buffered
            )
            
            # Stream output to terminal and buffer
            if stream:
                for line in process.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    full_response.append(line)
            else:
                full_response = [process.stdout.read()]
                
            process.wait()
            response = "".join(full_response)
            success = process.returncode == 0
        except Exception as e:
            response = f"Execution Error: {str(e)}"
            success = False
            
        latency = __import__("time").time() - start_time
        
        # 4. Record to Memory
        try:
            self.record_interaction(
                prompt=user_prompt, 
                response=response, 
                success=success,
                metadata={"latency": latency, "command": " ".join(command_args)}
            )
        except Exception as e:
            logger.error(f"Error recording to memory: {e}")

        return response

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
