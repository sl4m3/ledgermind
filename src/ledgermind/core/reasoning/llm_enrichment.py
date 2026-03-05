import logging
import httpx
import os
import subprocess
from typing import Any, Optional

logger = logging.getLogger(__name__)

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

    def process_batch(self, memory: Any):
        """
        Scans semantic store for proposals pending enrichment and processes them iteratively.
        """
        if self.mode == "lite":
            return

        # 1. Find pending proposals via direct SQLite query
        db_path = os.path.join(memory.semantic.repo_path, "semantic_meta.db")
        if not os.path.exists(db_path):
            return

        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            # Find any record with pending enrichment
            query = "SELECT fid FROM semantic_meta WHERE context_json LIKE '%\"enrichment_status\": \"pending\"%'"
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

        print(f"INFO: Found {len(pending_fids)} tasks pending enrichment (mode={self.mode}, client={self.client_name}, model={self.model_name or 'default'}).")

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
                is_procedural = hasattr(proposal, 'procedural') and proposal.procedural and proposal.procedural.steps
                
                # If no logs to process, just mark as completed
                if not all_ids and not is_procedural:
                    with memory.semantic.transaction():
                        memory.semantic.update_decision(fid, {"enrichment_status": "completed"}, "Enrichment: No evidence to process.")
                    continue

                # Process in chunks of 100
                CHUNK_SIZE = 100
                processed_in_this_run = 0
                
                # For procedural, we process once since they are defined by steps, not just log clusters
                # For behavioral, we can iterate
                status = "pending"
                while True:
                    current_ids = all_ids[:CHUNK_SIZE]
                    remaining_ids = all_ids[CHUNK_SIZE:]
                    
                    cluster_logs = None
                    if current_ids:
                        events = memory.episodic.get_by_ids(current_ids)
                        log_entries = []
                        for ev in events:
                            log_entries.append(f"[{ev['kind'].upper()}] {ev['content']}")
                        cluster_logs = "\n".join(log_entries)

                    # Call LLM
                    old_rationale = proposal.rationale
                    proposal = self.enrich_proposal(proposal, cluster_logs=cluster_logs, file_path=file_path)
                    
                    # Verification: Did anything change?
                    # Note: rationale is updated inside enrich_proposal
                    if str(proposal.rationale) == str(old_rationale):
                        # LLM failed or returned same text, stop processing this file for now
                        break

                    # Update local state
                    proposal.evidence_event_ids = remaining_ids
                    
                    # If this is the last chunk or it was procedural (single pass)
                    is_last_chunk = len(remaining_ids) == 0
                    
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
                        "total_evidence_count": getattr(proposal, 'total_evidence_count', 0) + len(current_ids)
                    }
                    
                    if is_procedural and is_last_chunk:
                        updates["procedural"] = None # Clear raw steps after conversion

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
                    
                    # Limit to one chunk per FID per process_batch call to prevent long hangs?
                    # Or process all? Let's process all but with a safety break
                    if processed_in_this_run >= 500: # Safety break for very large files
                        break

                print(f"✓ Processed {processed_in_this_run} events for {fid}. Status: {status}")

            except Exception as e:
                logger.error(f"Failed to enrich proposal {fid}: {e}")
                import traceback
                logger.error(traceback.format_exc())

    def enrich_proposal(self, proposal: Any, cluster_logs: Optional[str] = None, file_path: Optional[str] = None) -> Any:
        """
        Takes a raw distilled proposal and converts it into a meaningful summary.
        """
        if self.mode == "lite":
            return proposal
            
        is_procedural = hasattr(proposal, 'procedural') and proposal.procedural and proposal.procedural.steps
        is_cluster = cluster_logs is not None
        
        if not is_procedural and not is_cluster:
            return proposal

        # Format input text for LLM
        if is_procedural:
            raw_text = self._format_procedural_text(proposal)
            prompt = self._build_procedural_prompt(raw_text, existing_rationale=proposal.rationale)
        else:
            prompt = self._build_behavioral_prompt(proposal.target, cluster_logs, existing_rationale=proposal.rationale)
        
        try:
            response_text = None
            if self.mode == "optimal":
                response_text = self._call_model(prompt, use_local=True)
            elif self.mode == "rich":
                response_text = self._call_cli_model(prompt)
                if not response_text:
                    response_text = self._call_model(prompt, use_local=False)

            if response_text:
                # Parse structured response
                import re
                goal_match = re.search(r'<goal>(.*?)</goal>', response_text, re.DOTALL | re.IGNORECASE)
                rationale_match = re.search(r'<rationale>(.*?)</rationale>', response_text, re.DOTALL | re.IGNORECASE)
                compressive_match = re.search(r'<compressive>(.*?)</compressive>', response_text, re.DOTALL | re.IGNORECASE)
                
                if goal_match:
                    proposal.title = goal_match.group(1).strip()
                if rationale_match:
                    proposal.rationale = rationale_match.group(1).strip()
                if compressive_match:
                    # Append technical note to compressive summary
                    display_path = file_path if file_path else (proposal.decision_id if hasattr(proposal, 'decision_id') else 'this file')
                    path_note = f"\n\n*Technical Note: Full logs available via 'cat {display_path}'. Do not use read_file.*"
                    proposal.compressive_rationale = compressive_match.group(1).strip() + path_note
                    
        except Exception as e:
            logger.warning(f"LLM Enrichment failed (fallback to current data): {e}")

        return proposal

    def _format_procedural_text(self, proposal: Any) -> str:
        text = f"Target: {proposal.target}\n"
        for i, step in enumerate(proposal.procedural.steps):
            text += f"Step {i+1}: {step.action}\nRationale: {step.rationale}\n\n"
        return text

    def _build_procedural_prompt(self, raw_text: str, existing_rationale: Optional[str] = None) -> str:
        context_part = ""
        if existing_rationale:
            context_part = (
                "CURRENT DETAILED RATIONALE:\n"
                "--------------------------\n"
                f"{existing_rationale}\n"
                "--------------------------\n\n"
                "The sequence below contains NEW execution steps. Integrate them into the rationale.\n"
            )

        return (
            "You are an expert Software Architect. Analyze the procedural sequence and update the knowledge record.\n\n"
            f"{context_part}"
            "NEW STEPS:\n"
            f"{raw_text}\n\n"
            "RESPONSE FORMAT (STRICT):\n"
            "1. <goal>One sentence summary of the overall purpose.</goal>\n"
            "2. <rationale>Full, detailed step-by-step architectural guide.</rationale>\n"
            "3. <compressive>Exactly 3 sentences summarizing the essence for quick context injection.</compressive>\n\n"
            "Ensure all technical terms remain in English. Output must be in Russian."
        )

    def _build_behavioral_prompt(self, target: str, logs: str, existing_rationale: Optional[str] = None) -> str:
        context_part = ""
        if existing_rationale:
            context_part = (
                "CURRENT DETAILED RATIONALE:\n"
                "--------------------------\n"
                f"{existing_rationale}\n"
                "--------------------------\n\n"
                "The logs below are NEW activities. Integrate them into the rationale.\n"
            )

        return (
            "You are a Principal Engineer. Analyze this activity cluster for '{target}' and update the knowledge record.\n\n"
            f"{context_part}"
            "NEW LOGS:\n"
            f"{logs[:5000]}\n\n"
            "RESPONSE FORMAT (STRICT):\n"
            "1. <goal>One sentence summary of the technical shift or main intent.</goal>\n"
            "2. <rationale>Comprehensive analysis of patterns, implications, and evolution.</rationale>\n"
            "3. <compressive>Exactly 3 sentences summarizing the technical state for quick context injection.</compressive>\n\n"
            "Ensure all technical terms remain in English. Output must be in Russian."
        )

    def _call_cli_model(self, prompt: str) -> Optional[str]:
        """
        Attempts to use an already authorized CLI client like gemini or claude.
        Uses a temporary file buffer for maximum reliability in Termux/Mobile.
        """
        import tempfile
        import uuid
        import shutil
        
        prompt_file = os.path.join(tempfile.gettempdir(), f"lm_prompt_{uuid.uuid4().hex[:8]}.txt")
        response_file = os.path.join(tempfile.gettempdir(), f"lm_res_{uuid.uuid4().hex[:8]}.txt")
        
        try:
            # Write prompt to buffer
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(prompt)
            
            if self.client_name == "gemini":
                # Securely locate the binary and use list-based arguments
                gemini_bin = shutil.which("gemini")
                if gemini_bin:
                    # Construct command array securely
                    cmd = [
                        gemini_bin,
                        "--model",
                        self.model_name or 'gemini-2.5-flash-lite',
                        "--prompt",
                        prompt
                    ]
                    with open(response_file, "w") as out_f:
                        subprocess.run(cmd, stdout=out_f, stderr=subprocess.DEVNULL, check=True, timeout=120) # nosec B603
                
            elif self.client_name == "claude":
                claude_bin = shutil.which("claude")
                if claude_bin:
                    cmd = [claude_bin, prompt]
                    with open(response_file, "w") as out_f:
                        subprocess.run(cmd, stdout=out_f, stderr=subprocess.DEVNULL, check=True, timeout=120) # nosec B603
            
            # Read response from buffer
            if os.path.exists(response_file):
                with open(response_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
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
                if os.path.exists(f): os.remove(f)
        
        return None

    def _call_model(self, prompt: str, use_local: bool = True) -> Optional[str]:
        """Unified method for local (Ollama) or remote (OpenAI) API calls."""
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
