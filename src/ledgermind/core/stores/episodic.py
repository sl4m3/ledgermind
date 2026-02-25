import sqlite3
import json
import threading
from typing import List, Optional, Dict, Any, Tuple
from contextlib import contextmanager
from ledgermind.core.core.schemas import MemoryEvent

class EpisodicStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _get_conn(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            # Set factory for dict-like rows
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=10000")
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source TEXT,
                        kind TEXT,
                        content TEXT,
                        context TEXT,
                        timestamp TEXT,
                        status TEXT DEFAULT 'active',
                        linked_id TEXT DEFAULT NULL,
                        link_strength REAL DEFAULT 1.0
                    )
                """)
                # Migration: Add link_strength if it doesn't exist
                try:
                    conn.execute("ALTER TABLE events ADD COLUMN link_strength REAL DEFAULT 1.0")
                except sqlite3.OperationalError:
                    pass

    def append(self, event: MemoryEvent, linked_id: Optional[str] = None, link_strength: float = 1.0) -> int:
        # Step 0: Last-resort duplicate check
        existing_id = self.find_duplicate(event, linked_id=linked_id)
        if existing_id:
            return existing_id

        with self._get_conn() as conn:
            # Handle context serialization for Pydantic models
            context_data = event.context
            if hasattr(context_data, 'model_dump'):
                context_dict = context_data.model_dump(mode='json')
            else:
                context_dict = context_data
                
            with conn:
                cursor = conn.execute(
                    "INSERT INTO events (source, kind, content, context, timestamp, linked_id, link_strength) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.source,
                        event.kind,
                        event.content,
                        json.dumps(context_dict),
                        event.timestamp.isoformat(),
                        linked_id,
                        link_strength
                    )
                )
                return cursor.lastrowid

    def link_to_semantic(self, event_id: int, semantic_id: str, strength: float = 1.0):
        with self._get_conn() as conn:
            with conn:
                conn.execute("UPDATE events SET linked_id = ?, link_strength = ? WHERE id = ?", (semantic_id, strength, event_id))

    def unlink_all_for_semantic(self, semantic_id: str):
        """Clears linked_id for all events pointing to this semantic decision."""
        with self._get_conn() as conn:
            with conn:
                conn.execute("UPDATE events SET linked_id = NULL WHERE linked_id = ?", (semantic_id,))

    def query(self, limit: int = 100, status: Optional[str] = 'active', after_id: Optional[int] = None, order: str = 'DESC') -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            query_parts = []
            params = []
            
            if status:
                query_parts.append("status = ?")
                params.append(status)
            
            if after_id is not None:
                query_parts.append("id > ?")
                params.append(after_id)
            
            where_clause = ""
            if query_parts:
                where_clause = "WHERE " + " AND ".join(query_parts)
            
            direction = 'ASC' if order.upper() == 'ASC' else 'DESC'
            sql = f"SELECT id, source, kind, content, context, timestamp, status, linked_id, link_strength FROM events {where_clause} ORDER BY id {direction} LIMIT ?"  # nosec B608
            params.append(limit)
            
            cursor = conn.execute(sql, params)
            return [
                {
                    "id": row[0],
                    "source": row[1],
                    "kind": row[2],
                    "content": row[3],
                    "context": json.loads(row[4]),
                    "timestamp": row[5],
                    "status": row[6],
                    "linked_id": row[7],
                    "link_strength": row[8]
                } for row in cursor.fetchall()
            ]

    def get_linked_event_ids(self, semantic_id: str) -> List[int]:
        """Returns a list of event IDs linked to a given semantic decision."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT id FROM events WHERE linked_id = ?", (semantic_id,))
            return [row[0] for row in cursor.fetchall()]

    def count_links_for_semantic(self, semantic_id: str) -> Tuple[int, float]:
        """Returns (count, total_strength) for a given semantic decision."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*), SUM(link_strength) FROM events WHERE linked_id = ?",
                (semantic_id,)
            ).fetchone()
            return (row[0] or 0, row[1] or 0.0)

    def mark_archived(self, event_ids: List[int]):
        if not event_ids: return
        placeholders = ','.join(['?'] * len(event_ids))
        with self._get_conn() as conn:
            with conn:
                conn.execute(f"UPDATE events SET status = 'archived' WHERE id IN ({placeholders})", event_ids) # nosec B608

    def find_duplicate(self, event: MemoryEvent, linked_id: Optional[str] = None, ignore_links: bool = False) -> Optional[int]:
        """Checks if an identical event (source, kind, content, context) already exists."""
        # Handle context serialization for comparison
        context_data = event.context
        if hasattr(context_data, 'model_dump'):
            context_dict = context_data.model_dump(mode='json')
        else:
            context_dict = context_data
        context_json = json.dumps(context_dict)

        with self._get_conn() as conn:
            sql = "SELECT id FROM events WHERE source = ? AND kind = ? AND content = ? AND context = ?"
            params = [event.source, event.kind, event.content, context_json]
            
            if not ignore_links:
                if linked_id is not None:
                    sql += " AND linked_id = ?"
                    params.append(linked_id)
                else:
                    sql += " AND linked_id IS NULL"
                
            sql += " LIMIT 1"
            
            cursor = conn.execute(sql, params)
            row = cursor.fetchone()
            return row[0] if row else None

    def physical_prune(self, event_ids: List[int]):
        if not event_ids: return
        # I2 Protection: Only prune if NOT linked
        placeholders = ','.join(['?'] * len(event_ids))
        with self._get_conn() as conn:
            with conn:
                conn.execute(f"DELETE FROM events WHERE id IN ({placeholders}) AND linked_id IS NULL", event_ids) # nosec B608

    def count_events(self, status: Optional[str] = 'active') -> int:
        """Returns the number of events with the given status."""
        with self._get_conn() as conn:
            if status:
                row = conn.execute("SELECT COUNT(*) FROM events WHERE status = ?", (status,)).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
            return row[0] or 0
