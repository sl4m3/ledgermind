import logging
import os
import re
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from ledgermind.core.core.schemas import DecisionStream, KIND_PROPOSAL, ProceduralContent, ProceduralStep

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
                    # Parse procedural steps if provided
                    procedural_data = None
                    raw_procedural = data.get("procedural")
                    if raw_procedural and isinstance(raw_procedural, list):
                        steps = []
                        for s in raw_procedural:
                            if isinstance(s, dict) and "action" in s:
                                steps.append(ProceduralStep(
                                    action=s["action"],
                                    expected_outcome=s.get("expected_outcome"),
                                    rationale=s.get("rationale")
                                ))
                            elif isinstance(s, str):
                                steps.append(ProceduralStep(action=s))
                        
                        if steps:
                            procedural_data = ProceduralContent(steps=steps, target_task=target_val)

                    # V5.9: Programmatically add 'cat' suffix to compressive rationale
                    compressive = data.get("compressive") or data.get("compressive_rationale")
                    if compressive:
                        fid = getattr(proposal, 'fid', None)
                        if fid and memory and hasattr(memory, 'semantic'):
                            try:
                                # Get absolute path to the file
                                full_path = os.path.join(memory.semantic.repo_path, fid)
                                # Calculate path relative to the current working directory (project root)
                                rel_path = os.path.relpath(full_path, os.getcwd())
                                
                                suffix = f" To retrieve more detailed data, use cat {rel_path}."
                                compressive = compressive.strip() + suffix
                            except Exception:
                                # Fallback to generic if path calculation fails
                                pass

                    # V6.2: Replace keywords entirely with high-quality semantic concepts from LLM
                    raw_keywords = data.get("keywords", [])
                    semantic_keywords = []
                    for k in raw_keywords:
                        if "(" in k and ")" in k:
                            # Split "Concept (English)" into two separate keywords
                            parts = re.split(r'[\(\)]', k)
                            for p in parts:
                                p_clean = p.strip()
                                if p_clean: semantic_keywords.append(p_clean)
                        else:
                            semantic_keywords.append(k.strip())
                    
                    # Ensure unique values
                    semantic_keywords = list(set(semantic_keywords))

                    # V5.9: Evidence Crystallization
                    # Preserve the count, but completely clear the raw list after enrichment
                    current_eids = getattr(proposal, 'evidence_event_ids', [])
                    total_count = len(current_eids)
                    crystallized_eids = []

                    model_updates = {
                        "title": data.get("title") or data.get("goal") or getattr(proposal, 'title', ''),
                        "rationale": data.get("rationale") or getattr(proposal, 'rationale', ''),
                        "compressive_rationale": compressive,
                        "keywords": semantic_keywords,
                        "strengths": data.get("strengths", []),
                        "objections": data.get("objections", []),
                        "consequences": data.get("consequences", []),
                        "estimated_utility": float(data.get("estimated_utility", 0.5)),
                        "estimated_removal_cost": float(data.get("estimated_removal_cost", 0.5)),
                        "procedural": procedural_data,
                        "enrichment_status": "completed",
                        "total_evidence_count": total_count,
                        "evidence_event_ids": crystallized_eids
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
            "You are a Senior Principal Software Architect.\n"
            f"### TASK: Analyze activity for '{target}' and create a unified knowledge entry.\n"
            f"### CONTEXT: {existing_rationale}\n"
            f"### RULES: {lang_instr} Return ONLY JSON with fields:\n"
            "1. title: Professional technical title.\n"
            "2. rationale: Full, detailed architectural rationale focusing on 'what' and 'why'. Use Markdown.\n"
            "3. compressive: Exactly 3 sentences summarizing the technical essence.\n"
            "4. strengths: List of technical advantages.\n"
            "5. objections: List of potential risks or drawbacks.\n"
            "6. consequences: List of architectural impacts.\n"
            "7. estimated_utility: Number (0.0-1.0) representing current usefulness for tasks.\n"
            "8. estimated_removal_cost: Number (0.0-1.0) representing the risk of losing this knowledge.\n"
            "9. keywords: A flat list of 8-12 semantic concepts. For each concept, include both the language-specific term and the English term as SEPARATE items (e.g., ['Инъекция зависимостей', 'Dependency Injection']).\n"
            "10. procedural: List of {action, expected_outcome, rationale} steps representing the workflow."
        )
