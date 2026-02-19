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
                    title TEXT DEFAULT '',
                    status TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    superseded_by TEXT,
                    content_hash TEXT,
                    content TEXT DEFAULT '',
                    hit_count INTEGER DEFAULT 0,
                    last_hit_at DATETIME,
                    confidence REAL DEFAULT 1.0,
                    namespace TEXT DEFAULT 'default'
                )
            """)
            
            # Migration: Add missing columns
            cols = {
                "title": "TEXT DEFAULT ''",
                "namespace": "TEXT DEFAULT 'default'",
                "hit_count": "INTEGER DEFAULT 0",
                "content": "TEXT DEFAULT ''",
                "last_hit_at": "DATETIME",
                "confidence": "REAL DEFAULT 1.0",
                "context_json": "TEXT DEFAULT '{}'"
            }
            for col, definition in cols.items():
                try:
                    conn.execute(f"ALTER TABLE semantic_meta ADD COLUMN {col} {definition}")
                except sqlite3.OperationalError: pass

            # I4 Violation Prevention: Only one 'active' decision per target per namespace
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

    def upsert(self, fid: str, target: str, status: str, kind: str, timestamp: datetime, 
               title: str = "", superseded_by: Optional[str] = None, namespace: str = "default",
               content: str = "", confidence: float = 1.0, context_json: str = "{}"):
        """Atomic upsert of decision metadata with content caching."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO semantic_meta (fid, target, title, status, kind, timestamp, superseded_by, namespace, content, confidence, context_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fid) DO UPDATE SET
                    title=excluded.title,
                    status=excluded.status,
                    superseded_by=excluded.superseded_by,
                    namespace=excluded.namespace,
                    content=excluded.content,
                    confidence=excluded.confidence,
                    context_json=excluded.context_json
            """, (fid, target, title, status, kind, timestamp.isoformat(), superseded_by, namespace, content, confidence, context_json))

    def get_by_fid(self, fid: str) -> Optional[Dict[str, Any]]:
        """Retrieves full metadata for a specific file ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM semantic_meta WHERE fid = ?", (fid,)).fetchone()
            return dict(row) if row else None

    def get_active_fid(self, target: str, namespace: str = "default") -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT fid FROM semantic_meta WHERE target = ? AND namespace = ? AND status = 'active' AND kind = 'decision'", 
                (target, namespace)
            ).fetchone()
            return row[0] if row else None

    def keyword_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fallback search using SQL LIKE when embeddings are unavailable."""
        words = query.lower().split()
        if not words: return []
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Build dynamic WHERE clause for multiple words
            conditions = []
            params = []
            for word in words:
                pattern = f"%{word}%"
                conditions.append("(target LIKE ? OR fid LIKE ? OR title LIKE ?)")
                params.extend([pattern, pattern, pattern])
            
            where_clause = " OR ".join(conditions)

            params.append(limit)
            
            query_sql = f"""
                SELECT * FROM semantic_meta 
                WHERE {where_clause}
                ORDER BY timestamp DESC LIMIT ?
            """  # nosec B608
            cursor = conn.execute(query_sql, params)
            return [dict(row) for row in cursor.fetchall()]


    def list_all(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM semantic_meta")
            return [dict(row) for row in cursor.fetchall()]

    def list_draft_proposals(self) -> List[Dict[str, Any]]:
        """Efficiently retrieves all draft proposals from the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM semantic_meta WHERE kind = 'proposal' AND status = 'draft'"
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_active_targets(self) -> set:
        """Efficiently retrieves all targets of active decisions."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT DISTINCT target FROM semantic_meta WHERE kind = 'decision' AND status = 'active'"
            )
            return {row[0] for row in cursor.fetchall()}

    def increment_hit(self, fid: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE semantic_meta 
                SET hit_count = hit_count + 1, 
                    last_hit_at = ? 
                WHERE fid = ?
            """, (datetime.now().isoformat(), fid))

    def delete(self, fid: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM semantic_meta WHERE fid = ?", (fid,))

    def clear(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM semantic_meta")

    def get_config(self, key: str, default: Any = None) -> Any:
        """Retrieves a configuration value from sys_config."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
            row = conn.execute("SELECT value FROM sys_config WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default

    def set_config(self, key: str, value: Any):
        """Stores a configuration value in sys_config."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)", (key, str(value)))

    def get_version(self) -> str:
        """Retrieves the current schema version."""
        return self.get_config('version', '1.0.0')

    def set_version(self, version: str):
        """Updates the schema version."""
        self.set_config('version', version)
