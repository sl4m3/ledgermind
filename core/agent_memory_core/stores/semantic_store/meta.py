import sqlite3
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class SemanticMetaStore:
    """
    Transactional metadata index for the Semantic Store using SQLite.
    Provides DB-level guarantees for invariants.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_meta (
                    fid TEXT PRIMARY KEY,
                    target TEXT NOT NULL,
                    status TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    superseded_by TEXT,
                    content_hash TEXT,
                    hit_count INTEGER DEFAULT 0
                )
            """)
            
            # Migration: Add namespace and hit_count columns if they don't exist
            try:
                conn.execute("ALTER TABLE semantic_meta ADD COLUMN namespace TEXT DEFAULT 'default'")
            except sqlite3.OperationalError: pass
            try:
                conn.execute("ALTER TABLE semantic_meta ADD COLUMN hit_count INTEGER DEFAULT 0")
            except sqlite3.OperationalError: pass

            # I4 Violation Prevention: Only one 'active' decision per target per namespace
            # We don't drop the index if it fails, just try to create the new one
            try:
                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_active_target_ns 
                    ON semantic_meta(target, namespace) WHERE status = 'active' AND kind = 'decision'
                """)
            except sqlite3.OperationalError:
                pass

            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON semantic_meta(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_target ON semantic_meta(target)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_namespace ON semantic_meta(namespace)")
            conn.commit()

    def upsert(self, fid: str, target: str, status: str, kind: str, timestamp: datetime, superseded_by: Optional[str] = None, namespace: str = "default"):
        """Atomic upsert of decision metadata."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO semantic_meta (fid, target, status, kind, timestamp, superseded_by, namespace)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fid) DO UPDATE SET
                    status=excluded.status,
                    superseded_by=excluded.superseded_by,
                    namespace=excluded.namespace
            """, (fid, target, status, kind, timestamp.isoformat(), superseded_by, namespace))

    def get_active_fid(self, target: str, namespace: str = "default") -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT fid FROM semantic_meta WHERE target = ? AND namespace = ? AND status = 'active' AND kind = 'decision'", 
                (target, namespace)
            ).fetchone()
            return row[0] if row else None

    def keyword_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fallback search using SQL LIKE when embeddings are unavailable."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            pattern = f"%{query}%"
            cursor = conn.execute("""
                SELECT * FROM semantic_meta 
                WHERE (target LIKE ? OR fid LIKE ?)
                ORDER BY timestamp DESC LIMIT ?
            """, (pattern, pattern, limit))
            return [dict(row) for row in cursor.fetchall()]

    def list_all(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM semantic_meta")
            return [dict(row) for row in cursor.fetchall()]

    def increment_hit(self, fid: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE semantic_meta SET hit_count = hit_count + 1 WHERE fid = ?", (fid,))

    def delete(self, fid: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM semantic_meta WHERE fid = ?", (fid,))

    def clear(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM semantic_meta")
