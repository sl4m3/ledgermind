import os
import sys
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
sys.path.insert(0, os.path.abspath("src"))

from ledgermind.core.api.memory import Memory
from ledgermind.core.reasoning.enrichment import LLMEnricher

def main():
    storage_path = os.path.abspath("../.ledgermind")
    print(f">>> Testing Enrichment on SINGLE item (Storage: {storage_path})")

    memory = Memory(storage_path=storage_path)
    try:
        # We run auto-enrichment with limit=1 to process only the first pending item
        enricher = LLMEnricher()
        enricher.run_auto_enrichment(memory, limit=1)
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        memory.close()
        print("\n>>> test complete!")

if __name__ == "__main__":
    main()
