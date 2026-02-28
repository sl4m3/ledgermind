import os
import json
import yaml
import sqlite3
from pathlib import Path

# Configuration
MEMORY_PATH = os.path.abspath("../.ledgermind")
SEMANTIC_DIR = os.path.join(MEMORY_PATH, "semantic")
DB_PATH = os.path.join(SEMANTIC_DIR, "semantic_meta.db")

def migrate():
    print(f"Starting migration of proposals in {SEMANTIC_DIR}...")
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Find all proposals in DB without enrichment_status
    query = "SELECT fid, context_json FROM semantic_meta WHERE kind='proposal' AND status IN ('draft', 'active') AND context_json NOT LIKE '%enrichment_status%';"
    rows = cursor.execute(query).fetchall()
    
    print(f"Found {len(rows)} proposals to migrate.")
    
    updated_count = 0
    for fid, ctx_json in rows:
        try:
            # Update DB context
            ctx = json.loads(ctx_json)
            ctx['enrichment_status'] = 'pending'
            new_ctx_json = json.dumps(ctx)
            
            # Update File
            file_path = os.path.join(SEMANTIC_DIR, fid)
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Simple regex-free YAML update
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        data = yaml.safe_load(parts[1])
                        if 'context' not in data: data['context'] = {}
                        data['context']['enrichment_status'] = 'pending'
                        
                        # Stringify back
                        new_yaml = yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()
                        new_content = f"---\n{new_yaml}\n---\n{parts[2]}"
                        
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(new_content)
            
            # Commit to DB
            cursor.execute("UPDATE semantic_meta SET context_json = ? WHERE fid = ?", (new_ctx_json, fid))
            updated_count += 1
            print(f"✓ Migrated {fid}")
            
        except Exception as e:
            print(f"✗ Failed to migrate {fid}: {e}")

    conn.commit()
    conn.close()
    print(f"\nMigration complete. {updated_count} proposals queued for enrichment.")

if __name__ == "__main__":
    migrate()
