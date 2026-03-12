#!/usr/bin/env python3
"""
Полный тест работоспособности LEDGERMIND.

Что делает:
1. Очищает semantic, vector, sessions (сохраняет episodic.db)
2. Запускает background worker
3. Мониторит логи (worker сам делает reflection → enrichment → merging → promotion)

Использование:
    python scripts/full_system_test.py [--keep-events 500]
"""
import os
import shutil
import sqlite3
import time
import sys
import argparse
from datetime import datetime, timedelta

def print_header(text):
    print("\n" + "="*70)
    print(f">>> {text}")
    print("="*70 + "\n")

def main():
    parser = argparse.ArgumentParser(description='Full LEDGERMIND System Test')
    parser.add_argument('--keep-events', type=int, default=None, help='Keep only N most recent events')
    parser.add_argument('--storage', type=str, default=None, help='Storage path (default: ../.ledgermind)')
    args = parser.parse_args()

    storage_path = os.path.abspath(args.storage if args.storage else "../.ledgermind")
    ledgermind_dir = os.path.dirname(storage_path)
    
    print_header("FULL LEDGERMIND SYSTEM TEST")
    print(f"Storage: {storage_path}")
    
    # ============================================
    # STEP 1: Очистка (сохраняем episodic.db и .git)
    # ============================================
    print_header("STEP 1: Cleaning (preserving episodic.db, .git)")
    
    # Kill existing workers
    os.system("pkill -f 'background.py --storage' 2>/dev/null || true")
    os.system("pkill -f 'ledgermind-mcp' 2>/dev/null || true")
    time.sleep(2)
    
    to_remove = []
    if os.path.exists(storage_path):
        for item in os.listdir(storage_path):
            if item in ('episodic.db', '.git'):
                print(f"   ✓ Preserved: {item}")
                continue
            path = os.path.join(storage_path, item)
            to_remove.append(path)
    
    for path in to_remove:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
                print(f"   - Removed dir: {os.path.basename(path)}")
            else:
                os.remove(path)
                print(f"   - Removed file: {os.path.basename(path)}")
        except Exception as e:
            print(f"   ! Error removing {path}: {e}")
    
    # ============================================
    # STEP 2: Проверка episodic.db
    # ============================================
    print_header("STEP 2: Checking episodic.db")
    
    episodic_db = os.path.join(storage_path, "episodic.db")
    if not os.path.exists(episodic_db):
        print("ERROR: episodic.db not found!")
        sys.exit(1)
    
    conn = sqlite3.connect(episodic_db)
    cursor = conn.execute('SELECT COUNT(*) FROM events')
    event_count = cursor.fetchone()[0]
    
    cursor = conn.execute('SELECT MIN(timestamp), MAX(timestamp) FROM events')
    row = cursor.fetchone()
    oldest = row[0][:19] if row[0] else 'N/A'
    newest = row[1][:19] if row[1] else 'N/A'
    
    print(f"   Events: {event_count}")
    print(f"   Time range: {oldest} → {newest}")
    
    # ============================================
    # STEP 3: Омоложение дат (если нужно)
    # ============================================
    if args.keep_events and event_count > args.keep_events:
        print_header(f"STEP 3: Keeping only {args.keep_events} recent events")
        
        cursor = conn.execute('SELECT id, timestamp FROM events ORDER BY timestamp DESC LIMIT ?', (args.keep_events,))
        recent = cursor.fetchall()
        
        if recent:
            oldest_ts = recent[-1][1]
            newest_ts = recent[0][1]
            
            oldest_dt = datetime.fromisoformat(oldest_ts.replace('Z', '+00:00')).replace(tzinfo=None)
            newest_dt = datetime.fromisoformat(newest_ts.replace('Z', '+00:00')).replace(tzinfo=None)
            
            now = datetime.now()
            time_span = newest_dt - oldest_dt
            new_oldest = now - time_span
            shift_delta = new_oldest - oldest_dt
            
            event_ids = [e[0] for e in recent]
            placeholders = ','.join('?' * len(event_ids))
            conn.execute(f'DELETE FROM events WHERE id NOT IN ({placeholders})', event_ids)
            
            for eid, ts in recent:
                old_dt = datetime.fromisoformat(ts.replace('Z', '+00:00')).replace(tzinfo=None)
                new_ts = (old_dt + shift_delta).isoformat()
                conn.execute('UPDATE events SET timestamp = ? WHERE id = ?', (new_ts, eid))
            
            conn.commit()
            
            print(f"   Deleted: {event_count - len(recent)} old events")
            print(f"   New range: {new_oldest.strftime('%Y-%m-%d %H:%M')} → {now.strftime('%Y-%m-%d %H:%M')}")
            event_count = len(recent)
    
    conn.close()
    
    # ============================================
    # STEP 4: Сброс конфигурации
    # ============================================
    print_header("STEP 4: Resetting configuration")
    
    from ledgermind.core.api.memory import Memory
    memory = Memory(storage_path=storage_path)
    
    memory.semantic.meta.set_config("last_reflection_event_id", "0")
    memory.semantic.meta.set_config("arbitration_mode", "rich")
    memory.semantic.meta.set_config("client", "gemini")
    memory.semantic.meta.set_config("enrichment_model", "gemini-2.5-flash-lite")
    memory.semantic.meta.set_config("preferred_language", "russian")
    memory.semantic.meta.set_config("enrichment_mode", "rich")
    memory.semantic.meta.set_config("enrichment_language", "russian")
    memory.close()
    
    print("   ✓ Configuration reset")
    
    # ============================================
    # STEP 5: Запуск Background Worker
    # ============================================
    print_header("STEP 5: Starting Background Worker")
    
    log_path = os.path.join(ledgermind_dir, "ledgermind/logs/background_worker.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    # Clear old log
    if os.path.exists(log_path):
        open(log_path, 'w').close()
    
    worker_cmd = f"cd {ledgermind_dir}/ledgermind && nohup python src/ledgermind/server/background.py --storage {storage_path} --log {log_path} > /dev/null 2>&1 &"
    os.system(worker_cmd)
    
    time.sleep(3)
    
    # Check if worker started
    ps_output = os.popen(f"ps aux | grep 'background.py --storage {storage_path}' | grep -v grep").read()
    if ps_output:
        print(f"   ✓ Worker started")
        print(f"   Log file: {log_path}")
    else:
        print("   ✗ Worker failed to start!")
        sys.exit(1)
    
    # ============================================
    # STEP 6: Мониторинг логов
    # ============================================
    print_header("STEP 6: Monitoring Worker Logs")
    print("Watching for: reflection → proposals → enrichment → merging → decisions")
    print("Press Ctrl+C to stop monitoring (worker continues in background)\n")
    
    try:
        last_line_count = 0
        cycle = 0
        
        while True:
            time.sleep(10)
            cycle += 1
            
            if not os.path.exists(log_path):
                continue
            
            with open(log_path, 'r') as f:
                lines = f.readlines()
            
            # Показываем только новые строки
            new_lines = lines[last_line_count:]
            last_line_count = len(lines)
            
            if new_lines:
                timestamp = datetime.now().strftime('%H:%M:%S')
                print(f"\n--- {timestamp} (cycle {cycle}) ---")
                for line in new_lines[-30:]:  # Показываем последние 30 новых строк
                    # Сокращаем длинные строки
                    line = line.strip()
                    if len(line) > 150:
                        line = line[:150] + "..."
                    print(line)
            
            # Проверка на критические ошибки
            with open(log_path, 'r') as f:
                content = f.read()
                if 'ERROR' in content:
                    error_lines = [l for l in content.split('\n') if 'ERROR' in l and 'Failed to process' not in l]
                    if error_lines:
                        print(f"\n   ⚠️  ERRORS: {len(error_lines)}")
                        for el in error_lines[-3:]:
                            print(f"      {el[:120]}...")
            
            # Проверка прогресса
            with open(log_path, 'r') as f:
                content = f.read()
                
            progress_indicators = [
                ('Reflection', 'reflection'),
                ('Proposals', 'proposal_'),
                ('Enrichment', 'Enrichment cycle completed'),
                ('Merging', 'merging'),
                ('Decisions', 'decision_'),
                ('Promotion', 'Promotion:'),
                ('Coordinator', 'Coordinator stats'),
            ]
            
            print(f"\n   Progress:")
            for name, indicator in progress_indicators:
                count = content.count(indicator)
                if count > 0:
                    print(f"      ✓ {name}: {count} events")
            
            # Показать последнюю статистику coordinator
            if 'Coordinator stats' in content:
                for line in reversed(content.split('\n')):
                    if 'Coordinator stats' in line:
                        print(f"\n   Coordinator: {line.strip()}")
                        break
        
    except KeyboardInterrupt:
        print("\n\n   Monitoring stopped by user")
    
    # ============================================
    # STEP 7: Финальная статистика
    # ============================================
    print_header("STEP 7: Final Statistics")
    
    semantic_db = os.path.join(storage_path, "semantic_meta.db")
    if os.path.exists(semantic_db):
        conn = sqlite3.connect(semantic_db)
        
        cursor = conn.execute('SELECT kind, status, COUNT(*) FROM semantic_meta GROUP BY kind, status ORDER BY kind, status')
        print("\n=== Semantic Records ===")
        for row in cursor.fetchall():
            print(f"   {row[0]:<15} | {row[1]:<12} | {row[2]}")
        
        cursor = conn.execute('SELECT COUNT(*) FROM semantic_meta WHERE kind="decision"')
        decisions = cursor.fetchone()[0]
        
        cursor = conn.execute('SELECT COUNT(*) FROM semantic_meta WHERE kind="proposal"')
        proposals = cursor.fetchone()[0]
        
        cursor = conn.execute('SELECT COUNT(*) FROM semantic_meta WHERE enrichment_status="completed"')
        enriched = cursor.fetchone()[0]
        
        conn.close()
        
        print(f"\n   Summary:")
        print(f"      Decisions: {decisions}")
        print(f"      Proposals: {proposals}")
        print(f"      Enriched: {enriched}/{proposals}")
    
    print("\n" + "="*70)
    print(">>> TEST COMPLETE")
    print("="*70)
    print(f"\nWorker continues running in background.")
    print(f"Log file: {log_path}")
    print(f"To stop worker: pkill -f 'background.py --storage {storage_path}'")

if __name__ == "__main__":
    main()
