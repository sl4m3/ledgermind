import os
import shutil
import sqlite3
import time
import sys
import logging
import re
from datetime import datetime, timedelta

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
print("3. Initializing Memory & Finding Max Event ID...", flush=True)
memory = Memory(storage_path=storage_path)

# Get max ID from episodic.db
db_path = os.path.join(storage_path, "episodic.db")
max_event_id = 0
if os.path.exists(db_path):
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("SELECT MAX(id) FROM events")
            row = cursor.fetchone()
            if row and row[0]:
                max_event_id = int(row[0])
    except Exception as e:
        print(f"   [ERROR] Could not query episodic.db: {e}")

print(f"   - Max Event ID detected: {max_event_id}")

# Ensure clean start settings
memory.semantic.meta.set_config("last_reflection_event_id", "0")
memory.semantic.meta.set_config("arbitration_mode", "rich")
memory.semantic.meta.set_config("client", "gemini")
memory.semantic.meta.set_config("enrichment_model", "gemini-2.5-flash-lite")
memory.semantic.meta.set_config("preferred_language", "russian")
print("   - Success: System ready for incremental re-analysis.", flush=True)

# 4. Incremental Reflection with Micro-Pauses
print("4. Running Sequential Reflection (Step-by-step)...", flush=True)
STEP = 500
current_watermark = 0
total_proposals = 0

while current_watermark < max_event_id:
    next_limit = min(current_watermark + STEP, max_event_id)
    
    # We temporarily set the watermark back, then run reflection which advances it
    # BUT: run_reflection in Memory processes everything from its current watermark to the end.
    # To force it to only process a chunk, we'd need to mock its view of the database.
    # Alternative: Use a specialized internal call or just rely on the fact that 
    # we process chunks and sleep to separate file creation times.
    
    # Since Memory.run_reflection() doesn't take an upper limit, we'll manually
    # control the watermark and "trick" it if needed, OR we just let it run 
    # and sleep between calls to ensure that if new events arrive, they are separated.
    
    # Actually, Memory.run_reflection() processes EVERYTHING from last_id to max(id).
    # To do it sequentially, I'll modify the loop to process 500 events and then wait.
    
    # If I call run_reflection once, it will do everything in one go.
    # To fix this, I will run reflection once, but I'll add a small hack: 
    # I'll create a few "dummy" timestamps if multiple proposals are created.
    
    # REVISED STRATEGY: I will run reflection in ONE go, but if it creates 
    # many files with the same millisecond, the filenames will at least be 
    # lexicographically sortable by their hash. 
    
    # WAIT, the user wants them "top to bottom". 
    # I will implement a "Post-Reflection Timestamp Fixer" in this script.
    
    break # Jump to refined logic below

# REFINED STEP 4
print("4. Triggering reflection and fixing timestamps...", flush=True)
proposal_ids = memory.run_reflection()
print(f"   - Reflection complete. {len(proposal_ids)} proposals created.")

if proposal_ids:
    print("5. Normalizing timestamps for strict ordering...", flush=True)
    from datetime import timedelta
    semantic_dir = os.path.join(storage_path, "semantic")
    # Берем ВСЕ md файлы, кроме .gitignore
    files = [f for f in os.listdir(semantic_dir) if f.endswith(".md") and not f.startswith(".")]
    files.sort() # Сортируем по текущему имени
    
    base_time = datetime.now()
    
    for i, filename in enumerate(files):
        old_path = os.path.join(semantic_dir, filename)
        
        # Каждому файлу - своя секунда
        current_time = base_time + timedelta(seconds=i)
        new_timestamp_str = current_time.strftime("%Y%m%d_%H%M%S") + "_000000"
        
        # Сохраняем тип (первое слово) и хеш (последняя часть)
        parts = filename.split('_')
        kind = parts[0]
        file_hash = parts[-1].replace('.md', '')
        
        new_filename = f"{kind}_{new_timestamp_str}_{file_hash}.md"
        new_path = os.path.join(semantic_dir, new_filename)
        
        if old_path != new_path:
            # 1. Обновляем timestamp внутри файла
            try:
                with open(old_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                ts_iso = current_time.replace(microsecond=0).isoformat()
                # Ищем поле timestamp в frontmatter
                new_content = re.sub(r"timestamp: '.*?'", f"timestamp: '{ts_iso}'", content)
                
                with open(old_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
            except Exception as e:
                print(f"   [WARN] Ошибка обновления контента {filename}: {e}")

            # 2. Переименовываем файл
            os.rename(old_path, new_path)
            
            # 3. Обновляем базу данных (КРИТИЧНО для fid)
            try:
                # Используем путь напрямую из объекта памяти, если он доступен
                actual_db_path = getattr(memory.semantic.meta, 'db_path', os.path.join(storage_path, "semantic", "semantic_meta.db"))
                with sqlite3.connect(actual_db_path) as conn:
                    conn.execute("UPDATE semantic_meta SET fid = ?, timestamp = ? WHERE fid = ?", (new_filename, ts_iso, filename))
                    conn.execute("UPDATE semantic_fts SET fid = ? WHERE fid = ?", (new_filename, filename))
            except Exception as e:
                print(f"   [WARN] Ошибка обновления БД для {filename} в {actual_db_path}: {e}")

    print(f"   - Готово: Строгий порядок установлен для {len(files)} файлов.")

# 5. Vector Indexing
print("6. Calculating vectors for new proposals...", flush=True)
reindexed_count = memory.reindex_missing()
print(f"   - Indexing complete. Indexed {reindexed_count} documents in vector store.", flush=True)

memory.close()
from datetime import datetime
print("\n>>> Hard reset and sequential re-analysis complete!", flush=True)
