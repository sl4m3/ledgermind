import logging
import json
import httpx
import os
from typing import Dict, Any, Optional, List
from ledgermind.core.core.schemas import ProposalContent, ProceduralContent

logger = logging.getLogger(__name__)

class LLMEnricher:
    """
    Enriches machine-generated proposals into human-readable text
    using local or remote LLMs based on the selected arbitration mode.
    """
    
    def __init__(self, mode: str = "lite", client_name: str = "none"):
        self.mode = mode.lower()
        self.client_name = client_name.lower()
        self.client = httpx.Client(timeout=60.0)

    def process_batch(self, memory: Any):
        """
        Scans semantic store for proposals pending enrichment and processes them.
        """
        if self.mode == "lite":
            return

        # 1. Find pending proposals via direct SQLite query for speed and reliability
        query = "SELECT fid FROM semantic_meta WHERE kind = 'proposal' AND status = 'draft' AND context_json LIKE '%\"enrichment_status\": \"pending\"%'"
        rows = memory.semantic.meta._conn.execute(query).fetchall()
        pending_fids = [row[0] for row in rows]

        if not pending_fids:
            return

        # Update client name from config if not provided
        if self.client_name == "none":
            self.client_name = memory.semantic.meta.get_config("client", "none").lower()

        logger.info(f"Found {len(pending_fids)} proposals pending enrichment (mode={self.mode}, client={self.client_name}).")

        for fid in pending_fids:
            try:
                # Load full proposal
                from ledgermind.core.stores.semantic_store.loader import MemoryLoader
                from ledgermind.core.core.schemas import ProposalContent
                
                file_path = os.path.join(memory.semantic.repo_path, fid)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                data, body = MemoryLoader.parse(content)
                if not data: continue
                
                # Context is stored in the 'context' key of the YAML
                proposal_data = data.get('context', {})
                if not proposal_data: continue
                
                proposal = ProposalContent(**proposal_data)

                # Enrich
                raw_rationale = proposal.rationale
                enriched = self.enrich_proposal(proposal)
                
                # If rationale didn't change and we are not in lite mode, 
                # it means enrichment failed or skipped.
                status = "completed"
                if self.mode != "lite" and enriched.rationale == raw_rationale:
                    # Check if it was a transient error (already logged in enrich_proposal)
                    # We keep it pending if nothing changed and it's not a 'lite' intention
                    status = "pending"

                if status == "completed":
                    # Use update_decision to synchronize file and database
                    updates = {
                        "rationale": enriched.rationale,
                        "enrichment_status": "completed"
                    }
                    
                    with memory.semantic.transaction():
                        memory.semantic.update_decision(
                            filename=fid,
                            updates=updates,
                            commit_msg=f"Enrich proposal {fid} via LLM ({self.mode})"
                        )
                    
                    logger.info(f"Successfully enriched proposal {fid}")
            except Exception as e:
                logger.error(f"Failed to enrich proposal {fid}: {e}")

    def enrich_proposal(self, proposal: ProposalContent) -> ProposalContent:
        """
        Takes a raw distilled proposal and converts it into a meaningful summary.
        """
        if self.mode == "lite":
            return proposal
            
        if not proposal.procedural or not proposal.procedural.steps:
            return proposal

        raw_text = self._format_raw_text(proposal)
        
        try:
            enriched_rationale = None
            if self.mode == "optimal":
                enriched_rationale = self._call_optimal_model(raw_text)
            elif self.mode == "rich":
                # Priority 1: Local Authorized CLI
                enriched_rationale = self._call_cli_model(raw_text)
                
                # Priority 2: Direct API Fallback
                if not enriched_rationale:
                    enriched_rationale = self._call_rich_model(raw_text)

            if enriched_rationale:
                proposal.rationale = f"{enriched_rationale}\n\n*Original Data:* {proposal.rationale}"
        except Exception as e:
            logger.warning(f"LLM Enrichment failed (fallback to lite): {e}")

        return proposal

    def _call_cli_model(self, raw_text: str) -> Optional[str]:
        """Attempts to use an already authorized CLI client like gemini or claude."""
        import subprocess
        prompt = self._build_prompt(raw_text)
        
        try:
            if self.client_name == "gemini":
                # Gemini CLI headless mode
                cmd = ["gemini", "--prompt", prompt]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
                return result.stdout.strip()
            
            elif self.client_name == "claude":
                # Claude Code CLI (non-interactive prompt)
                cmd = ["claude", prompt]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
                return result.stdout.strip()
                
        except Exception as e:
            logger.debug(f"CLI enrichment failed for {self.client_name}: {e}")
        
        return None

    def _format_raw_text(self, proposal: ProposalContent) -> str:
        text = f"Target: {proposal.target}\n"
        for i, step in enumerate(proposal.procedural.steps):
            text += f"Step {i+1}: {step.action}\nRationale: {step.rationale}\n\n"
        return text

    def _build_prompt(self, raw_text: str) -> str:
        return (
            "You are an expert AI architect summarizing system behavior.\n"
            "Analyze the following machine-generated execution logs and convert them "
            "into a single, coherent, human-readable summary of the actions taken and the rationale behind them. "
            "Focus on the 'why' and 'what'. Keep it concise but highly informative.\n\n"
            f"Logs:\n{raw_text}\n\nSummary:"
        )

    def _call_optimal_model(self, raw_text: str) -> Optional[str]:
        """Calls local Ollama or OpenAI-compatible endpoint."""
        url = os.getenv("LEDGERMIND_OPTIMAL_URL", "http://localhost:11434/v1/chat/completions")
        model = os.getenv("LEDGERMIND_OPTIMAL_MODEL", "llama3") # common default for local
        
        prompt = self._build_prompt(raw_text)
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }
        
        response = self.client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def _call_rich_model(self, raw_text: str) -> Optional[str]:
        """Calls external cloud LLM (e.g., OpenAI or Anthropic)."""
        prompt = self._build_prompt(raw_text)
        
        # Simple OpenAI fallback as standard for 'rich'
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.debug("OPENAI_API_KEY not set for rich mode, skipping enrichment.")
            return None
            
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3
        }
        
        response = self.client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
