import logging
import json
import httpx
import os
import subprocess
from typing import Dict, Any, Optional, List
from ledgermind.core.core.schemas import ProposalContent, ProceduralContent

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
        Scans semantic store for proposals pending enrichment and processes them.
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
                
                file_path = os.path.join(memory.semantic.repo_path, fid)
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

                # Fetch extra logs if this is a cluster (no procedural steps)
                cluster_logs = None
                is_procedural = hasattr(proposal, 'procedural') and proposal.procedural and proposal.procedural.steps
                
                if not is_procedural and proposal.evidence_event_ids:
                    events = memory.episodic.get_by_ids(proposal.evidence_event_ids)
                    log_entries = []
                    for ev in events:
                        log_entries.append(f"[{ev['kind'].upper()}] {ev['content']}")
                    cluster_logs = "\n".join(log_entries)

                # Enrich
                raw_rationale = proposal.rationale
                enriched = self.enrich_proposal(proposal, cluster_logs=cluster_logs)
                
                status = "completed"
                if self.mode != "lite" and enriched.rationale == raw_rationale:
                    status = "pending"

                if status == "completed":
                    # Ensure rationale is a clean string
                    final_rationale = str(enriched.rationale)
                    
                    # --- OPTIMIZATION: Evidence Compression (Counter) ---
                    orig_ids = proposal.evidence_event_ids or []
                    total_count = len(orig_ids)
                    # Keep only last 5 IDs for traceability
                    compressed_ids = orig_ids[-5:] if total_count > 5 else orig_ids
                    
                    updates = {
                        "rationale": final_rationale,
                        "enrichment_status": "completed",
                        "evidence_event_ids": compressed_ids,
                        "total_evidence_count": total_count
                    }
                    
                    if is_procedural:
                        updates["procedural"] = None # Clear raw steps after conversion to text
                    
                    with memory.semantic.transaction():
                        memory.semantic.update_decision(
                            fid,
                            updates,
                            f"Enrich proposal {fid} via LLM ({self.mode})"
                        )
                    
                    print(f"✓ Successfully enriched and compressed: {fid} (Total evidence: {total_count})")
            except Exception as e:
                logger.error(f"Failed to enrich proposal {fid}: {e}")

    def enrich_proposal(self, proposal: Any, cluster_logs: Optional[str] = None) -> Any:
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
            enriched_rationale = None
            if self.mode == "optimal":
                enriched_rationale = self._call_model(prompt, use_local=True)
            elif self.mode == "rich":
                # Priority 1: Local Authorized CLI
                enriched_rationale = self._call_cli_model(prompt)
                
                # Priority 2: Direct API Fallback
                if not enriched_rationale:
                    enriched_rationale = self._call_model(prompt, use_local=False)

            if enriched_rationale:
                proposal.rationale = f"{enriched_rationale}\n\n*Original Data:* {proposal.rationale}"
        except Exception as e:
            logger.warning(f"LLM Enrichment failed (fallback to lite): {e}")

        return proposal

    def _format_procedural_text(self, proposal: Any) -> str:
        text = f"Target: {proposal.target}\n"
        for i, step in enumerate(proposal.procedural.steps):
            text += f"Step {i+1}: {step.action}\nRationale: {step.rationale}\n\n"
        return text

    def _build_procedural_prompt(self, raw_text: str, existing_rationale: Optional[str] = None) -> str:
        context_part = ""
        if existing_rationale and "*Original Data:*" in existing_rationale:
            # Extract only the LLM-generated part
            clean_context = existing_rationale.split("*Original Data:*")[0].strip()
            if clean_context and "Overall Objective" in clean_context:
                context_part = (
                    "EXISTING GUIDE CONTEXT:\n"
                    "--------------------------\n"
                    f"{clean_context}\n"
                    "--------------------------\n\n"
                    "The sequence below contains NEW execution steps that have occurred SINCE the existing guide was written.\n"
                )

        return (
            "You are an expert Software Architect and Technical Documentation Specialist with 15+ years of experience. \n"
            "You excel at turning raw execution traces, command sequences, API calls, tool invocations, and successful action chains into clear, professional, human-readable procedural guides.\n\n"
            "TASK:\n"
            "Analyze the following procedural log/sequence of successful actions and transform it into a coherent, easy-to-follow step-by-step instruction guide for a developer or engineer.\n\n"
            f"{context_part}"
            "REQUIREMENTS:\n"
            "- Identify the overall purpose and final outcome.\n"
            "- Break everything into logical, numbered steps.\n"
            "- For each step clearly state:\n"
            "  • WHAT is done\n"
            "  • WHY it is done (technical or business reason)\n"
            "- Show dependencies and flow between steps.\n"
            "- Remove noise, abstract technical details where possible, but keep important parameters and outcomes.\n"
            "- Use concise, professional language.\n"
            "- IMPORTANT: If previous context is provided, INTEGRATE the new steps into the existing guide. Re-order, group, or refine the steps to maintain a logical and coherent flow. Update the 'Overall Objective' if needed.\n"
            "- LANGUAGE: Detect the primary language used in the provided execution logs (the user's prompts) and respond ONLY in that language. Maintain technical terms in English where appropriate.\n\n"
            "OUTPUT FORMAT (strictly follow this structure):\n\n"
            "1. **Overall Objective**\n"
            "   One-sentence summary of what this procedure achieves.\n\n"
            "2. **Prerequisites** (if any)\n\n"
            "3. **Step-by-Step Procedure**\n"
            "   1. [Step description]\n"
            "      • What: ...\n"
            "      • Why: ...\n"
            "      • Key details/parameters: ...\n\n"
            "4. **Key Insights & Recommendations**\n"
            "   Any architectural observations, potential improvements, or best practices.\n\n"
            "Now analyze this sequence of NEW actions:\n\n"
            f"{raw_text}\n\nUpdated Procedural Guide:"
        )

    def _build_behavioral_prompt(self, target: str, logs: str, existing_rationale: Optional[str] = None) -> str:
        context_part = ""
        if existing_rationale and "*Original Data:*" in existing_rationale:
            # Extract only the LLM-generated part, ignoring the raw data dump
            clean_context = existing_rationale.split("*Original Data:*")[0].strip()
            if clean_context and "Detected Technical Shift" in clean_context:
                context_part = (
                    "PREVIOUS SUMMARY CONTEXT:\n"
                    "--------------------------\n"
                    f"{clean_context}\n"
                    "--------------------------\n\n"
                    "The logs below are NEW activities that have occurred SINCE the previous summary.\n"
                )

        return (
            "You are a Principal Engineer and Codebase Archaeologist specializing in reverse-engineering developer intent from activity clusters.\n\n"
            "TASK:\n"
            "You are given a dense cluster of NEW events, logs, commits, or activities concentrated around a specific component, module, file, or target. \n"
            f"Analyze this high-density activity zone for '{target}' and extract the underlying technical shift, main goal, and behavioral pattern of the developer/team.\n\n"
            f"{context_part}"
            "REQUIREMENTS:\n"
            "- Identify the primary technical evolution or refactoring direction.\n"
            "- Uncover the core objective (what problem is being solved or opportunity pursued).\n"
            "- Detect recurring patterns in the work style or architectural decisions.\n"
            "- Base every conclusion on concrete evidence from the provided cluster.\n"
            "- IMPORTANT: If previous context is provided, INTEGRATE the new findings into a single, updated, and coherent summary. Refine the technical shift and goal if the new logs provide more clarity.\n"
            "- LANGUAGE: Detect the primary language used in the provided execution logs (the user's prompts) and respond ONLY in that language. Maintain technical terms in English where appropriate.\n\n"
            "OUTPUT FORMAT (strictly follow this structure):\n\n"
            "1. **Detected Technical Shift**\n"
            "   One-sentence summary of the main change happening.\n\n"
            "2. **Primary Goal / Intent**\n"
            "   What the developer is ultimately trying to achieve.\n\n"
            "3. **Key Patterns Observed**\n"
            "   • Pattern 1: description + evidence\n"
            "   • Pattern 2: ...\n\n"
            "4. **Architectural & Strategic Implications**\n"
            "   How this activity affects the larger codebase and possible next steps or risks.\n\n"
            "5. **Component Evolution Summary**\n"
            "   Brief before → after picture (if inferable).\n\n"
            "Now analyze this NEW activity cluster:\n\n"
            f"{logs[:5000]}\n\nUpdated Summary of Behavioral Pattern:"
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
                # Using shell redirect for 100% reliable capture
                cmd = f"gemini --model {self.model_name or 'gemini-2.5-flash-lite'} --prompt \"$(cat {prompt_file})\" > {response_file} 2>/dev/null"
                subprocess.run(cmd, shell=True, check=True, timeout=120) # nosec B602
                
            elif self.client_name == "claude":
                cmd = f"claude \"$(cat {prompt_file})\" > {response_file} 2>/dev/null"
                subprocess.run(cmd, shell=True, check=True, timeout=120) # nosec B602
            
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
