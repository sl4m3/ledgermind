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
    print(f">>> Initializing Enrichment Pipeline (Storage: {storage_path})")

    memory = Memory(storage_path=storage_path)
    try:
        # Business logic is fully encapsulated in LLMEnricher facade
        enricher = LLMEnricher()
        enricher.run_auto_enrichment(memory)
    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
    finally:
        memory.close()
        print("\n>>> session complete!")

if __name__ == "__main__":
    main()
