import os
import shutil
import sqlite3
import time
import sys
import logging

# Configure logging to see internal messages
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add src to path
sys.path.insert(0, os.path.abspath("src"))
from ledgermind.core.api.memory import Memory

# Storage path should be one level up from the code directory
storage_path = os.path.abspath("../.ledgermind")

print(f"Storage path: {storage_path}")

print(">>> Hard Reset Script Starting...", flush=True)

# 1. Kill any running instances
print("1. Killing background workers and servers...", flush=True)
os.system("pkill -f ledgermind-mcp")
time.sleep(1)
print("   - Done: Background workers killed.", flush=True)

# 2. Targeted deletion (KEEPING episodic.db)
print("2. Deleting semantic knowledge and indexes...", flush=True)
if os.path.exists(storage_path):
    # List of items to remove to reset knowledge but keep events
    to_remove = [
        os.path.join(storage_path, "semantic"),
        os.path.join(storage_path, "vector_index"),
        os.path.join(storage_path, "semantic_meta.db"),
        os.path.join(storage_path, "sessions"),
        os.path.join(storage_path, ".lock")
    ]
    
    for item in to_remove:
        if os.path.exists(item):
            try:
                if os.path.isdir(item):
                    shutil.rmtree(item)
                else:
                    os.remove(item)
                print(f"   - Removed: {item}", flush=True)
            except Exception as e:
                print(f"   [WARNING] Failed to remove {item}: {e}", flush=True)

# 3. Initialization and Watermark Reset
print("3. Initializing Memory & Forcing Watermark to 0...", flush=True)
memory = Memory(storage_path=storage_path)
# Ensure clean start
memory.semantic.meta.set_config("last_reflection_event_id", "0")
memory.semantic.meta.set_config("arbitration_mode", "rich")
memory.semantic.meta.set_config("client", "gemini")
memory.semantic.meta.set_config("enrichment_model", "gemini-2.5-flash-lite")
print("   - Success: System ready for full re-analysis.", flush=True)

# 4. Incremental Reflection
print("4. Running Full Reflection (Catching up)...", flush=True)
proposal_ids = memory.run_reflection()
print(f"   - Reflection complete. Created {len(proposal_ids)} total proposals.", flush=True)

# 5. Vector Indexing
print("5. Calculating vectors for new proposals...", flush=True)
reindexed_count = memory.reindex_missing()
print(f"   - Indexing complete. Indexed {reindexed_count} documents in vector store.", flush=True)

memory.close()
print("\n>>> Hard reset and re-analysis complete! (Episodic memory preserved)", flush=True)
