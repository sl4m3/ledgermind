import sqlite3
import json
from typing import List, Optional, Dict, Any, Tuple
from ledgermind.core.core.schemas import MemoryEvent

class EpisodicStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
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
        with sqlite3.connect(self.db_path) as conn:
            # Handle context serialization for Pydantic models
            context_data = event.context
            if hasattr(context_data, 'model_dump'):
                context_dict = context_data.model_dump(mode='json')
            else:
                context_dict = context_data
                
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE events SET linked_id = ?, link_strength = ? WHERE id = ?", (semantic_id, strength, event_id))

    def query(self, limit: int = 100, status: Optional[str] = 'active') -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            if status:
                cursor = conn.execute(
                    "SELECT id, source, kind, content, context, timestamp, status, linked_id, link_strength FROM events WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (status, limit)
                )
            else:
                cursor = conn.execute(
                    "SELECT id, source, kind, content, context, timestamp, status, linked_id, link_strength FROM events ORDER BY id DESC LIMIT ?",
                    (limit,)
                )
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

    def count_links_for_semantic(self, semantic_id: str) -> Tuple[int, float]:
        """Returns (count, total_strength) for a given semantic decision."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*), SUM(link_strength) FROM events WHERE linked_id = ?",
                (semantic_id,)
            ).fetchone()
            return (row[0] or 0, row[1] or 0.0)

    def mark_archived(self, event_ids: List[int]):
        if not event_ids: return
        placeholders = ','.join(['?'] * len(event_ids))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE events SET status = 'archived' WHERE id IN ({placeholders})", event_ids) # nosec B608

    def find_duplicate(self, event: MemoryEvent) -> Optional[int]:
        """Checks if an identical event (source, kind, content) already exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id FROM events WHERE source = ? AND kind = ? AND content = ? LIMIT 1",
                (event.source, event.kind, event.content)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def physical_prune(self, event_ids: List[int]):
        if not event_ids: return
        # I2 Protection: Only prune if NOT linked
        placeholders = ','.join(['?'] * len(event_ids))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"DELETE FROM events WHERE id IN ({placeholders}) AND linked_id IS NULL", event_ids) # nosec B608
