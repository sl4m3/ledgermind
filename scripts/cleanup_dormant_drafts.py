#!/usr/bin/env python3
"""
Очистка старых draft proposal из semantic store.

Что делает:
1. Находит draft proposal старше N дней
2. Удаляет их из semantic store
3. Очищает evidence_event_ids в связанных записях

Использование:
    python scripts/cleanup_dormant_drafts.py [--days 7] [--dry-run] [--storage path]
"""
import os
import sys
import sqlite3
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath("src"))

def main():
    parser = argparse.ArgumentParser(description='Cleanup old draft proposals')
    parser.add_argument('--days', type=int, default=7, help='Delete drafts older than N days (default: 7)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without modifying')
    parser.add_argument('--storage', type=str, default=None, help='Storage path (default: ../.ledgermind)')
    args = parser.parse_args()

    storage_path = os.path.abspath(args.storage if args.storage else "../.ledgermind")
    semantic_db_path = os.path.join(storage_path, "semantic_meta.db")
    episodic_db_path = os.path.join(storage_path, "episodic.db")

    if not os.path.exists(semantic_db_path):
        print(f"Error: Semantic database not found at {semantic_db_path}")
        sys.exit(1)

    print(f">>> Cleaning up draft proposals in {storage_path}")
    print(f"    Threshold: {args.days} days")
    if args.dry_run:
        print("    DRY RUN - No changes will be made")
    print()

    conn = sqlite3.connect(semantic_db_path)
    conn.row_factory = sqlite3.Row

    # Найти draft proposal старше N дней
    cutoff_date = (datetime.now() - timedelta(days=args.days)).isoformat()
    
    cursor = conn.execute('''
        SELECT fid, kind, status, timestamp, enrichment_status
        FROM semantic_meta
        WHERE status = 'draft'
          AND timestamp < ?
        ORDER BY timestamp
    ''', (cutoff_date,))

    old_drafts = cursor.fetchall()
    
    if not old_drafts:
        print(f">>> No draft proposals older than {args.days} days found.")
        conn.close()
        return

    print(f"Found {len(old_drafts)} old draft proposals:")
    print(f"{'FID':<50} | kind | status | timestamp")
    print("-" * 90)

    draft_fids = []
    for row in old_drafts:
        fid = row['fid']
        draft_fids.append(fid)
        ts = row['timestamp'][:19] if row['timestamp'] else 'N/A'
        print(f"✓ {fid[:45]}... | {row['kind']:<6} | {row['status']:<8} | {ts}")

    print()

    if not args.dry_run:
        # Удалить draft proposal
        placeholders = ','.join('?' * len(draft_fids))
        cursor = conn.execute(f'''
            DELETE FROM semantic_meta
            WHERE fid IN ({placeholders})
        ''', draft_fids)
        deleted_count = cursor.rowcount
        print(f">>> Deleted {deleted_count} draft proposals from semantic_meta")

        # Очистить evidence_event_ids в связанных записях (если есть)
        # Это предотвратит ссылки на удалённые proposal
        print(">>> Cleaning up references to deleted proposals...")
        
        # Получить все context_json и обновить те, что ссылаются на удалённые
        cursor = conn.execute('SELECT fid, context_json FROM semantic_meta WHERE context_json IS NOT NULL')
        updated_count = 0
        for row in cursor.fetchall():
            import json
            fid = row['fid']
            ctx = json.loads(row['context_json'])
            
            # Проверить и удалить ссылки
            modified = False
            
            # Проверить superseded_by
            if ctx.get('superseded_by') in draft_fids:
                ctx['superseded_by'] = None
                modified = True
            
            # Проверить merged_into
            if ctx.get('merged_into') in draft_fids:
                ctx['merged_into'] = None
                modified = True
            
            if modified:
                conn.execute('''
                    UPDATE semantic_meta
                    SET context_json = ?
                    WHERE fid = ?
                ''', (json.dumps(ctx), fid))
                updated_count += 1

        conn.commit()
        print(f">>> Cleaned up {updated_count} references in other records")
    else:
        print(f">>> Would delete {len(old_drafts)} draft proposals")

    conn.close()

    # Очистка episodic.db от ссылок на удалённые proposal
    if os.path.exists(episodic_db_path) and not args.dry_run:
        episodic_conn = sqlite3.connect(episodic_db_path)
        
        # Очистить linked_id если он ссылается на удалённый proposal
        placeholders = ','.join('?' * len(draft_fids))
        cursor = episodic_conn.execute(f'''
            UPDATE events
            SET linked_id = NULL
            WHERE linked_id IN ({placeholders})
        ''', draft_fids)
        episodic_conn.commit()
        episodic_conn.close()
        print(f">>> Cleaned up {cursor.rowcount} episodic event links")

    print()
    print(">>> Cleanup complete!")

if __name__ == "__main__":
    main()
