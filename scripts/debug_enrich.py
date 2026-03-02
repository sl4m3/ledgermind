import sys
import os
import logging

# Extreme logging
logging.basicConfig(level=logging.INFO)

from ledgermind.core.api.memory import Memory
from ledgermind.core.reasoning.llm_enrichment import LLMEnricher
from ledgermind.core.stores.semantic_store.loader import MemoryLoader
from ledgermind.core.core.schemas import ProposalContent

def main():
    storage_path = os.path.abspath("../.ledgermind")
    memory = Memory(storage_path=storage_path)
    
    # Target one specific file
    fid = "proposal_20260302_053337_707000_63730eb4.md" # The docs one we tested manually
    file_path = os.path.join(memory.semantic.repo_path, fid)
    
    print(f"DEBUG: Processing {fid}...")
    
    with open(file_path, 'r') as f:
        data, _ = MemoryLoader.parse(f.read())
    
    p_obj = ProposalContent(**data['context'])
    
    enricher = LLMEnricher(mode='rich', client_name='gemini')
    
    print("DEBUG: Requesting LLM...")
    try:
        enriched = enricher.enrich_proposal(p_obj)
        print("DEBUG: LLM Response received.")
        
        if enriched.rationale != p_obj.rationale:
            print("DEBUG: Rationale changed! Saving...")
            
            updates = {
                "rationale": str(enriched.rationale),
                "enrichment_status": "completed",
                "evidence_event_ids": p_obj.evidence_event_ids[-5:] if p_obj.evidence_event_ids else []
            }
            
            # Direct save without complex transactions for now
            memory.semantic.update_decision(fid, updates, "Debug Enrichment")
            print("DEBUG: Save call finished.")
        else:
            print("DEBUG: No changes returned from LLM.")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    main()
