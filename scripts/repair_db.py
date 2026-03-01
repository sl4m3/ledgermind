import sqlite3
import os
import sys

def repair_episodic(db_path):
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    print(f"Repairing episodic database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Count duplicates before
        cursor.execute("""
            SELECT COUNT(*) FROM events e1
            WHERE EXISTS (
                SELECT 1 FROM events e2 
                WHERE e1.source = e2.source 
                  AND e1.kind = e2.kind 
                  AND e1.content = e2.content 
                  AND e1.context = e2.context 
                  AND e1.timestamp = e2.timestamp 
                  AND e1.id > e2.id
            )
        """)
        dup_count = cursor.fetchone()[0]
        print(f"Found {dup_count} duplicate events.")

        if dup_count > 0:
            # 2. Delete duplicates keeping the lowest ID
            cursor.execute("""
                DELETE FROM events 
                WHERE id IN (
                    SELECT e1.id FROM events e1
                    WHERE EXISTS (
                        SELECT 1 FROM events e2 
                        WHERE e1.source = e2.source 
                          AND e1.kind = e2.kind 
                          AND e1.content = e2.content 
                          AND e1.context = e2.context 
                          AND e1.timestamp = e2.timestamp 
                          AND e1.id > e2.id
                    )
                )
            """)
            conn.commit()
            print(f"Successfully deleted {dup_count} duplicates.")
            
            # 3. Rebuild index to include timestamp if not already done by the app
            print("Rebuilding index...")
            cursor.execute("DROP INDEX IF EXISTS idx_events_duplicate")
            cursor.execute("CREATE INDEX idx_events_duplicate ON events (source, kind, content, timestamp)")
            conn.commit()
            
            # 4. Vacuum to reclaim space
            print("Vacuuming database...")
            conn.execute("VACUUM")
            print("Done.")
        else:
            print("No duplicates found. Database is clean.")

    except Exception as e:
        print(f"Error during repair: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    db_path = "../.ledgermind/episodic.db"
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    repair_episodic(db_path)
