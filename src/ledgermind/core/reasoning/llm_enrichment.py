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

        # Update client name from config if not provided
        if self.client_name == "none":
            self.client_name = memory.semantic.meta.get_config("client", "none").lower()

        print(f"INFO: Found {len(pending_fids)} tasks pending enrichment (mode={self.mode}, client={self.client_name}).")

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
                    
                    print(f"✓ Successfully enriched: {fid}")
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
            prompt = self._build_procedural_prompt(raw_text)
        else:
            prompt = self._build_behavioral_prompt(proposal.target, cluster_logs)
        
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

    def _build_procedural_prompt(self, raw_text: str) -> str:
        return (
            "You are an expert AI architect summarizing system behavior.\n"
            "Analyze the following machine-generated execution logs and convert them "
            "into a single, coherent, human-readable summary of the actions taken and the rationale behind them. "
            "Focus on the 'why' and 'what'. Keep it concise but highly informative.\n\n"
            f"Logs:\n{raw_text}\n\nSummary:"
        )

    def _build_behavioral_prompt(self, target: str, logs: str) -> str:
        return (
            "You are an expert AI architect analyzing behavioral patterns in a codebase.\n"
            f"I have detected a high density of activity related to the component '{target}'.\n"
            "Based on the following execution logs, please provide a high-level summary of what the developer/agent "
            "has been working on in this area. Identify the main theme, goal, or technical shift reflected in these actions.\n\n"
            f"Logs:\n{logs[:5000]}\n\nSummary of Behavioral Pattern:"
        )

    def _call_cli_model(self, prompt: str) -> Optional[str]:
        """Attempts to use an already authorized CLI client like gemini or claude."""
        try:
            if self.client_name == "gemini":
                cmd = ["gemini", "--prompt", prompt]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
                return result.stdout.strip()
            
            elif self.client_name == "claude":
                cmd = ["claude", prompt]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
                return result.stdout.strip()
                
        except Exception as e:
            logger.debug(f"CLI enrichment failed for {self.client_name}: {e}")
        
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
