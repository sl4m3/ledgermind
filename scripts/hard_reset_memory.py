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
backup_path = "/data/data/com.termux/files/home/.gemini/tmp/episodic.db.backup"
episodic_db = os.path.join(storage_path, "episodic.db")

print(f"Storage path: {storage_path}")

print(">>> Hard Reset Script Starting...", flush=True)

# 1. Kill any running instances
print("1. Killing background workers and servers...", flush=True)
os.system("pkill -f ledgermind-mcp")
time.sleep(1)
print("   - Done: Background workers killed.", flush=True)

# 2. Complete deletion and restoration
print("2. Deleting knowledge base and restoring episodic.db...", flush=True)
if os.path.exists(storage_path):
    try:
        shutil.rmtree(storage_path)
        print(f"   - Removed existing storage: {storage_path}", flush=True)
    except Exception as e:
        print(f"   [WARNING] Failed to remove some files: {e}", flush=True)

os.makedirs(storage_path, exist_ok=True)
if os.path.exists(backup_path):
    shutil.copy2(backup_path, episodic_db)
    print("   - Success: episodic.db restored from backup.", flush=True)
else:
    print(f"   [WARNING] Backup not found at {backup_path}. Database will be empty.", flush=True)

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

# 5. Enrichment
print("5. Starting Enrichment Batch (LLM Synthesis)...", flush=True)
# We use the existing memory object to avoid re-opening overhead/locks
from ledgermind.core.reasoning.llm_enrichment import LLMEnricher
enricher = LLMEnricher(mode="rich", client_name="gemini", model_name="gemini-2.5-flash-lite")
results = enricher.process_batch(memory)

if not results:
    print("   [WARNING] No proposals were enriched.", flush=True)
else:
    print(f"   - Done: Enriched {len(results)} proposals.", flush=True)

memory.close()
print("\n>>> Hard reset and full rebuild complete!", flush=True)
