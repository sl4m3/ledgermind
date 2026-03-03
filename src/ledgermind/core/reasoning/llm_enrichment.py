import logging
import json
import httpx
import os
import subprocess
import gc
import time
from typing import Dict, Any, Optional, List
from ledgermind.core.core.schemas import ProposalContent

logger = logging.getLogger("ledgermind.core.reasoning.enrichment")

class LLMEnricher:
    """
    Enriches machine-generated proposals into human-readable text
    using local or remote LLMs based on the selected arbitration mode.
    """
    
    def __init__(self, mode: str = "lite", client_name: str = "none", model_name: Optional[str] = None, worker: Optional[Any] = None):
        self.mode = mode.lower()
        self.client_name = client_name.lower()
        self.model_name = model_name
        self.worker = worker
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client

    def close(self):
        """Explicitly release resources."""
        if self._client:
            self._client.close()
            self._client = None

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

        instructions = (
            "You are a Senior Principal Engineer. I am merging multiple semantically identical hypotheses into one canonical decision.\n"
            "Analyze the rationales below and synthesize them into a single, high-quality, non-redundant architectural guide.\n\n"
            "RESPONSE FORMAT (STRICT):\n"
            "1. <goal>One sentence summary of the unified intent.</goal>\n"
            "2. <rationale>Full, detailed unified architectural rationale. Merge logic, resolve contradictions, keep it professional.</rationale>\n"
            "3. <compressive>Exactly 3 sentences summarizing the final state.</compressive>\n\n"
            "Ensure technical terms remain in English. Output must be in the same language as the input rationales."
        )

        try:
            response_text = None
            if self.mode == "optimal":
                response_text = self._call_model(instructions + "\n\n" + combined_text, use_local=True)
            elif self.mode == "rich":
                response_text = self._call_cli_model(instructions, data=combined_text)
                if not response_text:
                    response_text = self._call_model(instructions + "\n\n" + combined_text, use_local=False)

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
        try:
            if self.mode == "lite":
                return results

            # 1. Find pending proposals via direct SQLite query
            db_path = os.path.abspath(os.path.join(memory.semantic.repo_path, "semantic_meta.db"))
            if not os.path.exists(db_path):
                # Fallback to subdirectory if not in root
                db_path = os.path.abspath(os.path.join(memory.semantic.repo_path, "semantic", "semantic_meta.db"))
            
            logger.info(f"Enrichment: Checking database at {db_path}")
            if not os.path.exists(db_path):
                logger.warning(f"Enrichment: Database not found at {db_path}")
                return results

            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                # Increased limit to 50 to process more proposals at once
                query = "SELECT fid FROM semantic_meta WHERE (enrichment_status = 'pending' OR status = 'draft') AND kind = 'proposal' LIMIT 50"
                rows = conn.execute(query).fetchall()
                pending_fids = [row[0] for row in rows]
                conn.close()
            except Exception as e:
                logger.error(f"Failed to query enrichment queue: {e}")
                return results

            if not pending_fids:
                return results

            # Update client and model from config if not provided
            if self.client_name == "none":
                self.client_name = memory.semantic.meta.get_config("client", "none").lower()
            
            if self.model_name is None:
                self.model_name = memory.semantic.meta.get_config("enrichment_model")

            logger.info(f"Enrichment: Found {len(pending_fids)} tasks (mode={self.mode}, client={self.client_name}, model={self.model_name or 'default'}).")
            print(f"   [ENRICH] Processing {len(pending_fids)} proposals...")

            for idx, fid in enumerate(pending_fids):
                try:
                    # Load full proposal
                    from ledgermind.core.stores.semantic_store.loader import MemoryLoader
                    from ledgermind.core.core.schemas import ProposalContent, DecisionStream

                    file_path = os.path.abspath(os.path.join(memory.semantic.repo_path, fid))
                    if not os.path.exists(file_path):
                        print(f"   [WARNING] File not found: {file_path}")
                        continue

                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    data, body = MemoryLoader.parse(content)
                    if not data:
                        print(f"   [WARNING] Failed to parse proposal data: {fid}")
                        continue

                    # Fix status if needed
                    proposal_data = data.get('context', {})
                    if not proposal_data:
                        print(f"   [WARNING] No context in proposal data: {fid}")
                        continue

                    # Handle 'active' status for proposals
                    if 'decision_id' not in proposal_data and proposal_data.get('status') == 'active':
                        proposal_data['status'] = 'draft'

                    # Determine object type
                    if 'decision_id' in proposal_data:
                        proposal = DecisionStream(**proposal_data)
                    else:
                        proposal = ProposalContent(**proposal_data)

                    # Determine knowledge type (Behavioral vs Procedural)
                    from ledgermind.core.core.schemas import DecisionPhase
                    is_behavioral = getattr(proposal, 'phase', None) == DecisionPhase.PATTERN
                    
                    if is_behavioral:
                        instructions = self._build_behavioral_prompt(proposal.target, existing_rationale=proposal.rationale)
                    else:
                        instructions = self._build_procedural_prompt(proposal.target, existing_rationale=proposal.rationale)

                    # --- ITERATIVE CHUNKING LOGIC ---
                    all_ids = sorted(proposal.evidence_event_ids or [])
                    total_events = len(all_ids)
                    
                    print(f"   ({idx+1}/{len(pending_fids)}) Enriching {fid} (Total events: {total_events})...")
                    
                    # If no logs to process, just mark as completed
                    if not all_ids:
                        with memory.semantic.transaction():
                            memory.semantic.update_decision(fid, {"enrichment_status": "completed"}, "Enrichment: No evidence to process.")
                        logger.info(f"Enrichment: No evidence for {fid}. Completed.")
                        continue

                    processed_in_this_run = 0
                    iteration = 0
                    status = "pending"
                    
                    while True:
                        iteration += 1

                        # --- TOKEN-BASED CHUNKING LOGIC ---
                        selected_ids = []
                        log_entries = []
                        current_tokens = self._estimate_tokens(instructions)
                        TOKEN_LIMIT = 100000

                        for event_id in all_ids:
                            # Get the event
                            events = memory.episodic.get_by_ids([event_id])
                            if not events:
                                continue

                            ev = events[0]

                            # Format with full context and content
                            ctx_str = ""
                            if ev.get('context'):
                                try:
                                    ctx = ev['context']
                                    if isinstance(ctx, dict):
                                        ctx_str = f" | Context: {str(ctx)}"
                                    else:
                                        ctx_str = f" | Context: {ctx}"
                                except: pass

                            entry = f"[{ev['kind'].upper()}] {ev['content']}{ctx_str}"
                            entry_tokens = self._estimate_tokens(entry)

                            # Check if adding this event exceeds the 100k limit
                            if current_tokens + entry_tokens > TOKEN_LIMIT:
                                # If we already have events, stop here to process them
                                if selected_ids:
                                    break
                                # If this is the FIRST event and it's huge, we have to process it alone
                            
                            selected_ids.append(event_id)
                            log_entries.append(entry)
                            current_tokens += entry_tokens

                        current_ids = selected_ids
                        cluster_logs = "\n".join(log_entries)
                        current_chunk_size = len(selected_ids)

                        print(f"   [INFO] Selected {current_chunk_size} events (~{current_tokens:,} tokens)", flush=True)

                        remaining_ids = all_ids[len(current_ids):]
                        is_last_chunk = len(remaining_ids) == 0

                        # Call LLM
                        old_rationale = str(getattr(proposal, 'rationale', ''))
                        iteration_processed = False
                        
                        print(f"   - Iteration {iteration}: Sending {len(current_ids)} events to LLM ({len(cluster_logs)} bytes)...", flush=True)
                        updated_proposal = self.enrich_proposal(proposal, cluster_logs=cluster_logs, file_path=file_path, memory=memory)

                        # Handle failure or token limit (though unlikely with 100k limit)
                        if updated_proposal == "TOO_MANY_TOKENS":
                            print(f"   [ERROR] Token limit exceeded even with 100k limit. Skipping this chunk.")
                            # Move forward anyway to avoid infinite loop
                            all_ids = all_ids[len(current_ids):]
                            continue

                        if updated_proposal:
                            proposal = updated_proposal
                            iteration_processed = True

                        if hasattr(proposal, '_enrichment_failed') and proposal._enrichment_failed:
                            with memory.semantic.transaction():
                                memory.semantic.update_decision(fid, {"enrichment_status": "failed"}, "Enrichment: CLI failed systematically")
                            print(f"   [SKIPPED] {fid} marked as failed due to systematic CLI errors.")
                            break

                        # Update local state
                        processed_in_this_run += len(current_ids)
                        all_ids = all_ids[len(current_ids):]
                        
                        if not hasattr(proposal, 'total_evidence_count') or proposal.total_evidence_count is None:
                            proposal.total_evidence_count = 0
                        proposal.total_evidence_count += len(current_ids)
                        
                        status = "pending"
                        if is_last_chunk:
                            status = "completed"
                        
                        # Save intermediate or final progress
                        updates = {
                            "title": getattr(proposal, 'title', 'Untitled'),
                            "content": getattr(proposal, 'title', 'Untitled'),
                            "rationale": getattr(proposal, 'rationale', ''),
                            "keywords": getattr(proposal, 'keywords', []),
                            "compressive_rationale": getattr(proposal, 'compressive_rationale', None),
                            "enrichment_status": status,
                            "evidence_event_ids": all_ids,
                            "total_evidence_count": proposal.total_evidence_count
                        }

                        with memory.semantic.transaction():
                            memory.semantic.update_decision(fid, updates, f"Enrichment iteration ({status})")
                        
                        if is_last_chunk:
                            break
                        
                        if processed_in_this_run >= 1000: # Safety break for very large files
                            print(f"   - Safety break for {fid} after {processed_in_this_run} events.")
                            break

                    print(f"   - Done: Processed {processed_in_this_run}/{total_events} events. Status: {status}")
                    results.append({"fid": fid, "status": status, "events": processed_in_this_run})
                    gc.collect()

                except Exception as e:
                    logger.error(f"Failed to enrich proposal {fid}: {e}")
                    print(f"   [ERROR] Failed to enrich proposal {fid}: {e}")
            
            return results
        finally:
            # Final cleanup of any stray files in tmp directory
            self.cleanup_temp_files(memory)

    def cleanup_temp_files(self, memory: Any = None):
        """
        Forcefully removes all temporary enrichment files.
        Simplified - no longer creates temp files for CLI calls.
        """
        import os
        import shutil
        import glob

        tmp_dir = os.path.join(memory.storage_path, "tmp") if (memory and hasattr(memory, 'storage_path')) else "/tmp"
        if not os.path.exists(tmp_dir):
            return

        # Remove any existing temp files from previous sessions
        temp_files = glob.glob(os.path.join(tmp_dir, "*"))
        for f in temp_files:
            try:
                if os.path.isfile(f):
                    os.remove(f)
            except OSError:
                pass

        # Try to remove the directory itself if it belongs to .ledgermind
        if memory and hasattr(memory, 'storage_path') and ".ledgermind" in memory.storage_path:
            try:
                if not os.listdir(tmp_dir):
                    os.rmdir(tmp_dir)
            except OSError:
                pass

    def enrich_proposal(self, proposal: Any, cluster_logs: Optional[str] = None, file_path: Optional[str] = None, memory: Any = None) -> Any:
        """
        Takes a raw distilled proposal and converts it into a meaningful summary using event logs.
        Selects specialized prompts based on whether it is a Behavioral Pattern or a Procedural Trajectory.
        """
        if self.mode == "lite" or not cluster_logs:
            return proposal
            
        # Determine knowledge type (Behavioral vs Procedural)
        from ledgermind.core.core.schemas import DecisionPhase
        is_behavioral = getattr(proposal, 'phase', None) == DecisionPhase.PATTERN
        
        if is_behavioral:
            instructions = self._build_behavioral_prompt(proposal.target, existing_rationale=proposal.rationale)
        else:
            instructions = self._build_procedural_prompt(proposal.target, existing_rationale=proposal.rationale)
        
        try:
            response_text = None
            if self.mode == "optimal":
                response_text = self._call_model(instructions + "\n\n### RAW DATA TO ANALYZE:\n" + cluster_logs, use_local=True)
            elif self.mode == "rich":
                try:
                    response_text = self._call_cli_model(instructions, data=cluster_logs, memory=memory)
                    # Empty string ("") means CLI failed (exit/timeout) - don't try fallback
                    # None means not available or fallback should be attempted
                    if response_text == "":
                        print(f"   [ERROR] CLI failed systematically. Aborting enrichment for this proposal.")
                        proposal._enrichment_failed = True
                        return proposal
                    if response_text is None:
                        response_text = self._call_model(instructions + "\n\n### RAW DATA TO ANALYZE:\n" + cluster_logs, use_local=False)
                except Exception as e:
                    print(f"   [ERROR] Enrichment failed: {e}")
                    # Keep original values and continue
                    response_text = None

            if response_text:
                import re
                import json

                # 1. Try JSON parsing first (for procedural or structured models)
                try:
                    # Look for JSON block if model wrapped it in markdown
                    json_text = response_text
                    if "```json" in response_text:
                        json_text = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL).group(1)
                    elif "{" in response_text and "}" in response_text:
                        # Extract first JSON-like object
                        start = response_text.find("{")
                        end = response_text.rfind("}") + 1
                        json_text = response_text[start:end]
                    
                    data = json.loads(json_text)
                    if isinstance(data, dict):
                        if "goal" in data: proposal.title = data["goal"]
                        if "rationale" in data: proposal.rationale = data["rationale"]
                        if "compressive" in data: proposal.compressive_rationale = data["compressive"]
                        
                        # Update keywords based on new rich content
                        self._update_keywords(proposal)

                        # Add technical note to compressive
                        if proposal.compressive_rationale:
                            display_path = file_path if file_path else (proposal.decision_id if hasattr(proposal, 'decision_id') else 'this file')
                            path_note = f"\n\n*Technical Note: Full logs available via 'cat {display_path}'. Do not use read_file.*"
                            if path_note not in proposal.compressive_rationale:
                                proposal.compressive_rationale += path_note
                        return proposal
                except (json.JSONDecodeError, AttributeError, ValueError) as e:
                    print(f"   [DEBUG] JSON extraction failed: {e}")
                    if response_text:
                        # Log the first 500 chars of the failed response
                        print(f"   [DEBUG] Raw response start: {response_text[:500]}...")
                    pass # Not JSON or failed to extract, try regex

                # 2. Parse text format
                goal_match = re.search(r'GOAL:\s*(.*?)(?:\n|$)', response_text, re.IGNORECASE)
                rationale_match = re.search(r'RATIONALE:\s*(.*?)(?:\n3\. COMPRESSIVE:|$)', response_text, re.DOTALL | re.IGNORECASE)
                compressive_match = re.search(r'3\. COMPRESSIVE:\s*(.*)', response_text, re.IGNORECASE)

                if goal_match:
                    proposal.title = goal_match.group(1).strip()
                if rationale_match:
                    proposal.rationale = rationale_match.group(1).strip()
                if compressive_match:
                    proposal.compressive_rationale = compressive_match.group(1).strip()

                # Update keywords based on new rich content
                self._update_keywords(proposal)

                # Add technical note if not present
                if hasattr(proposal, 'compressive_rationale') and proposal.compressive_rationale:
                    display_path = file_path if file_path else (proposal.decision_id if hasattr(proposal, 'decision_id') else 'this file')
                    path_note = f"\n\n*Technical Note: Full logs available via 'cat {display_path}'. Do not use read_file.*"
                    if path_note not in proposal.compressive_rationale:
                        proposal.compressive_rationale += path_note

                if not goal_match and not rationale_match:
                    # Try fallback to XML
                    goal_xml = re.search(r'<goal>(.*?)</goal>', response_text, re.DOTALL | re.IGNORECASE)
                    rationale_xml = re.search(r'<rationale>(.*?)</rationale>', response_text, re.DOTALL | re.IGNORECASE)
                    if goal_xml:
                        proposal.title = goal_xml.group(1).strip()
                    if rationale_xml:
                        proposal.rationale = rationale_xml.group(1).strip()
                        self._update_keywords(proposal)
                    
        except Exception as e:
            logger.warning(f"LLM Enrichment failed: {e}")
            print(f"   [ERROR] LLM Enrichment failed: {e}")

        return proposal

    def _update_keywords(self, proposal: Any):
        """Extracts and updates keywords based on title, target and rationale using frequency."""
        import re
        from collections import Counter
        
        target = getattr(proposal, 'target', '')
        title = getattr(proposal, 'title', '')
        rationale = getattr(proposal, 'rationale', '')
        
        all_text = f"{title} {target} {rationale}".lower()
        # Support RU/EN
        words = re.findall(r'[a-zа-я0-9]{3,}', all_text)
        
        stop_words = {
            "for", "the", "and", "with", "from", "this", "that", "was", "were", "been", "has", "had", 
            "для", "или", "это", "был", "была", "было", "были", "его", "ее", "их", "как", "мне",
            "observed", "emerging", "activity", "analysis", "raw", "logs", "behavioral", "pattern",
            "technical", "note", "available", "full", "procedural", "guide"
        }
        
        filtered_words = [w for w in words if w not in stop_words]
        if not filtered_words:
            return
            
        most_common = Counter(filtered_words).most_common(10)
        proposal.keywords = [w for w, count in most_common]


    def _build_behavioral_prompt(self, target: str, existing_rationale: Optional[str] = None) -> str:
        """Expert prompt for reverse-engineering developer intent from activity clusters."""
        context_part = ""
        if existing_rationale and "Observed emerging activity" not in existing_rationale and "Analysis of raw logs" not in existing_rationale:
            context_part = (
                "### EXISTING RATIONALE (CURRENT KNOWLEDGE)\n"
                f"{existing_rationale}\n\n"
            )

        return (
            "### SYSTEM ROLE\n"
            "You are a Principal Engineer and Codebase Archaeologist (MemP v5.5).\n"
            "You specialize in reverse-engineering developer intent from activity clusters, logs, and commits.\n\n"
            f"### TASK: Analyze the following high-density activity cluster for target '{target}'.\n"
            "Identify the underlying technical shift, the main goal, and the recurring behavioral patterns.\n\n"
            "### REQUIREMENTS\n"
            "- Identify the primary technical evolution or refactoring direction.\n"
            "- Uncover the core objective (what problem is being solved or opportunity pursued).\n"
            "- Detect recurring patterns in the work style or architectural decisions.\n"
            "- Base every conclusion on concrete evidence from the provided cluster.\n"
            "- LANGUAGE: Detect the language of the provided logs/context. Your entire response (goal, rationale, compressive) MUST be in the SAME language.\n"
            "- CRITICAL: If the input is in Russian, respond in Russian. If German, respond in German. Do not default to English unless the input is in English.\n\n"
            f"{context_part}"
            "### RESPONSE FORMAT\n"
            "Respond with ONLY a JSON object with these keys:\n"
            "{\n"
            '  "goal": "One-sentence summary of the unified intent",\n'
            '  "rationale": "# Behavioral Analysis: ' + target + '\\n\\n## 1. Primary Goal / Intent\\n[Detailed description]\\n\\n## 2. Key Patterns Observed\\n- **Pattern 1**: [Description] + [Evidence]\\n\\n## 3. Architectural Implications\\n[Strategic impact]",\n'
            '  "compressive": "3 sentences summarizing the final state"\n'
            "}\n"
            "No additional text before or after the JSON."
        )

    def _build_procedural_prompt(self, target: str, existing_rationale: Optional[str] = None) -> str:
        """Expert prompt for turning raw execution traces into step-by-step instruction guides."""
        context_part = ""
        if existing_rationale and "Observed emerging activity" not in existing_rationale and "Analysis of raw logs" not in existing_rationale:
            context_part = (
                "### EXISTING RATIONALE (CURRENT KNOWLEDGE)\n"
                f"{existing_rationale}\n\n"
            )

        return (
            "### SYSTEM ROLE\n"
            "You are a Senior Software Architect and Technical Documentation Specialist (15+ years exp).\n"
            "You excel at turning raw execution traces, command sequences, and successful action chains into professional, human-readable procedural guides.\n\n"
            f"### TASK: Analyze the following procedural logs for target '{target}' and transform them into a coherent, step-by-step instruction guide.\n\n"
            "### REQUIREMENTS\n"
            "- Identify the overall purpose and final outcome.\n"
            "- Break everything into logical, numbered steps.\n"
            "- For each step clearly state: WHAT is done and WHY it is done.\n"
            "- Remove noise, abstract technical details, but keep important parameters.\n"
            "- Use concise, professional language.\n"
            "- LANGUAGE: Detect the language of the provided logs/context. Your entire response (goal, rationale, compressive) MUST be in the SAME language.\n"
            "- CRITICAL: If the input is in Russian, respond in Russian. If German, respond in German. Do not default to English unless the input is in English.\n\n"
            f"{context_part}"
            "### RESPONSE FORMAT\n"
            "Respond with ONLY a JSON object with these keys:\n"
            '{\n  "goal": "One-sentence summary of the overall objective",\n  "rationale": "# Procedural Guide: ' + target + '\\n\\n## 1. Overall Objective\\n[One-sentence summary]\\n\\n## 2. Step-by-Step Procedure\\n1. [Step Description]\\n   - **What**: ...\\n   - **Why**: ...\\n\\n## 3. Key Insights & Recommendations\\n[Architectural observations]",\n  "compressive": "3 sentences summarizing the procedure"\n}\n'
            "No additional text before or after the JSON."
        )

    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count (4 chars ≈ 1 token)."""
        return len(text) // 4

    def _call_cli_model(self, instructions: str, data: Optional[str] = None, memory: Any = None) -> Optional[str]:
        """
        Calls the CLI model (gemini) using stdin for context data and positional argument for instructions.
        """
        import subprocess
        import time

        try:
            total_chars = len(data or "") + len(instructions)
            estimated_tokens = total_chars # Conservative estimate

            # Token limit check (1M for Gemini Flash)
            MAX_TOKENS = 1000000
            if estimated_tokens > MAX_TOKENS:
                print(f"   [WARNING] Input too large ({estimated_tokens:,} tokens). Limit: {MAX_TOKENS:,}")
                return "TOO_MANY_TOKENS"
            
            print(f"   [DEBUG] CLI Enrichment: Sending {len(data or ''):,} chars context and {len(instructions)} chars prompt", flush=True)

            model_name = self.model_name or "gemini-2.5-flash-lite"
            timeout = 300  # 5 minutes

            max_retries = 3
            for attempt in range(1, max_retries + 1):
                print(f"   [CLI] Attempt {attempt}/{max_retries}: Waiting for Gemini response...", flush=True)
                start_time = time.time()

                try:
                    # RECOMMENDED PATTERN: context via stdin, instructions as positional argument
                    # This avoids hangs related to -p and properly triggers headless mode
                    proc = subprocess.run(
                        ["gemini", "-m", model_name, instructions],
                        input=data or "",
                        capture_output=True,
                        text=True,
                        timeout=timeout
                    )

                    duration = time.time() - start_time

                    if proc.returncode == 0:
                        if proc.stdout:
                            output = proc.stdout.strip()
                            print(f"   [DEBUG] CLI completed in {duration:.2f}s (received {len(output)} bytes)", flush=True)
                            return output
                        else:
                            print(f"   [WARNING] CLI output is empty after {duration:.2f}s")
                    else:
                        error_msg = proc.stderr[:500] if proc.stderr else f"Exit code: {proc.returncode}"
                        print(f"   [ERROR] CLI failed (exit {proc.returncode}) in {duration:.2f}s: {error_msg}")

                        if "token" in error_msg.lower() or "limit" in error_msg.lower() or "quota" in error_msg.lower():
                            return "TOO_MANY_TOKENS"

                        if proc.returncode == 1: # Fatal error
                            return ""

                except subprocess.TimeoutExpired:
                    print(f"   [ERROR] CLI Timeout after {timeout}s on attempt {attempt}")

                if attempt < max_retries:
                    time.sleep(5)

            return ""

        except Exception as e:
            print(f"   [ERROR] CLI enrichment failed: {e}")
            return ""

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
