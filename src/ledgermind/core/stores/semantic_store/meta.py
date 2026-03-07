import re
import sqlite3
import logging
import time
import json
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from contextlib import contextmanager
from functools import lru_cache

logger = logging.getLogger(__name__)

@lru_cache(maxsize=128)
def _clean_query(query: str) -> str:
    """Pre-cleans query for FTS5 with caching. Preserves alpha-numerics across languages."""
    # Keep letters, numbers and spaces. Replace everything else with space.
    clean = re.sub(r'[^\w\s]', ' ', query)
    return " ".join(clean.split())

class SemanticMetaStore:
    """
    Transactional metadata index for the Semantic Store using SQLite.
    Provides DB-level guarantees for invariants.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=60.0, isolation_level=None)
        self._init_db()

    def _init_db(self):
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=60000")
        self._conn.execute("PRAGMA cache_size=-64000")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        
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
                    namespace TEXT DEFAULT 'default',
                    keywords TEXT DEFAULT '',
                    phase TEXT DEFAULT 'pattern',
                    vitality TEXT DEFAULT 'active',
                    reinforcement_density REAL DEFAULT 0.0,
                    stability_score REAL DEFAULT 0.0,
                    coverage REAL DEFAULT 0.0,
                    link_count INTEGER DEFAULT 0,
                    compressive_rationale TEXT,
                    enrichment_status TEXT DEFAULT 'pending',
                    context_json TEXT DEFAULT '{}'
                )
            """)

            # Migration: Add missing columns automatically
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
                "link_count": "INTEGER DEFAULT 0",
                "compressive_rationale": "TEXT",
                "content_hash": "TEXT",
                "enrichment_status": "TEXT DEFAULT 'pending'",
                "context_json": "TEXT DEFAULT '{}'"
            }
            for col, definition in cols.items():
                try:
                    self._conn.execute(f"ALTER TABLE semantic_meta ADD COLUMN {col} {definition}")
                except sqlite3.OperationalError: pass

            # Ensure FTS5 is available
            try:
                cursor = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='semantic_fts'")
                if not cursor.fetchone():
                    logger.info("Creating FTS5 index table...")
                    self._conn.execute("""
                        CREATE VIRTUAL TABLE semantic_fts USING fts5(
                            fid UNINDEXED,
                            title,
                            target,
                            content,
                            keywords,
                            tokenize='unicode61 remove_diacritics 1'
                        )
                    """)
            except sqlite3.OperationalError as e:
                logger.warning(f"FTS5 not available: {e}")

            # I4 Violation Prevention
            try:
                self._conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_active_target_ns
                    ON semantic_meta(target, namespace) WHERE status = 'active' AND kind = 'decision'
                """)
            except sqlite3.OperationalError: pass

            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON semantic_meta(status)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_target ON semantic_meta(target)")
            
            self.commit_transaction()
        except Exception as e:
            self.rollback_transaction()
            logger.error(f"Failed to initialize metadata store: {e}")
            raise

    def begin_transaction(self):
        self._conn.execute("BEGIN TRANSACTION")

    def commit_transaction(self):
        self._conn.execute("COMMIT")

    def rollback_transaction(self):
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.OperationalError: pass

    @contextmanager
    def batch_update(self):
        """Context manager for batching multiple upserts. Supports re-entrancy."""
        in_tx = self._conn.in_transaction
        if not in_tx: self.begin_transaction()
        try:
            yield
            if not in_tx: self.commit_transaction()
        except Exception:
            if not in_tx: self.rollback_transaction()
            raise

    def _execute_with_retry(self, sql: str, params: tuple = ()):
        max_retries = 5
        for i in range(max_retries):
            try:
                return self._conn.execute(sql, params)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and i < max_retries - 1:
                    time.sleep(0.5 * (i + 1))
                    continue
                raise

    def upsert(self, fid: str, target: str, status: str, kind: str, timestamp: datetime,
               title: str = "", superseded_by: Optional[str] = None, namespace: str = "default",
               content: str = "", keywords: str = "", confidence: float = 1.0, 
               content_hash: Optional[str] = None, last_hit_at: Optional[datetime] = None,
               compressive_rationale: Optional[str] = None,
               context_json: str = "{}", phase: str = "pattern", vitality: str = "active", 
               reinforcement_density: float = 0.0, stability_score: float = 0.0, 
               coverage: float = 0.0, link_count: int = 0, enrichment_status: str = "pending"):
        
        ts_str = timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp)
        lh_str = last_hit_at.isoformat() if last_hit_at and hasattr(last_hit_at, 'isoformat') else None

        self._execute_with_retry("""
            INSERT INTO semantic_meta (
                fid, target, title, status, kind, timestamp, superseded_by, namespace, 
                content, keywords, confidence, content_hash, last_hit_at, 
                compressive_rationale, context_json, phase, vitality, 
                reinforcement_density, stability_score, coverage, link_count, enrichment_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fid) DO UPDATE SET
                target=excluded.target, title=excluded.title, status=excluded.status,
                kind=excluded.kind, timestamp=excluded.timestamp, superseded_by=excluded.superseded_by,
                namespace=excluded.namespace, content=excluded.content, keywords=excluded.keywords,
                confidence=excluded.confidence, content_hash=excluded.content_hash,
                last_hit_at=excluded.last_hit_at, compressive_rationale=excluded.compressive_rationale,
                context_json=excluded.context_json, phase=excluded.phase, vitality=excluded.vitality,
                reinforcement_density=excluded.reinforcement_density, stability_score=excluded.stability_score,
                coverage=excluded.coverage, link_count=excluded.link_count, enrichment_status=excluded.enrichment_status
        """, (fid, target, title, status, kind, ts_str, superseded_by, namespace, 
              content, keywords, confidence, content_hash, lh_str, 
              compressive_rationale, context_json, phase, vitality, 
              reinforcement_density, stability_score, coverage, link_count, enrichment_status))

        try:
            self._execute_with_retry("DELETE FROM semantic_fts WHERE fid = ?", (fid,))
            self._execute_with_retry(
                "INSERT INTO semantic_fts (fid, title, target, content, keywords) VALUES (?, ?, ?, ?, ?)",
                (fid, title, target, content, keywords)
            )
        except sqlite3.OperationalError: pass

    def get_by_fid(self, fid: str, unpack_context: bool = False) -> Optional[Dict[str, Any]]:
        self._conn.row_factory = sqlite3.Row
        row = self._conn.execute("SELECT * FROM semantic_meta WHERE fid = ?", (fid,)).fetchone()
        if not row: return None
        res = dict(row)
        if unpack_context and res.get('context_json'):
            try:
                ctx = json.loads(res['context_json'])
                res.update(ctx)
            except: pass
        return res

    def get_batch_by_fids(self, fids: List[str]) -> List[Dict[str, Any]]:
        if not fids: return []
        self._conn.row_factory = sqlite3.Row
        placeholders = ', '.join(['?'] * len(fids))
        rows = self._conn.execute(f"SELECT * FROM semantic_meta WHERE fid IN ({placeholders})", fids).fetchall()
        return [dict(r) for r in rows]

    def list_all(self) -> List[Dict[str, Any]]:
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute("SELECT * FROM semantic_meta").fetchall()
        return [dict(r) for r in rows]

    def delete(self, fid: str):
        self._execute_with_retry("DELETE FROM semantic_meta WHERE fid = ?", (fid,))
        try: self._execute_with_retry("DELETE FROM semantic_fts WHERE fid = ?", (fid,))
        except sqlite3.OperationalError: pass

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_version(self) -> str:
        return self.get_config("schema_version", "0.0.0")

    def set_version(self, version: str):
        self.set_config("schema_version", version)

    def set_config(self, key: str, value: str):
        self._conn.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
        self._conn.execute("INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)", (key, value))

    def get_config(self, key: str, default: Any = None) -> Optional[str]:
        try:
            row = self._conn.execute("SELECT value FROM sys_config WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default
        except: return default

    def increment_hit(self, fid: str):
        now = datetime.now().isoformat()
        self._execute_with_retry("UPDATE semantic_meta SET hit_count = hit_count + 1, last_hit_at = ? WHERE fid = ?", (now, fid))

    def keyword_search(self, query: str, limit: int = 10, namespace: str = "default", status: Optional[str] = None) -> List[tuple]:
        original_factory = self._conn.row_factory
        self._conn.row_factory = None
        try:
            if not query.strip(): return []
            clean = _clean_query(query)
            if not clean: return []
            
            status_clause = "AND m.status = ?" if status else ""
            params = []
            
            try:
                # 1. Primary path: FTS5
                fts_query = clean + "*" if " " not in clean else clean
                params = [fts_query, namespace]
                if status: params.append(status)
                params.append(limit)

                sql = f"""
                    SELECT m.fid, m.title, m.target, m.status, m.kind, m.timestamp, m.namespace, m.phase, m.vitality, m.link_count,
                           (CASE m.phase WHEN 'canonical' THEN 1.5 WHEN 'emergent' THEN 1.2 ELSE 1.0 END * 
                            CASE m.vitality WHEN 'active' THEN 1.0 WHEN 'decaying' THEN 0.5 ELSE 0.2 END) as calculated_score
                    FROM semantic_meta m
                    JOIN semantic_fts f ON m.fid = f.fid
                    WHERE f.semantic_fts MATCH ? AND m.namespace = ? {status_clause}
                    ORDER BY f.rank LIMIT ?
                """
                return self._conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError as e:
                if "no such table: semantic_fts" in str(e) or "fts5" in str(e).lower():
                    # 2. Fallback path: standard SQL LIKE
                    logger.debug("FTS5 unavailable, falling back to LIKE search.")
                    # Use simpler matching for fallback
                    like_term = f"%{clean.lower()}%"
                    params = [like_term, like_term, like_term, namespace]
                    if status: params.append(status)
                    params.append(limit)
                    
                    sql = f"""
                        SELECT fid, title, target, status, kind, timestamp, namespace, phase, vitality, link_count,
                               (CASE phase WHEN 'canonical' THEN 1.5 WHEN 'emergent' THEN 1.2 ELSE 1.0 END * 
                                CASE vitality WHEN 'active' THEN 1.0 WHEN 'decaying' THEN 0.5 ELSE 0.2 END) as calculated_score,
                                hit_count, content_hash, enrichment_status, compressive_rationale, context_json
                        FROM semantic_meta
                        WHERE (LOWER(target) LIKE ? OR LOWER(title) LIKE ? OR LOWER(content) LIKE ?) AND namespace = ? {status_clause}
                        LIMIT ?
                    """
                    return self._conn.execute(sql, params).fetchall()
                raise
        finally: self._conn.row_factory = original_factory

    def resolve_to_truth(self, fid: str) -> Optional[Dict[str, Any]]:
        current_fid, visited, depth = fid, {fid}, 0
        last_valid_meta = None
        
        while depth < 20:
            meta = self.get_by_fid(current_fid)
            if not meta: 
                # Broken link: return the last valid record found
                return last_valid_meta
            
            last_valid_meta = meta
            if meta.get('status') != 'superseded' or not meta.get('superseded_by'): 
                return meta
                
            next_fid = meta['superseded_by']
            # Cycle detected
            if not next_fid or next_fid in visited: 
                return None
                
            visited.add(next_fid); current_fid = next_fid; depth += 1
            
        # Depth limit exceeded
        return None

    def get_active_fid(self, target: str, namespace: str = "default") -> Optional[str]:
        query = "SELECT fid FROM semantic_meta WHERE target = ? AND namespace = ? AND status = 'active' AND kind = 'decision' LIMIT 1"
        row = self._conn.execute(query, [target, namespace]).fetchone()
        return row[0] if row else None

    def get_active_fids_by_base_target(self, base_target: str, namespace: str = "default") -> List[str]:
        pattern = f"{base_target}/%"
        query = "SELECT fid FROM semantic_meta WHERE (target = ? OR target LIKE ?) AND namespace = ? AND status = 'active' AND kind = 'decision'"
        rows = self._conn.execute(query, [base_target, pattern, namespace]).fetchall()
        return [row[0] for row in rows]
