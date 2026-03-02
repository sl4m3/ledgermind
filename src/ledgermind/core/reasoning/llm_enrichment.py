import logging
import json
import httpx
import os
import subprocess
from typing import Dict, Any, Optional, List
from ledgermind.core.core.schemas import ProposalContent, ProceduralContent

logger = logging.getLogger("ledgermind.core.reasoning.enrichment")

class LLMEnricher:
    """
    Enriches machine-generated proposals into human-readable text
    using local or remote LLMs based on the selected arbitration mode.
    """
    
    def __init__(self, mode: str = "lite", client_name: str = "none", model_name: Optional[str] = None):
        self.mode = mode.lower()
        self.client_name = client_name.lower()
        self.model_name = model_name
        self.client = httpx.Client(timeout=60.0)

    def synthesize_merged_rationale(self, rationales: List[str]) -> str:
        """
        Synthesizes multiple rationales into a single coherent technical decision.
        """
        if self.mode == "lite" or not rationales:
            return "\n\n".join(rationales)

        # Build prompt for merging
        combined_text = ""
        for i, rat in enumerate(rationales):
            combined_text += f"HYPOTHESIS {i+1}:\n---\n{rat}\n---\n\n"

        prompt = (
            "You are a Senior Principal Engineer. I am merging multiple semantically identical hypotheses into one canonical decision.\n"
            "Analyze the rationales below and synthesize them into a single, high-quality, non-redundant architectural guide.\n\n"
            f"{combined_text}"
            "RESPONSE FORMAT (STRICT):\n"
            "1. <goal>One sentence summary of the unified intent.</goal>\n"
            "2. <rationale>Full, detailed unified architectural rationale. Merge logic, resolve contradictions, keep it professional.</rationale>\n"
            "3. <compressive>Exactly 3 sentences summarizing the final state.</compressive>\n\n"
            "Ensure technical terms remain in English. Output must be in the same language as the input rationales."
        )

        try:
            response_text = None
            if self.mode == "optimal":
                response_text = self._call_model(prompt, use_local=True)
            elif self.mode == "rich":
                response_text = self._call_cli_model(prompt)
                if not response_text:
                    response_text = self._call_model(prompt, use_local=False)

            if response_text:
                import re
                rationale_match = re.search(r'<rationale>(.*?)</rationale>', response_text, re.DOTALL | re.IGNORECASE)
                if rationale_match:
                    return rationale_match.group(1).strip()
        except Exception as e:
            logger.warning(f"Rationale synthesis failed: {e}")

        return "\n\n".join(rationales)

    def process_batch(self, memory: Any) -> List[Dict[str, Any]]:
        """
        Scans semantic store for proposals pending enrichment and processes them iteratively.
        Returns a list of processed results: [{"fid": str, "status": str, "events": int}]
        """
        results = []
        if self.mode == "lite":
            return results

        # 1. Find pending proposals via direct SQLite query
        db_path = os.path.abspath(os.path.join(memory.semantic.repo_path, "semantic_meta.db"))
        # ... (rest of search logic)
        logger.info(f"Enrichment: Checking database at {db_path}")
        if not os.path.exists(db_path):
            logger.warning(f"Enrichment: Database not found at {db_path}")
            return

        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            # Find any record with pending enrichment
            query = "SELECT fid FROM semantic_meta WHERE (enrichment_status = 'pending' OR status = 'draft') AND kind = 'proposal' LIMIT 10"
            rows = conn.execute(query).fetchall()
            pending_fids = [row[0] for row in rows]
            conn.close()
        except Exception as e:
            logger.error(f"Failed to query enrichment queue: {e}")
            return

        if not pending_fids:
            return

        # Update client and model from config if not provided
        if self.client_name == "none":
            self.client_name = memory.semantic.meta.get_config("client", "none").lower()
        
        if self.model_name is None:
            self.model_name = memory.semantic.meta.get_config("enrichment_model")

        logger.info(f"Enrichment: Found {len(pending_fids)} tasks (mode={self.mode}, client={self.client_name}, model={self.model_name or 'default'}).")

        for fid in pending_fids:
            try:
                # Load full proposal
                from ledgermind.core.stores.semantic_store.loader import MemoryLoader
                from ledgermind.core.core.schemas import ProposalContent, DecisionStream
                
                file_path = os.path.abspath(os.path.join(memory.semantic.repo_path, fid))
                if not os.path.exists(file_path): continue
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                data, body = MemoryLoader.parse(content)
                if not data: continue
                
                proposal_data = data.get('context', {})
                if not proposal_data: continue
                
                # Determine object type
                if 'decision_id' in proposal_data:
                    proposal = DecisionStream(**proposal_data)
                else:
                    proposal = ProposalContent(**proposal_data)

                # --- ITERATIVE CHUNKING LOGIC ---
                all_ids = sorted(proposal.evidence_event_ids or [])
                
                # If no logs to process, just mark as completed
                if not all_ids:
                    with memory.semantic.transaction():
                        memory.semantic.update_decision(fid, {"enrichment_status": "completed"}, "Enrichment: No evidence to process.")
                    logger.info(f"Enrichment: No evidence for {fid}. Completed.")
                    continue

                # Process in chunks of 50
                CHUNK_SIZE = 50
                processed_in_this_run = 0
                
                status = "pending"
                while True:
                    current_ids = all_ids[:CHUNK_SIZE]
                    remaining_ids = all_ids[CHUNK_SIZE:]
                    
                    # Last chunk is determined at the start of iteration
                    is_last_chunk = len(remaining_ids) == 0
                    
                    cluster_logs = None
                    if current_ids:
                        events = memory.episodic.get_by_ids(current_ids)
                        log_entries = []
                        for ev in events:
                            # NO TRUNCATION as requested
                            log_entries.append(f"[{ev['kind'].upper()}] {ev['content']}")
                        cluster_logs = "\n".join(log_entries)

                    # Call LLM
                    old_rationale = str(proposal.rationale)
                    proposal = self.enrich_proposal(proposal, cluster_logs=cluster_logs, file_path=file_path, memory=memory)
                    
                    # Verification: Did anything change?
                    if str(proposal.rationale) == old_rationale:
                        logger.warning(f"Enrichment: LLM returned identical rationale for {fid}. Breaking cycle.")
                        # If it's the only chunk, we might as well mark it finished to avoid infinite loops
                        if is_last_chunk: status = "completed"
                        else: status = "pending"
                        break

                    # Update local state
                    proposal.evidence_event_ids = remaining_ids
                    
                    status = "pending"
                    if is_last_chunk:
                        status = "completed"
                    
                    # Update metadata
                    updates = {
                        "title": proposal.title,
                        "content": proposal.title,
                        "rationale": proposal.rationale,
                        "compressive_rationale": proposal.compressive_rationale,
                        "enrichment_status": status,
                        "evidence_event_ids": proposal.evidence_event_ids,
                        "total_evidence_count": (getattr(proposal, 'total_evidence_count', 0) or 0) + len(current_ids)
                    }

                    # Save intermediate or final progress
                    with memory.semantic.transaction():
                        memory.semantic.update_decision(
                            fid,
                            updates,
                            f"Enrichment iteration ({status})"
                        )
                    
                    processed_in_this_run += len(current_ids)
                    all_ids = remaining_ids
                    
                    if is_last_chunk or is_procedural:
                        break
                    
                    if processed_in_this_run >= 500: # Safety break for very large files
                        break

                if status == "completed":
                    # Extra safety: update enrichment_status in case break happened before update
                    with memory.semantic.transaction():
                        memory.semantic.update_decision(fid, {"enrichment_status": "completed"}, "Finalizing enrichment")

                logger.info(f"Enrichment: Processed {processed_in_this_run} events for {fid}. Final Status: {status}")
                results.append({"fid": fid, "status": status, "events": processed_in_this_run})

            except Exception as e:
                logger.error(f"Failed to enrich proposal {fid}: {e}")
        
        return results

    def enrich_proposal(self, proposal: Any, cluster_logs: Optional[str] = None, file_path: Optional[str] = None, memory: Any = None) -> Any:
        """
        Takes a raw distilled proposal and converts it into a meaningful summary using event logs.
        """
        if self.mode == "lite" or not cluster_logs:
            return proposal
            
        prompt = self._build_enrichment_prompt(proposal.target, cluster_logs, existing_rationale=proposal.rationale)
        
        try:
            response_text = None
            if self.mode == "optimal":
                response_text = self._call_model(prompt, use_local=True)
            elif self.mode == "rich":
                response_text = self._call_cli_model(prompt)
                if not response_text:
                    response_text = self._call_model(prompt, use_local=False)

            if response_text:
                import re
                goal_match = re.search(r'<goal>(.*?)</goal>', response_text, re.DOTALL | re.IGNORECASE)
                rationale_match = re.search(r'<rationale>(.*?)</rationale>', response_text, re.DOTALL | re.IGNORECASE)
                compressive_match = re.search(r'<compressive>(.*?)</compressive>', response_text, re.DOTALL | re.IGNORECASE)
                
                if goal_match:
                    proposal.title = goal_match.group(1).strip()
                if rationale_match:
                    proposal.rationale = rationale_match.group(1).strip()
                if compressive_match:
                    display_path = file_path if file_path else (proposal.decision_id if hasattr(proposal, 'decision_id') else 'this file')
                    path_note = f"\n\n*Technical Note: Full logs available via 'cat {display_path}'. Do not use read_file.*"
                    proposal.compressive_rationale = compressive_match.group(1).strip() + path_note
                    
        except Exception as e:
            logger.warning(f"LLM Enrichment failed: {e}")

        return proposal

    def _build_enrichment_prompt(self, target: str, logs: str, existing_rationale: Optional[str] = None) -> str:
        context_part = ""
        if existing_rationale and "Observed emerging activity" not in existing_rationale and "Analysis of raw logs" not in existing_rationale:
            context_part = (
                "CURRENT DETAILED RATIONALE:\n"
                "--------------------------\n"
                f"{existing_rationale}\n"
                "--------------------------\n\n"
                "The logs below are NEW technical activities. Integrate them into the rationale.\n"
            )

        return (
            f"You are a Principal Software Engineer. Analyze these raw execution logs for '{target}' and update the knowledge record.\n\n"
            f"{context_part}"
            "EXECUTION LOGS:\n"
            f"{logs}\n\n"
            "RESPONSE FORMAT (STRICT):\n"
            "1. <goal>One sentence summary of the technical intent or outcome.</goal>\n"
            "2. <rationale>Comprehensive architectural rationale. Describe the steps, decisions, and patterns discovered in the logs.</rationale>\n"
            "3. <compressive>Exactly 3 sentences summarizing the technical state for quick context injection.</compressive>\n\n"
            "Ensure all technical terms remain in English. Output must be in the same language as the context or logs."
        )

    def _call_cli_model(self, prompt: str) -> Optional[str]:
        """
        Attempts to use an already authorized CLI client like gemini or claude.
        Uses a temporary file buffer for maximum reliability in Termux/Mobile.
        """
        import tempfile
        import uuid
        
        prompt_file = os.path.join(tempfile.gettempdir(), f"lm_prompt_{uuid.uuid4().hex[:8]}.txt")
        response_file = os.path.join(tempfile.gettempdir(), f"lm_res_{uuid.uuid4().hex[:8]}.txt")
        
        try:
            # Write prompt to buffer
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(prompt)
            
            if self.client_name == "gemini":
                # Use --non-interactive and pipe from /dev/null to prevent hangs
                # Use larger timeout (300s) for full logs processing
                cmd = f"gemini --model {self.model_name or 'gemini-2.5-flash-lite'} --prompt \"$(cat {prompt_file})\" < /dev/null > {response_file} 2>&1"
                subprocess.run(cmd, shell=True, check=True, timeout=300) # nosec B602
                
            elif self.client_name == "claude":
                cmd = f"claude \"$(cat {prompt_file})\" < /dev/null > {response_file} 2>&1"
                subprocess.run(cmd, shell=True, check=True, timeout=300) # nosec B602
            
            # Read response from buffer
            if os.path.exists(response_file):
                with open(response_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    logger.debug(f"CLI ({self.client_name}) Raw Output (first 100 chars): {content[:100]}...")
                    # Filter out possible CLI headers
                    if "Loaded cached credentials" in content:
                        lines = content.split("\n")
                        content = "\n".join([l for l in lines if "Loaded cached" not in l and "Listening for changes" not in l]).strip()
                    return content
                
        except Exception as e:
            logger.debug(f"Buffered CLI enrichment failed for {self.client_name}: {e}")
        finally:
            # Cleanup
            for f in [prompt_file, response_file]:
                if os.path.exists(f): 
                    try: os.remove(f)
                    except OSError: pass
        
        return None

    def _call_model(self, prompt: str, use_local: bool = True) -> Optional[str]:
        """Unified method for local (Ollama) or remote (OpenAI) API calls."""
        try:
            if use_local:
                url = os.getenv("LEDGERMIND_OPTIMAL_URL", "http://localhost:11434/v1/chat/completions")
                model = os.getenv("LEDGERMIND_OPTIMAL_MODEL", "llama3")
                headers = {}
            else:
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key: return None
                url = "https://api.openai.com/v1/chat/completions"
                model = "gpt-4o-mini"
                headers = {"Authorization": f"Bearer {api_key}"}

            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3
            }
            
            response = self.client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.debug(f"API call failed: {e}")
            return None
