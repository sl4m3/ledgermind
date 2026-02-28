import re
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from contextlib import contextmanager
from functools import lru_cache

logger = logging.getLogger(__name__)

@lru_cache(maxsize=128)
def _clean_query(query: str) -> str:
    """Pre-cleans query for FTS5 with caching."""
    # Clean query of FTS5 special characters to avoid syntax errors or weird matching
    # Keep alphanumerics (including Unicode) and spaces.
    clean = re.sub(r'[^\w\s]', ' ', query)
    return " ".join(clean.split())

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
        self._conn.execute("PRAGMA synchronous=OFF") # Restored from v3.0.3 for performance
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute("PRAGMA cache_size=-64000") # 64MB cache
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA mmap_size=30000000000")
        # Ensure FTS5 is available or fallback
        try:
            self._conn.execute("SELECT 1")
        except sqlite3.OperationalError: pass

        self.begin_transaction()
        try:
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
                "keywords": "TEXT DEFAULT ''",
                "last_hit_at": "DATETIME",
                "confidence": "REAL DEFAULT 1.0",
                "phase": "TEXT DEFAULT 'pattern'",
                "vitality": "TEXT DEFAULT 'active'",
                "reinforcement_density": "REAL DEFAULT 0.0",
                "stability_score": "REAL DEFAULT 0.0",
                "coverage": "REAL DEFAULT 0.0",
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
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_phase ON semantic_meta(phase)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_vitality ON semantic_meta(vitality)")

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
                            fid, title, target, content, keywords,
                            content='semantic_meta', 
                            content_rowid='rowid'
                        )
                    """)
                    
                    # Triggers are required for External Content Tables to keep index in sync
                    self._conn.execute("""
                        CREATE TRIGGER semantic_ai AFTER INSERT ON semantic_meta BEGIN
                            INSERT INTO semantic_fts(rowid, fid, title, target, content, keywords) VALUES (new.rowid, new.fid, new.title, new.target, new.content, new.keywords);
                        END;
                    """)
                    self._conn.execute("""
                        CREATE TRIGGER semantic_ad AFTER DELETE ON semantic_meta BEGIN
                            INSERT INTO semantic_fts(semantic_fts, rowid, fid, title, target, content, keywords) VALUES('delete', old.rowid, old.fid, old.title, old.target, old.content, old.keywords);
                        END;
                    """)
                    self._conn.execute("""
                        CREATE TRIGGER semantic_au AFTER UPDATE ON semantic_meta BEGIN
                            INSERT INTO semantic_fts(semantic_fts, rowid, fid, title, target, content, keywords) VALUES('delete', old.rowid, old.fid, old.title, old.target, old.content, old.keywords);
                            INSERT INTO semantic_fts(rowid, fid, title, target, content, keywords) VALUES (new.rowid, new.fid, new.title, new.target, new.content, new.keywords);
                        END;
                    """)
                    
                    # Initial rebuild
                    self._conn.execute("INSERT INTO semantic_fts(semantic_fts) VALUES('rebuild')")
                else:
                    # Ensure triggers exist (migration for old versions)
                    self._conn.execute("CREATE TRIGGER IF NOT EXISTS semantic_ai AFTER INSERT ON semantic_meta BEGIN INSERT INTO semantic_fts(rowid, fid, title, target, content, keywords) VALUES (new.rowid, new.fid, new.title, new.target, new.content, new.keywords); END;")
                    self._conn.execute("CREATE TRIGGER IF NOT EXISTS semantic_ad AFTER DELETE ON semantic_meta BEGIN INSERT INTO semantic_fts(semantic_fts, rowid, fid, title, target, content, keywords) VALUES('delete', old.rowid, old.fid, old.title, old.target, old.content, old.keywords); END;")
                    self._conn.execute("CREATE TRIGGER IF NOT EXISTS semantic_au AFTER UPDATE ON semantic_meta BEGIN INSERT INTO semantic_fts(semantic_fts, rowid, fid, title, target, content, keywords) VALUES('delete', old.rowid, old.fid, old.title, old.target, old.content, old.keywords); INSERT INTO semantic_fts(rowid, fid, title, target, content, keywords) VALUES (new.rowid, new.fid, new.title, new.target, new.content, new.keywords); END;")

            except sqlite3.OperationalError as e:
                logger.warning(f"FTS5 setup failed: {e}. Keyword search will be limited.")
            
            self.commit_transaction()
        except Exception:
            self.rollback_transaction()
            raise

    def upsert(self, fid: str, target: str, status: str, kind: str, timestamp: datetime, 
               title: str = "", superseded_by: Optional[str] = None, namespace: str = "default",
               content: str = "", keywords: str = "", confidence: float = 1.0, context_json: str = "{}",
               phase: str = "pattern", vitality: str = "active", reinforcement_density: float = 0.0, 
               stability_score: float = 0.0, coverage: float = 0.0):
        """Atomic upsert of decision metadata with content caching."""
        # Ensure timestamp is in ISO format string
        ts_str = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)

        self._conn.execute("""
            INSERT INTO semantic_meta (fid, target, title, status, kind, timestamp, superseded_by, namespace, content, keywords, confidence, context_json, phase, vitality, reinforcement_density, stability_score, coverage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fid) DO UPDATE SET
                title=excluded.title,
                status=excluded.status,
                superseded_by=excluded.superseded_by,
                namespace=excluded.namespace,
                content=excluded.content,
                keywords=excluded.keywords,
                confidence=excluded.confidence,
                context_json=excluded.context_json,
                phase=excluded.phase,
                vitality=excluded.vitality,
                reinforcement_density=excluded.reinforcement_density,
                stability_score=excluded.stability_score,
                coverage=excluded.coverage
        """, (fid, target, title, status, kind, ts_str, superseded_by, namespace, content, keywords, confidence, context_json, phase, vitality, reinforcement_density, stability_score, coverage))


    def get_by_fid(self, fid: str) -> Optional[Dict[str, Any]]:
        """Retrieves full metadata for a specific file ID."""
        self._conn.row_factory = sqlite3.Row
        cursor = self._conn.cursor()
        row = cursor.execute("SELECT * FROM semantic_meta WHERE fid = ?", (fid,)).fetchone()
        return dict(row) if row else None

    def get_batch_by_fids(self, fids: List[str]) -> List[Dict[str, Any]]:
        """Retrieves metadata for multiple file IDs efficiently."""
        if not fids: return []
        self._conn.row_factory = sqlite3.Row
        placeholders = ','.join('?' for _ in fids)
        cursor = self._conn.cursor()
        cursor.execute(f"SELECT * FROM semantic_meta WHERE fid IN ({placeholders})", fids) # nosec B608
        return [dict(row) for row in cursor.fetchall()]

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
            if not query.strip(): return []
            
            clean_query = _clean_query(query)
            if not clean_query: return []

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
            
            # Optimization: Use AND for intersection to match FTS behavior and improve performance.
            # Each word must be present in at least one of the fields.
            conditions = []
            params = []
            for word in words:
                pattern = f"%{word}%"
                conditions.append("(target LIKE ? OR fid LIKE ? OR title LIKE ? OR keywords LIKE ?)")
                params.extend([pattern, pattern, pattern, pattern])
            
            where_clause = "(" + " AND ".join(conditions) + ")"
            sql_params = params + [namespace, limit]
            
            query_sql = f"""
                SELECT * FROM semantic_meta 
                WHERE {where_clause} AND namespace = ?
                ORDER BY timestamp DESC LIMIT ?
            """  # nosec B608
            cursor.execute(query_sql, sql_params)
            return [dict(row) for row in cursor.fetchall()]

    def resolve_to_truth(self, fid: str) -> Optional[Dict[str, Any]]:
        """
        Recursively resolves the chain of superseded decisions to find the final active decision
        or the last existing link in the chain, using a single recursive CTE.
        """
        self._conn.row_factory = sqlite3.Row
        cursor = self._conn.cursor()

        # Recursive CTE to follow superseded_by links
        # Logic:
        # 1. Start with 'fid'.
        # 2. Recursively join if current is NOT active AND has a successor.
        # 3. Stop if depth limit (20) reached or chain ends.

        sql = """
            WITH RECURSIVE chain(fid, status, superseded_by, depth) AS (
                SELECT fid, status, superseded_by, 0
                FROM semantic_meta
                WHERE fid = ?

                UNION ALL

                SELECT m.fid, m.status, m.superseded_by, c.depth + 1
                FROM semantic_meta m
                JOIN chain c ON m.fid = c.superseded_by
                WHERE c.depth < 20
                  AND c.status != 'active'
                  AND c.superseded_by IS NOT NULL
            )
            SELECT m.*, c.depth
            FROM semantic_meta m
            JOIN chain c ON m.fid = c.fid
            ORDER BY c.depth DESC
            LIMIT 1;
        """

        try:
            cursor.execute(sql, (fid,))
            row = cursor.fetchone()

            if not row:
                return None

            res = dict(row)
            depth = res.pop('depth', 0)

            status = res.get("status")
            successor = res.get("superseded_by")

            # Replicate the logic of the iterative loop regarding depth limit
            if depth >= 20:
                logger.warning(f"Recursive truth resolution depth limit (20) reached for {fid}. Possible circularity or long evolution chain.")
                return None

            # Replicate broken link behavior:
            # If we stopped, but the record is not active and claims to have a successor,
            # it means the successor was not found (broken link).
            if status != "active" and successor:
                logger.warning(f"Broken chain at {fid}: successor {successor} not found. Returning last valid link.")
                return res

            return res

        except sqlite3.OperationalError as e:
            logger.error(f"Resolution failed: {e}")
            # Fallback to get_by_fid if CTE fails (e.g. very old SQLite version)
            return self.get_by_fid(fid)


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

    def begin_transaction(self):
        """Manually starts a transaction."""
        if not self._conn.in_transaction:
            self._conn.execute("BEGIN IMMEDIATE")

    def commit_transaction(self):
        """Manually commits a transaction."""
        if self._conn.in_transaction:
            self._conn.execute("COMMIT")

    def rollback_transaction(self):
        """Manually rolls back a transaction."""
        if self._conn.in_transaction:
            self._conn.execute("ROLLBACK")

    @contextmanager
    def batch_update(self):
        """Context manager for batched operations."""
        was_in_transaction = self._conn.in_transaction
        if not was_in_transaction:
            self.begin_transaction()
        try:
            yield
            if not was_in_transaction and self._conn.in_transaction:
                self.commit_transaction()
        except:
            if not was_in_transaction and self._conn.in_transaction:
                self.rollback_transaction()
            raise
