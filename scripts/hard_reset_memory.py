import os
import shutil
import sqlite3
import time
import sys
import logging
import re
import subprocess
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

sys.path.insert(0, os.path.abspath("src"))
from ledgermind.core.api.memory import Memory

storage_path = os.path.abspath("../.ledgermind")

def run_git(cmd, repo_path):
    try:
        subprocess.run(f"git {cmd}", shell=True, cwd=repo_path, check=True, capture_output=True)
    except Exception as e:
        print(f"   [GIT ERROR] {cmd}: {e}")

print(">>> RESET & NORMALIZATION: Ensuring Git consistency...")

# 1. Kill & Clean
os.system("pkill -f ledgermind-mcp")
if os.path.exists(storage_path):
    to_remove = ["semantic", "vector_index", "semantic_meta.db", "sessions", ".lock"]
    for item in to_remove:
        path = os.path.join(storage_path, item)
        if os.path.exists(path):
            if os.path.isdir(path): shutil.rmtree(path)
            else: os.remove(path)
            print(f"   - Removed: {item}")

# 2. Init & Reflection
memory = Memory(storage_path=storage_path)
memory.semantic.meta.set_config("last_reflection_event_id", "0")
memory.semantic.meta.set_config("arbitration_mode", "rich")
memory.semantic.meta.set_config("client", "gemini")
memory.semantic.meta.set_config("enrichment_model", "gemini-2.5-flash-lite")
memory.semantic.meta.set_config("preferred_language", "russian")

proposal_ids = memory.run_reflection()
print(f"   - Raw reflection complete. {len(proposal_ids)} files created.")

# 3. Normalization & SQL Update
print("3. Renaming files and updating meta-index...")
semantic_dir = os.path.join(storage_path, "semantic")
files = [f for f in os.listdir(semantic_dir) if f.endswith(".md") and f.startswith("proposal")]
files.sort()

base_time = datetime.now()
actual_db_path = memory.semantic.meta.db_path

for i, filename in enumerate(files):
    old_path = os.path.join(semantic_dir, filename)
    current_time = base_time + timedelta(seconds=i)
    ts_iso = current_time.replace(microsecond=0).isoformat()
    new_timestamp_str = current_time.strftime("%Y%m%d_%H%M%S") + "_000000"
    
    parts = filename.split('_')
    kind = parts[0]
    file_hash = parts[-1].replace('.md', '')
    new_filename = f"{kind}_{new_timestamp_str}_{file_hash}.md"
    new_path = os.path.join(semantic_dir, new_filename)
    
    # 1. Update SQLite
    with sqlite3.connect(actual_db_path) as conn:
        conn.execute("UPDATE semantic_meta SET fid = ?, timestamp = ? WHERE fid = ?", (new_filename, ts_iso, filename))
    
    # 2. Update Content (internal timestamp)
    with open(old_path, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = re.sub(r"timestamp: '.*?'", f"timestamp: '{ts_iso}'", content)
    with open(old_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    # 3. Rename
    os.rename(old_path, new_path)
    print(f"   - {filename} -> {new_filename}")

# 4. CRITICAL: Commit to Git Audit
print("4. Committing changes to internal Git repository...")
run_git("add .", semantic_dir)
run_git("commit -m 'System: Hard reset and strict timestamp normalization complete.'", semantic_dir)
print("   - Audit trail updated. Zombies eliminated.")

# 5. Final Sync & Indexing
memory.semantic.sync_meta_index()
memory._lifecycle_service.reindex_missing(limit=500)
memory.close()

print("\n>>> Reset Complete. Peace in our time.")
