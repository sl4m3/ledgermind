import logging
import os
import re
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from ledgermind.core.core.schemas import ProposalContent, KIND_PROPOSAL

logger = logging.getLogger("ledgermind-core.enrichment")

class LLMEnricher:
    """
    Unified enrichment logic for distilled knowledge.
    Modes:
    - optimal: Local LLM (GGUF via llama-cpp-python) - Privacy & Autonomy.
    - rich: Cloud LLM (Gemini via CLI/SDK) - Maximum Intelligence.
    """
    def __init__(self, mode: str = "optimal", worker: Any = None, preferred_language: str = "auto"):
        self.mode = mode # "optimal" or "rich"
        self.worker = worker
        self.preferred_language = preferred_language
        self._local_client = None

    def process_batch(self, proposals: List[Any], episodic_store: Any, memory: Any = None) -> List[Any]:
        """Processes a batch of proposals by fetching relevant logs and calling LLM."""
        enriched_proposals = []
        for proposal in proposals:
            try:
                # 1. Fetch evidence logs
                cluster_logs = self._get_cluster_logs(proposal, episodic_store)
                
                # 2. Call LLM to enrich (Optimal/Local or Rich/Cloud)
                enriched = self.enrich_proposal(proposal, cluster_logs=cluster_logs, memory=memory)
                enriched_proposals.append(enriched)
            except Exception as e:
                logger.error(f"Failed to enrich proposal {getattr(proposal, 'fid', 'unknown')}: {e}")
                enriched_proposals.append(proposal)
        
        return enriched_proposals

    def enrich_proposal(self, proposal: Any, cluster_logs: Optional[str] = None, memory: Any = None) -> Any:
        """
        Main entry point for enriching a single proposal.
        """
        # Build prompt for the unified knowledge model
        target_val = getattr(proposal, 'target', 'general')
        instructions = self._build_unified_prompt(target_val, existing_rationale=getattr(proposal, 'rationale', ''), lang=self.preferred_language)
        
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                response_text = None
                
                if self.mode == "optimal":
                    response_text = self._call_local_model(instructions, cluster_logs, memory)
                else: # "rich" mode
                    # Try CLI first, then fallback to SDK
                    response_text = self._call_cloud_model(instructions, cluster_logs, memory)
                
                if not response_text: continue

                data = self._parse_llm_json(response_text)
                if data:
                    model_updates = {
                        "title": data.get("title") or data.get("goal") or getattr(proposal, 'title', ''),
                        "rationale": data.get("rationale") or getattr(proposal, 'rationale', ''),
                        "compressive_rationale": data.get("compressive"),
                        "strengths": data.get("strengths", []),
                        "objections": data.get("objections", []),
                        "counter_patterns": data.get("counter_patterns", []),
                        "consequences": data.get("consequences", []),
                        "expected_outcome": data.get("expected_outcome"),
                        "enrichment_status": "completed"
                    }
                    
                    if hasattr(proposal, "model_copy"):
                        return proposal.model_copy(update=model_updates)
                    for k, v in model_updates.items(): setattr(proposal, k, v)
                    return proposal
            except Exception as e:
                logger.warning(f"Enrichment attempt {attempt} failed: {e}")
        
        return proposal

    def _call_local_model(self, instructions: str, data: str, memory: Any) -> Optional[str]:
        """Calls a local GGUF model for private enrichment."""
        try:
            from llama_cpp import Llama
            
            # Shared model management via memory or local instance
            if not self._local_client:
                # In a real system, we'd use the same model path as for embeddings if it supports both
                # or a dedicated small model like Phi-3 or Mistral-7B
                model_path = os.environ.get("LEDGERMIND_LOCAL_LLM_PATH")
                if not model_path:
                    logger.warning("LEDGERMIND_LOCAL_LLM_PATH not set. Falling back to vector model (may be low quality).")
                    # Fallback to vector store's model if available
                    if memory and hasattr(memory, 'vector') and hasattr(memory.vector, 'model_path'):
                        model_path = memory.vector.model_path
                
                if not model_path or not os.path.exists(model_path):
                    logger.error("No local LLM model found for 'optimal' mode.")
                    return None

                self._local_client = Llama(model_path=model_path, n_ctx=2048, verbose=False)

            prompt = f"System: You are an expert code architect.\nUser: {instructions}\n\nData: {data}\nAssistant: "
            output = self._local_client(prompt, max_tokens=1024, stop=["User:", "System:"], echo=False)
            return output['choices'][0]['text']
        except ImportError:
            logger.error("llama-cpp-python not installed. Cannot use 'optimal' mode.")
            return None
        except Exception as e:
            logger.error(f"Local LLM call failed: {e}")
            return None

    def _call_cloud_model(self, instructions: str, data: str, memory: Any) -> Optional[str]:
        """Calls a cloud model (Gemini) via CLI or SDK."""
        # 1. Try Gemini CLI (Rich/System mode)
        res = self._call_cli_model(instructions, data, memory)
        if res: return res
        
        # 2. Fallback to SDK if API key is present
        return self._call_sdk_model(instructions + "\n\n" + data)

    def _call_sdk_model(self, prompt: str) -> Optional[str]:
        """Directly calls the Gemini SDK."""
        try:
            import google.generativeai as genai
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key: return None
            
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            return response.text if response else None
        except (ImportError, Exception):
            return None

    def _call_cli_model(self, instructions: str, data: str = "", memory: Any = None) -> Optional[str]:
        """Calls the Gemini CLI through subprocess."""
        import subprocess
        try:
            # We use the built-in gemini CLI tool
            full_prompt = f"{instructions}\n\n### DATA TO ANALYZE:\n{data}"
            result = subprocess.run(["gemini", full_prompt], capture_output=True, text=True, timeout=180)
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as e:
            logger.error(f"CLI call failed: {e}")
            return None

    def _get_cluster_logs(self, proposal: Any, episodic_store: Any) -> str:
        eids = getattr(proposal, 'evidence_event_ids', [])
        if not eids: return "No logs provided."
        events = episodic_store.get_batch_by_ids(eids)
        return "\n".join([f"[{e['timestamp']}] {e['kind'].upper()}: {e['content']}" for e in events])

    def _parse_llm_json(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            if "```json" in text:
                text = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL).group(1)
            elif "{" in text and "}" in text:
                text = text[text.find("{"):text.rfind("}")+1]
            return json.loads(text)
        except Exception: return None

    def _build_unified_prompt(self, target: str, existing_rationale: str = "", lang: str = "auto") -> str:
        lang_instr = f"Respond strictly in {lang}." if lang != "auto" else "Respond in the original language."
        return (
            f"### TASK: Analyze activity for '{target}' and create a unified knowledge entry.\n"
            f"### CONTEXT: {existing_rationale}\n"
            f"### RULES: {lang_instr} Return ONLY JSON with fields: title, rationale, compressive, strengths, objections, consequences."
        )
