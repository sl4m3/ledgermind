import sqlite3
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import re

logger = logging.getLogger(__name__)

class SemanticMetaStore:
    """
    Transactional metadata index for the Semantic Store using SQLite.
    Provides DB-level guarantees for invariants.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0, isolation_level=None)
        self._init_db()

    def _init_db(self):
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute("PRAGMA cache_size=-64000") # 64MB cache
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA mmap_size=30000000000")
        # Ensure FTS5 is available or fallback
        try:
            self._conn.execute("SELECT 1")
        except sqlite3.OperationalError: pass

        with self._conn:
            self._conn.execute("BEGIN")
            self._conn.execute("""
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
                    self._conn.execute(f"ALTER TABLE semantic_meta ADD COLUMN {col} {definition}")
                except sqlite3.OperationalError: pass

            # I4 Violation Prevention: Only one 'active' decision per target per namespace
            try:
                self._conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_active_target_ns 
                    ON semantic_meta(target, namespace) WHERE status = 'active' AND kind = 'decision'
                """)
            except sqlite3.OperationalError:
                pass

            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON semantic_meta(status)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_target ON semantic_meta(target)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_namespace ON semantic_meta(namespace)")

            # FTS5 Full Text Search
            try:
                # Check if FTS table exists
                cursor = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='semantic_fts'")
                exists = cursor.fetchone()
                
                if not exists:
                    logger.info("Creating FTS5 index table...")
                    # Create FTS5 table linked to semantic_meta
                    self._conn.execute("""
                        CREATE VIRTUAL TABLE semantic_fts USING fts5(
                            fid, title, target, content, 
                            content='semantic_meta', 
                            content_rowid='rowid'
                        )
                    """)
                    
                    # Triggers are required for External Content Tables to keep index in sync
                    self._conn.execute("""
                        CREATE TRIGGER semantic_ai AFTER INSERT ON semantic_meta BEGIN
                            INSERT INTO semantic_fts(rowid, fid, title, target, content) VALUES (new.rowid, new.fid, new.title, new.target, new.content);
                        END;
                    """)
                    self._conn.execute("""
                        CREATE TRIGGER semantic_ad AFTER DELETE ON semantic_meta BEGIN
                            INSERT INTO semantic_fts(semantic_fts, rowid, fid, title, target, content) VALUES('delete', old.rowid, old.fid, old.title, old.target, old.content);
                        END;
                    """)
                    self._conn.execute("""
                        CREATE TRIGGER semantic_au AFTER UPDATE ON semantic_meta BEGIN
                            INSERT INTO semantic_fts(semantic_fts, rowid, fid, title, target, content) VALUES('delete', old.rowid, old.fid, old.title, old.target, old.content);
                            INSERT INTO semantic_fts(rowid, fid, title, target, content) VALUES (new.rowid, new.fid, new.title, new.target, new.content);
                        END;
                    """)
                    
                    # Initial rebuild
                    self._conn.execute("INSERT INTO semantic_fts(semantic_fts) VALUES('rebuild')")
                else:
                    # Ensure triggers exist (migration for old versions)
                    self._conn.execute("CREATE TRIGGER IF NOT EXISTS semantic_ai AFTER INSERT ON semantic_meta BEGIN INSERT INTO semantic_fts(rowid, fid, title, target, content) VALUES (new.rowid, new.fid, new.title, new.target, new.content); END;")
                    self._conn.execute("CREATE TRIGGER IF NOT EXISTS semantic_ad AFTER DELETE ON semantic_meta BEGIN INSERT INTO semantic_fts(semantic_fts, rowid, fid, title, target, content) VALUES('delete', old.rowid, old.fid, old.title, old.target, old.content); END;")
                    self._conn.execute("CREATE TRIGGER IF NOT EXISTS semantic_au AFTER UPDATE ON semantic_meta BEGIN INSERT INTO semantic_fts(semantic_fts, rowid, fid, title, target, content) VALUES('delete', old.rowid, old.fid, old.title, old.target, old.content); INSERT INTO semantic_fts(rowid, fid, title, target, content) VALUES (new.rowid, new.fid, new.title, new.target, new.content); END;")

            except sqlite3.OperationalError as e:
                logger.warning(f"FTS5 setup failed: {e}. Keyword search will be limited.")
            
            self._conn.execute("COMMIT")

    def upsert(self, fid: str, target: str, status: str, kind: str, timestamp: datetime, 
               title: str = "", superseded_by: Optional[str] = None, namespace: str = "default",
               content: str = "", confidence: float = 1.0, context_json: str = "{}"):
        """Atomic upsert of decision metadata with content caching."""
        self._conn.execute("""
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
        self._conn.row_factory = sqlite3.Row
        cursor = self._conn.cursor()
        row = cursor.execute("SELECT * FROM semantic_meta WHERE fid = ?", (fid,)).fetchone()
        return dict(row) if row else None

    def get_active_fid(self, target: str, namespace: str = "default") -> Optional[str]:
        cursor = self._conn.cursor()
        row = cursor.execute(
            "SELECT fid FROM semantic_meta WHERE target = ? AND namespace = ? AND status = 'active' AND kind = 'decision'", 
            (target, namespace)
        ).fetchone()
        return row[0] if row else None

    def keyword_search(self, query: str, limit: int = 10, namespace: str = "default") -> List[Dict[str, Any]]:
        """Search using FTS5 (BM25) or fallback to LIKE with namespace filtering."""
        self._conn.row_factory = sqlite3.Row
        cursor = self._conn.cursor()
        
        try:
            # FTS Search
            # Simple sanitization for FTS5 syntax
            safe_query = query.replace('"', '""')
            if not safe_query.strip(): return []
            
            # Clean query of FTS5 special characters to avoid syntax errors or weird matching
            # Keep alphanumerics and spaces.
            clean_query = re.sub(r'[^a-zA-Z0-9\s]', ' ', query)
            # Remove double spaces
            clean_query = " ".join(clean_query.split())

            # Use simple token search if query is simple, else use exact phrase
            words = clean_query.split()
            if len(words) > 5:
                 inner_query = " ".join(words[1:-1])
                 fts_query = inner_query if inner_query else clean_query
            elif " " not in clean_query:
                 fts_query = clean_query + "*"
            else:
                 fts_query = clean_query
            
            sql = """
                SELECT m.*, fts.rank 
                FROM semantic_meta m
                JOIN semantic_fts fts ON m.rowid = fts.rowid
                WHERE semantic_fts MATCH ? AND m.namespace = ?
                ORDER BY rank LIMIT ?
            """
            cursor.execute(sql, (fts_query, namespace, limit))
            res = [dict(row) for row in cursor.fetchall()]
            
            # Fallback to OR search if AND fails
            if not res and len(words) > 3:
                 fts_query_or = clean_query.replace(" ", " OR ")
                 cursor.execute(sql, (fts_query_or, namespace, limit * 2))
                 res = [dict(row) for row in cursor.fetchall()]
            
            return res
            
        except Exception as e:
            # Fallback to LIKE implementation
            words = query.lower().split()
            if not words: return []
            
            conditions = []
            params = []
            for word in words:
                pattern = f"%{word}%"
                conditions.append("(target LIKE ? OR fid LIKE ? OR title LIKE ?)")
                params.extend([pattern, pattern, pattern])
            
            where_clause = "(" + " OR ".join(conditions) + ")"
            sql_params = params + [namespace, limit]
            
            query_sql = f"""
                SELECT * FROM semantic_meta 
                WHERE {where_clause} AND namespace = ?
                ORDER BY timestamp DESC LIMIT ?
            """  # nosec B608
            cursor.execute(query_sql, sql_params)
            return [dict(row) for row in cursor.fetchall()]


    def list_all(self) -> List[Dict[str, Any]]:
        self._conn.row_factory = sqlite3.Row
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM semantic_meta ORDER BY timestamp DESC")
        return [dict(row) for row in cursor.fetchall()]

    def list_draft_proposals(self) -> List[Dict[str, Any]]:
        """Efficiently retrieves all draft proposals from the database."""
        self._conn.row_factory = sqlite3.Row
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT * FROM semantic_meta WHERE kind = 'proposal' AND status = 'draft'"
        )
        return [dict(row) for row in cursor.fetchall()]

    def list_active_targets(self) -> set:
        """Efficiently retrieves all targets of active decisions."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT DISTINCT target FROM semantic_meta WHERE kind = 'decision' AND status = 'active'"
        )
        return {row[0] for row in cursor.fetchall()}

    def increment_hit(self, fid: str):
        try:
            self._conn.execute("""
                UPDATE semantic_meta 
                SET hit_count = hit_count + 1, 
                    last_hit_at = ? 
                WHERE fid = ?
            """, (datetime.now().isoformat(), fid))
        except sqlite3.OperationalError as e:
            if "locked" in str(e):
                logger.debug(f"Telemetry update skipped (DB locked): {fid}")
            else:
                raise

    def delete(self, fid: str):
        self._conn.execute("DELETE FROM semantic_meta WHERE fid = ?", (fid,))

    def clear(self):
        self._conn.execute("DELETE FROM semantic_meta")

    def get_config(self, key: str, default: Any = None) -> Any:
        """Retrieves a configuration value from sys_config."""
        with self._conn:
            self._conn.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
        cursor = self._conn.cursor()
        row = cursor.execute("SELECT value FROM sys_config WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_config(self, key: str, value: Any):
        """Stores a configuration value in sys_config."""
        with self._conn:
            self._conn.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
            self._conn.execute("INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)", (key, str(value)))

    def get_version(self) -> str:
        """Retrieves the current schema version."""
        return self.get_config('version', '1.0.0')

    def set_version(self, version: str):
        """Updates the schema version."""
        self.set_config('version', version)

    def close(self):
        """Closes the persistent database connection."""
        self._conn.close()
