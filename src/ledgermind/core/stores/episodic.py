import sqlite3
import json
import threading
from typing import List, Optional, Dict, Any, Tuple
from contextlib import contextmanager
from ledgermind.core.core.schemas import MemoryEvent

from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool, Pool
from sqlalchemy.orm import sessionmaker, Session

from ledgermind.core.utils.result import Result, ErrorCode, safe_execute, unwrap_result

class EpisodicStore:
    def __init__(self, db_path: str, pool_size: int = 3):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.pool_size = pool_size

        self.engine = create_engine(
            f"sqlite:///{db_path}",
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=2,
            connect_args={
                'timeout': 30.0,
                'check_same_thread': False,
                'isolation_level': None,
            },
            echo=False,
            pool_pre_ping=True,
        )
        self.Session = sessionmaker(bind=self.engine)

        self._init_db()
        self._warm_up_pool()

    def _warm_up_pool(self):
        for _ in range(min(2, self.pool_size)):
            with self._get_conn():
                pass

    @contextmanager
    def _get_conn(self):
        session = self.Session()
        try:
            conn = session.connection()
            conn.connection.row_factory = sqlite3.Row
            yield conn.connection
        finally:
            session.close()

    def _get_pool_status(self) -> Dict[str, int]:
        pool: Pool = self.engine.pool
        return {
            'size': pool.size(),
            'checked_in': pool.checkedin(),
            'checked_out': pool.checkedout(),
            'overflow': pool.overflow(),
        }

    def close(self):
        if hasattr(self, 'engine'):
            self.engine.dispose()

    def _init_db(self):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
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
                
                # Performance: Add index for duplicate detection
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_duplicate ON events (source, kind, content, timestamp)")

    def _serialize_context(self, context_data: Any) -> str:
        if not context_data:
            return "{}"
        if hasattr(context_data, 'model_dump'):
            # Convert Pydantic models to dict first
            data = context_data.model_dump(mode='json')
        else:
            data = context_data
            
        # Ensure stable serialization with sort_keys=True for duplicate detection
        return json.dumps(data, sort_keys=True, default=str)

    def append(self, event: MemoryEvent, linked_id: Optional[str] = None, link_strength: float = 1.0) -> Result[int]:
        def _do_append():
            # Step 0: Last-resort duplicate check
            existing_result = self.find_duplicate(event, linked_id=linked_id)
            if existing_result and existing_result.value:
                return existing_result.value

            with self._get_conn() as conn:
                context_json = self._serialize_context(event.context)
                cursor = conn.execute(
                    "INSERT INTO events (source, kind, content, context, timestamp, linked_id, link_strength) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.source,
                        event.kind,
                        event.content,
                        context_json,
                        event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
                        linked_id,
                        link_strength
                    )
                )
                return cursor.lastrowid
        return safe_execute(_do_append)

    def link_to_semantic(self, event_id: int, semantic_id: str, strength: float = 1.0):
        with self._get_conn() as conn:
            conn.execute("UPDATE events SET linked_id = ?, link_strength = ? WHERE id = ?", (semantic_id, strength, event_id))

    def unlink_all_for_semantic(self, semantic_id: str):
        """Clears linked_id for all events pointing to this semantic decision."""
        with self._get_conn() as conn:
            conn.execute("UPDATE events SET linked_id = NULL WHERE linked_id = ?", (semantic_id,))

    def get_by_ids(self, ids: List[int]) -> List[Dict[str, Any]]:
        """Fetches multiple events by their IDs."""
        if not ids:
            return []
        
        # Use parameterized query with correct number of placeholders
        placeholders = ",".join(["?"] * len(ids))
        sql_template = "SELECT * FROM events WHERE id IN ({}) ORDER BY id ASC"
        query = sql_template.format(placeholders)
        
        with self._get_conn() as conn:
            rows = conn.execute(query, ids).fetchall()
            return [dict(row) for row in rows]

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
            sql_template = "SELECT id, source, kind, content, context, timestamp, status, linked_id, link_strength FROM events {} ORDER BY id {} LIMIT ?"
            sql = sql_template.format(where_clause, direction)
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

    def get_linked_event_ids_batch(self, semantic_ids: List[str]) -> Dict[str, List[int]]:
        """Returns a mapping of semantic_id -> list of linked event IDs efficiently."""
        if not semantic_ids:
            return {}

        results = {sid: [] for sid in semantic_ids}

        # Optimization: Chunk the query to avoid hitting SQLite's parameter limits (SQLITE_MAX_VARIABLE_NUMBER)
        chunk_size = 900
        sql_template = "SELECT linked_id, id FROM events WHERE linked_id IN ({})"
        with self._get_conn() as conn:
            for i in range(0, len(semantic_ids), chunk_size):
                chunk = semantic_ids[i:i + chunk_size]
                placeholders = ','.join('?' for _ in chunk)
                cursor = conn.execute(
                    sql_template.format(placeholders),
                    chunk
                )

                for row in cursor.fetchall():
                    results[row[0]].append(row[1])

        return results

    def count_links_for_semantic(self, semantic_id: str) -> Tuple[int, float]:
        """Returns (count, total_strength) for a given semantic decision."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*), SUM(link_strength) FROM events WHERE linked_id = ?",
                (semantic_id,)
            ).fetchone()
            return (row[0] or 0, row[1] or 0.0)

    def count_links_for_semantic_batch(self, semantic_ids: List[str]) -> Dict[str, Tuple[int, float]]:
        """Returns a mapping of semantic_id -> (count, total_strength) for multiple semantic decisions efficiently."""
        if not semantic_ids:
            return {}

        placeholders = ','.join('?' for _ in semantic_ids)
        sql_template = "SELECT linked_id, COUNT(*), SUM(link_strength) FROM events WHERE linked_id IN ({}) GROUP BY linked_id"
        with self._get_conn() as conn:
            cursor = conn.execute(
                sql_template.format(placeholders),
                semantic_ids
            )
            results = {row[0]: (row[1] or 0, row[2] or 0.0) for row in cursor.fetchall()}

            # Ensure all requested IDs are in the result
            for sid in semantic_ids:
                if sid not in results:
                    results[sid] = (0, 0.0)
            return results

    def mark_archived(self, event_ids: List[int]):
        if not event_ids: return
        placeholders = ','.join(['?'] * len(event_ids))
        sql_template = "UPDATE events SET status = 'archived' WHERE id IN ({})"
        with self._get_conn() as conn:
            conn.execute(sql_template.format(placeholders), event_ids)

    def find_duplicate(self, event: MemoryEvent, linked_id: Optional[str] = None, ignore_links: bool = False) -> Result[int]:
        """Checks if an identical event (source, kind, content, context, timestamp) already exists."""
        def _do_find():
            context_json = self._serialize_context(event.context)
            timestamp_str = event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp)

            with self._get_conn() as conn:
                # Use the indexed columns first
                base_sql = "SELECT id FROM events WHERE source = ? AND kind = ? AND content = ? AND context = ? AND timestamp = ?"
                params = [event.source, event.kind, event.content, context_json, timestamp_str]
                
                if not ignore_links:
                    if linked_id is not None:
                        base_sql += " AND linked_id = ?"
                        params.append(linked_id)
                    else:
                        base_sql += " AND linked_id IS NULL"
                
                base_sql += " LIMIT 1"
                cursor = conn.execute(base_sql, params)
                row = cursor.fetchone()
                return row[0] if row else 0
        return safe_execute(_do_find)

    def physical_prune(self, event_ids: List[int]):
        if not event_ids: return
        # I2 Protection: Only prune if NOT linked
        placeholders = ','.join(['?'] * len(event_ids))
        sql_template = "DELETE FROM events WHERE id IN ({}) AND linked_id IS NULL"
        with self._get_conn() as conn:
            conn.execute(sql_template.format(placeholders), event_ids)

    def count_events(self, status: Optional[str] = 'active') -> int:
        """Returns the number of events with the given status."""
        with self._get_conn() as conn:
            if status:
                row = conn.execute("SELECT COUNT(*) FROM events WHERE status = ?", (status,)).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
            return row[0] or 0
