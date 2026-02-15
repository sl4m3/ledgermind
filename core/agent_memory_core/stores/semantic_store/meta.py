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
                    content_hash TEXT
                )
            """)
            # I4 Violation Prevention: Only one 'active' decision per target
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_active_target 
                ON semantic_meta(target) WHERE status = 'active' AND kind = 'decision'
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON semantic_meta(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_target ON semantic_meta(target)")
            conn.commit()

    def upsert(self, fid: str, target: str, status: str, kind: str, timestamp: datetime, superseded_by: Optional[str] = None):
        """Atomic upsert of decision metadata."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO semantic_meta (fid, target, status, kind, timestamp, superseded_by)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(fid) DO UPDATE SET
                    status=excluded.status,
                    superseded_by=excluded.superseded_by
            """, (fid, target, status, kind, timestamp.isoformat(), superseded_by))

    def get_active_fid(self, target: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT fid FROM semantic_meta WHERE target = ? AND status = 'active' AND kind = 'decision'", 
                (target,)
            ).fetchone()
            return row[0] if row else None

    def list_all(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM semantic_meta")
            return [dict(row) for row in cursor.fetchall()]

    def delete(self, fid: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM semantic_meta WHERE fid = ?", (fid,))

    def clear(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM semantic_meta")
