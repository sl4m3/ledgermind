import os
import sys
import logging

# Setup paths and logging
sys.path.insert(0, os.path.abspath("src"))
logging.basicConfig(level=logging.INFO, format='%(message)s')

from ledgermind.core.api.memory import Memory
from ledgermind.core.reasoning.llm_enrichment import LLMEnricher
from ledgermind.core.core.schemas import DecisionStream
from ledgermind.core.stores.semantic_store.loader import MemoryLoader

def main():
    storage_path = os.path.abspath("../.ledgermind")
    memory = Memory(storage_path=storage_path, vector_workers=0)
    
    # Target file specified by the user
    fid = "proposal_20260308_224734_788000_1ba3ba1c.md"
    
    try:
        print(f">>> Enriching target file: {fid}")

        # 1. Load the actual object
        file_path = os.path.join(memory.semantic.repo_path, fid)
        if not os.path.exists(file_path):
            print(f"Error: File {file_path} not found.")
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            data, _ = MemoryLoader.parse(f.read())
        
        obj = DecisionStream(**data.get('context', {}))
        obj.fid = fid

        print(f"--- Evidence: {len(obj.evidence_event_ids)} events.")

        # 2. Enrich using LLMEnricher
        preferred_lang = memory.semantic.meta.get_config("preferred_language", "russian")
        enricher = LLMEnricher(mode="rich", preferred_language=preferred_lang)
        
        print(f"--- Calling LLM (Lang: {preferred_lang})...")
        enriched = enricher.enrich_proposal(obj, memory=memory)
        enriched.enrichment_status = "completed"

        # 3. Save back
        with memory.semantic.transaction():
            memory.semantic.update_decision(
                fid, 
                enriched.model_dump(mode='json', exclude_none=True), 
                commit_msg=f"Enrichment: Finalized specific test hypothesis {fid}"
            )
        
        print(f"\n>>> SUCCESS! Proposal enriched.")
        print(f"--- New Title: {enriched.title}")
        print(f"--- Final Compressive Rationale: {enriched.compressive_rationale}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        memory.close()

if __name__ == "__main__":
    main()
