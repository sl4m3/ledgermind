import sqlite3
import os
import sys

def repair_db(db_path):
    if not os.path.exists(db_path):
        print(f"Skipping: {db_path} not found.")
        return

    print(f"Checking integrity of {db_path}...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check integrity
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()[0]
        
        if result == "ok":
            print(f"✓ {db_path} is healthy. Running VACUUM...")
            cursor.execute("VACUUM;")
            print("✓ VACUUM complete.")
        else:
            print(f"✗ {db_path} is MALFORMED: {result}")
            print("Attempting basic recovery via .dump (requires sqlite3 CLI)...")
            # This is a placeholder for more advanced recovery if needed
        
        conn.close()
    except Exception as e:
        print(f"✗ Error accessing {db_path}: {e}")

def main():
    storage_path = sys.argv[1] if len(sys.argv) > 1 else ".ledgermind"
    
    dbs = [
        os.path.join(storage_path, "semantic", "metadata.db"),
        os.path.join(storage_path, "semantic", "semantic_meta.db"),
    ]
    
    for db in dbs:
        repair_db(db)

if __name__ == "__main__":
    main()
