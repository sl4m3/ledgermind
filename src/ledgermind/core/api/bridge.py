import os
import re
import logging
from typing import List, Optional, Dict, Any
from ledgermind.core.core.schemas import MemoryDecision
from ledgermind.core.api.memory import Memory
from ledgermind.core.stores.semantic_store.loader import MemoryLoader

logger = logging.getLogger(__name__)

class IntegrationBridge:
    """
    High-level bridge for integrating LedgerMind into CLI tools (like gemini-cli).
    Provides streamlined methods for context injection and interaction recording.
    """
    
    def __init__(self, memory_path: str = ".ledgermind", relevance_threshold: float = 0.45, retention_turns: int = 10, vector_model: Optional[str] = None, default_cli: Optional[List[str]] = None, memory_instance: Optional[Memory] = None):
        self.memory_path = os.path.abspath(memory_path)
        if memory_instance:
            self._memory = memory_instance
        else:
            try:
                self._memory = Memory(storage_path=self.memory_path, vector_model=vector_model)
            except Exception as e:
                logger.critical(f"Failed to initialize LedgerMind Core: {e}")
                raise RuntimeError(f"Memory initialization failed. Check permissions for {memory_path}")
            
        self.relevance_threshold = relevance_threshold
        self.retention_turns = retention_turns
        self.default_cli = default_cli or ["gemini"]
        # Maps decision_id -> turn_number when it was last injected
        self._active_context_ids: Dict[str, int] = {}
        self._turn_counter = 0

    def reset_session(self):
        """Clears the session context cache (forgotten injected IDs)."""
        self._active_context_ids.clear()
        self._turn_counter = 0

    def _find_relevant_memories(self, prompt: str, limit: int = 3, exclude_ids: Optional[set[str]] = None) -> List[Dict[str, Any]]:
        """Helper to find memories with exclusion logic."""
        try:
            results = self._memory.search_decisions(prompt, limit=limit, mode="balanced")
            memories = []
            exclude = exclude_ids or set()
            
            for item in results:
                fid = item.get('id')
                if fid in exclude:
                    continue
                    
                score = item.get('score', 0)
                if score >= self.relevance_threshold:
                    memories.append({
                        "id": fid,
                        "title": item.get('title'),
                        "content": item.get('preview')
                    })
            return memories
        except Exception as e:
            logger.error(f"Error searching memories: {e}")
            return []

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
        memories = self._find_relevant_memories(prompt, limit=limit)
        
        if not memories:
            return ""
        
        json_data = json.dumps({
            "source": "ledgermind",
            "memories": memories
        }, indent=2, ensure_ascii=False)
        
        return f"[LEDGERMIND KNOWLEDGE BASE ACTIVE]\n{json_data}"

    # --- Core Interaction Methods ---

    def record_decision(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None, evidence_ids: Optional[List[int]] = None) -> MemoryDecision:
        """Proxies record_decision to memory core with automatic LLM arbitration."""
        arbiter = lambda new_d, old_d: self.arbitrate_with_cli(self.default_cli, new_d, old_d)
        return self._memory.record_decision(title, target, rationale, consequences, evidence_ids=evidence_ids, arbiter_callback=arbiter)

    def supersede_decision(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> MemoryDecision:
        """Proxies supersede_decision to memory core."""
        return self._memory.supersede_decision(title, target, rationale, old_decision_ids, consequences)

    def accept_proposal(self, proposal_id: str) -> MemoryDecision:
        """Proxies accept_proposal to memory core."""
        return self._memory.accept_proposal(proposal_id)

    def reject_proposal(self, proposal_id: str, reason: str):
        """Proxies reject_proposal to memory core."""
        self._memory.reject_proposal(proposal_id, reason)

    def search_decisions(self, query: str, limit: int = 5, mode: str = "balanced") -> List[Dict[str, Any]]:
        """Proxies search_decisions to memory core."""
        return self._memory.search_decisions(query, limit=limit, mode=mode)

    def get_decisions(self) -> List[str]:
        """Proxies get_decisions to memory core."""
        return self._memory.get_decisions()

    def get_decision_history(self, decision_id: str) -> List[Dict[str, Any]]:
        """Proxies get_decision_history to memory core."""
        return self._memory.get_decision_history(decision_id)

    def get_recent_events(self, limit: int = 10, include_archived: bool = False) -> List[Dict[str, Any]]:
        """Proxies get_recent_events to memory core."""
        return self._memory.get_recent_events(limit, include_archived)

    def link_evidence(self, event_id: int, semantic_id: str):
        """Proxies link_evidence to memory core."""
        self._memory.link_evidence(event_id, semantic_id)

    def update_decision(self, decision_id: str, updates: Dict[str, Any], commit_msg: str) -> bool:
        """Proxies update_decision to memory core."""
        return self._memory.update_decision(decision_id, updates, commit_msg)

    def sync_git(self, repo_path: str = ".", limit: int = 20) -> int:
        """Proxies sync_git to memory core."""
        return self._memory.sync_git(repo_path, limit)

    def forget(self, decision_id: str):
        """Proxies forget to memory core."""
        self._memory.forget(decision_id)

    def generate_knowledge_graph(self, target: Optional[str] = None) -> str:
        """Proxies generate_knowledge_graph to memory core."""
        return self._memory.generate_knowledge_graph(target)

    def _strip_knowledge(self, prompt: str) -> str:
        """
        Removes LedgerMind injected context from the prompt to ensure 
        only the user's original query is stored in episodic memory.
        """
        if "[LEDGERMIND KNOWLEDGE BASE ACTIVE]" not in prompt:
            return prompt
            
        # Match the header and the following JSON block
        pattern = r"\[LEDGERMIND KNOWLEDGE BASE ACTIVE\]\n\{.*?\n\}\n+"
        stripped = re.sub(pattern, "", prompt, flags=re.DOTALL)
        return stripped.strip()

    def record_interaction(self, prompt: str, response: str, success: bool = True, metadata: Optional[Dict[str, Any]] = None):
        """
        Records a completed interaction (prompt and response) into episodic memory.
        
        Args:
            prompt: The user's input (will be stripped of injected knowledge).
            response: The agent's output.
            success: Whether the interaction was successful.
            metadata: Optional additional context (e.g. model name, latency).
        """
        try:
            clean_prompt = self._strip_knowledge(prompt)
            # Record prompt
            prompt_dec = self._memory.process_event(
                source="user",
                kind="prompt",
                content=clean_prompt or "(empty prompt)",
                context=metadata or {}
            )
            prompt_id = prompt_dec.metadata.get("event_id")
            
            # Record response (handle empty content to satisfy Pydantic min_length=1)
            safe_response = response.strip() if response else ""
            if not safe_response:
                safe_response = "[SUCCESSFUL EXECUTION WITH NO OUTPUT]" if success else "[FAILED EXECUTION WITH NO OUTPUT]"

            is_error = not success or any(kw in safe_response.lower() for kw in ["error", "failed", "exception", "traceback", "fatal"])
            
            ctx = {
                "layer": "cli_integration",
                "success": not is_error,
                "parent_event_id": prompt_id
            }
            if metadata:
                ctx.update(metadata)

            # Try to parse as JSON and extract separated events
            try:
                import json
                import os
                if safe_response.startswith("{") or safe_response.startswith("["):
                    data = json.loads(safe_response)
                    # Support for structured payloads containing transcript paths
                    if isinstance(data, dict) and "transcript_path" in data and os.path.exists(data["transcript_path"]):
                        with open(data["transcript_path"], 'r', encoding='utf-8') as f:
                            transcript = json.load(f)
                        turns = transcript.get("messages", transcript.get("turns", []))
                        last_user_idx = -1
                        for i in range(len(turns) - 1, -1, -1):
                            if turns[i].get("type") == "user" or turns[i].get("role") == "user":
                                last_user_idx = i
                                break
                        agent_turns = turns[last_user_idx + 1:] if last_user_idx != -1 else ([turns[-1]] if turns else [])
                        
                        events_recorded = 0
                        for t in agent_turns:
                            if t.get("type") in ["gemini", "agent", "assistant"] or t.get("role") in ["assistant", "agent", "gemini"]:
                                text_c = t.get("content", "").strip()
                                if text_c:
                                    self._memory.process_event(source="agent", kind="result", content=text_c, context=ctx)
                                    events_recorded += 1
                                for tc in t.get("toolCalls", []) + t.get("tool_calls", []):
                                    name = tc.get("name", "unknown")
                                    status = tc.get("status", "unknown")
                                    args_str = json.dumps(tc.get("args", {}), ensure_ascii=False)
                                    res_str = tc.get("resultDisplay", "")
                                    if not res_str and tc.get("result"):
                                        res_str = json.dumps(tc.get("result"), ensure_ascii=False)
                                    tc_content = f"Tool: {name}\\nStatus: {status}\\nArgs: {args_str}\\nResult:\\n{res_str}"
                                    self._memory.process_event(source="agent", kind="call", content=tc_content, context=ctx)
                                    events_recorded += 1
                        
                        if events_recorded > 0:
                            return  # Successfully separated events, skip raw recording

            except Exception as e:
                logger.debug(f"Could not parse response as structured events: {e}")

            self._memory.process_event(
                source="agent",
                kind="result",
                content=safe_response,
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
            # We use a longer timeout for arbitration in Termux/mobile environments
            result = subprocess.run(
                cli_command + [prompt], 
                capture_output=True, text=True, encoding='utf-8', timeout=180
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
        High-level orchestration with SLIDING WINDOW CONTEXT DEDUPLICATION:
        1. Manages turn counter and prunes old context from cache.
        2. Injects NEW context (ONLY if previous context has exited the window).
        3. Executes external command.
        4. Records interaction.
        """
        import subprocess
        import sys
        import json
        
        self._turn_counter += 1
        
        # Prune old memories from cache based on retention_turns
        cutoff = self._turn_counter - self.retention_turns
        # Keep only memories injected within the retention window
        active_ids = {k for k, v in self._active_context_ids.items() if v > cutoff}
        self._active_context_ids = {k: v for k, v in self._active_context_ids.items() if k in active_ids}
        
        # 1. Get Context (Strict Window: only inject if context window is empty)
        memories = []
        if not active_ids:
            memories = self._find_relevant_memories(user_prompt)
        
        context_str = ""
        if memories:
            # Add to active cache with current turn number
            for m in memories:
                self._active_context_ids[m['id']] = self._turn_counter
                
            json_data = json.dumps({
                "source": "ledgermind",
                "memories": memories
            }, indent=2, ensure_ascii=False)
            context_str = f"[LEDGERMIND KNOWLEDGE BASE ACTIVE]\n{json_data}"
        
        # 2. Prepare Augmented Prompt
        augmented_prompt = f"{context_str}\n\n{user_prompt}" if context_str else user_prompt
        
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
