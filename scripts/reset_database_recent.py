#!/usr/bin/env python3
"""
Скрипт очистки и омоложения базы данных LEDGERMIND.

Что делает:
1. Оставляет только N последних событий (по timestamp)
2. Сдвигает все даты так, чтобы последнее событие было сегодня
3. Сохраняет относительные интервалы между событиями

Использование:
    python scripts/reset_database_recent.py [--events 2000] [--storage path]
"""
import os
import sys
import sqlite3
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath("src"))

def main():
    parser = argparse.ArgumentParser(description='Reset database to recent events only')
    parser.add_argument('--events', type=int, default=2000, help='Number of recent events to keep (default: 2000)')
    parser.add_argument('--storage', type=str, default=None, help='Storage path (default: ../.ledgermind)')
    args = parser.parse_args()

    storage_path = os.path.abspath(args.storage if args.storage else "../.ledgermind")
    db_path = os.path.join(storage_path, "episodic.db")
    semantic_db_path = os.path.join(storage_path, "semantic_meta.db")

    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    print(f">>> Resetting database in {storage_path}")
    print(f"    Keeping {args.events} most recent events")
    print()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 1. Найти последние N событий
    print(">>> Step 1: Finding recent events...")
    cursor = conn.execute('''
        SELECT id, timestamp FROM events
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (args.events,))

    recent_events = cursor.fetchall()
    if not recent_events:
        print("No events found in database!")
        sys.exit(1)

    print(f"    Found {len(recent_events)} events")

    # 2. Определить временной диапазон
    oldest_timestamp = recent_events[-1]['timestamp']
    newest_timestamp = recent_events[0]['timestamp']

    print(f"    Original range: {oldest_timestamp} → {newest_timestamp}")

    # 3. Вычислить сдвиг
    now = datetime.now()
    oldest_dt = datetime.fromisoformat(oldest_timestamp.replace('Z', '+00:00')).replace(tzinfo=None)
    newest_dt = datetime.fromisoformat(newest_timestamp.replace('Z', '+00:00')).replace(tzinfo=None)

    # Сдвиг: чтобы oldest стал (now - (newest - oldest))
    time_span = newest_dt - oldest_dt
    new_oldest = now - time_span

    shift_delta = new_oldest - oldest_dt

    print(f"    Time span: {time_span}")
    print(f"    New range: {new_oldest} → {now}")
    print(f"    Shift delta: {shift_delta}")
    print()

    # 4. Удалить старые события
    print(">>> Step 2: Deleting old events...")
    event_ids_to_keep = [e['id'] for e in recent_events]
    placeholders = ','.join('?' * len(event_ids_to_keep))

    cursor = conn.execute(f'''
        DELETE FROM events
        WHERE id NOT IN ({placeholders})
    ''', event_ids_to_keep)

    deleted_count = cursor.rowcount
    print(f"    Deleted {deleted_count} old events")
    print()

    # 5. Обновить timestamps
    print(">>> Step 3: Updating timestamps...")
    updated_count = 0
    batch_size = 500

    for i in range(0, len(recent_events), batch_size):
        batch = recent_events[i:i+batch_size]
        for event in batch:
            old_ts = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00')).replace(tzinfo=None)
            new_ts = old_ts + shift_delta
            new_ts_str = new_ts.isoformat()

            conn.execute('''
                UPDATE events
                SET timestamp = ?
                WHERE id = ?
            ''', (new_ts_str, event['id']))

            updated_count += 1

        conn.commit()
        print(f"    Updated {updated_count}/{len(recent_events)} events...")

    print(f"    Total updated: {updated_count} events")
    print()

    # 6. Очистить semantic store (решения и proposal устарели)
    print(">>> Step 4: Cleaning semantic store...")
    if os.path.exists(semantic_db_path):
        semantic_conn = sqlite3.connect(semantic_db_path)

        # Удалить все решения и proposal (они ссылаются на старые event_id)
        cursor = semantic_conn.execute('''
            DELETE FROM semantic_meta
            WHERE kind IN ('decision', 'proposal')
        ''')
        deleted_semantic = cursor.rowcount

        # Сбросить связи на события
        cursor = semantic_conn.execute('''
            UPDATE semantic_meta
            SET context_json = json_remove(context_json, '$.evidence_event_ids')
            WHERE context_json IS NOT NULL
        ''')
        updated_links = cursor.rowcount

        semantic_conn.commit()
        semantic_conn.close()

        print(f"    Deleted {deleted_semantic} decisions/proposals")
        print(f"    Cleared {updated_links} evidence_event_ids references")
    else:
        print("    Semantic store not found, skipping...")
    print()

    # 7. VACUUM для оптимизации
    print(">>> Step 5: Optimizing database...")
    conn.execute("VACUUM")
    conn.commit()

    # Получить размер файла
    db_size = os.path.getsize(db_path) / (1024 * 1024)  # MB
    print(f"    Database size: {db_size:.2f} MB")
    print()

    conn.close()

    print(">>> Database reset complete!")
    print()
    print("Summary:")
    print(f"  - Events kept: {len(recent_events)}")
    print(f"  - Events deleted: {deleted_count}")
    print(f"  - Time range: {new_oldest.strftime('%Y-%m-%d %H:%M')} → {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"  - Decisions/proposals cleared: {deleted_semantic if os.path.exists(semantic_db_path) else 0}")
    print()
    print("Next steps:")
    print("  1. Run: python scripts/hard_reset_memory.py")
    print("  2. Run: python scripts/enrich_hypotheses.py")
    print("  3. Run: python scripts/run_merging.py")

if __name__ == "__main__":
    main()
