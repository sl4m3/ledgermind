import logging
import sys
import os

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import LedgermindConfig

def main():
    print("--- Hypotheses Rebuild Tool (2026-03-02) ---")
    
    # Path to the actual storage directory
    storage_path = os.path.abspath("../.ledgermind")
    print(f"Using storage path: {storage_path}")
    
    # 2. Initialize Memory
    try:
        # storage_path is the base directory containing episodic.db and semantic/
        memory = Memory(storage_path=storage_path)
        print("✓ Memory initialized successfully.")
        
        # Check vector store
        print(f"Vector Store Engine: {memory.vector.model_name}")
        
        # 3. Trigger Reflection
        print("\nStarting Reflection Cycle (Distillation + Pattern Discovery)...")
        proposals = memory.run_reflection()
        
        if proposals:
            print(f"\n✓ Generated/Updated {len(proposals)} proposals.")
            # List some results
            for p_id in proposals[:10]:
                print(f"  - Generated proposal: {p_id}")
        else:
            print("\n! No new proposals were generated. Check episodic logs for enough data.")
            
        print("\nRebuild complete.")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
