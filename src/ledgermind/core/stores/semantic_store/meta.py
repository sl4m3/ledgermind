import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

logger = logging.getLogger("ledgermind.core.semantic_store.meta")

class SemanticMetaStore:
    """
    Metadata index for semantic knowledge stored in SQLite.
    Optimized for ACID-compliant mass updates and hierarchical querying.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_meta (
                fid TEXT PRIMARY KEY,
                target TEXT NOT NULL,
                title TEXT,
                status TEXT NOT NULL,
                kind TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                content TEXT,
                context_json TEXT,
                namespace TEXT DEFAULT 'default',
                phase TEXT,
                vitality TEXT,
                enrichment_status TEXT,
                supersedes TEXT,
                superseded_by TEXT,
                converted_to TEXT,
                merge_status TEXT DEFAULT 'idle',
                keywords TEXT,
                confidence REAL,
                last_hit_at DATETIME,
                hit_count INTEGER DEFAULT 0,
                link_count INTEGER DEFAULT 0,
                reinforcement_density REAL DEFAULT 0.0,
                stability_score REAL DEFAULT 0.0,
                coverage REAL DEFAULT 0.0,
                estimated_removal_cost REAL DEFAULT 0.0,
                estimated_utility REAL DEFAULT 0.0,
                content_hash TEXT,
                compressive_rationale TEXT
            )
        """)
        self._conn.execute("CREATE TABLE IF NOT EXISTS semantic_config (key TEXT PRIMARY KEY, value TEXT)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_target ON semantic_meta(target)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON semantic_meta(status)")
        
        # Initialize FTS5 for full-text search
        try:
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts USING fts5(
                    fid UNINDEXED,
                    title,
                    content,
                    keywords,
                    content='semantic_meta',
                    tokenize='unicode61'
                )
            """)
            
            # Sync triggers for FTS using rowid for integrity
            self._conn.execute("DROP TRIGGER IF EXISTS trg_semantic_meta_insert")
            self._conn.execute("""
                CREATE TRIGGER trg_semantic_meta_insert AFTER INSERT ON semantic_meta BEGIN
                    INSERT INTO semantic_fts(rowid, title, content, keywords) VALUES (new.rowid, new.title, new.content, new.keywords);
                END
            """)
            
            self._conn.execute("DROP TRIGGER IF EXISTS trg_semantic_meta_delete")
            self._conn.execute("""
                CREATE TRIGGER trg_semantic_meta_delete AFTER DELETE ON semantic_meta BEGIN
                    INSERT INTO semantic_fts(semantic_fts, rowid, title, content, keywords) VALUES('delete', old.rowid, old.title, old.content, old.keywords);
                END
            """)
            
            self._conn.execute("DROP TRIGGER IF EXISTS trg_semantic_meta_update")
            self._conn.execute("""
                CREATE TRIGGER trg_semantic_meta_update AFTER UPDATE ON semantic_meta BEGIN
                    INSERT INTO semantic_fts(semantic_fts, rowid, title, content, keywords) VALUES('delete', old.rowid, old.title, old.content, old.keywords);
                    INSERT INTO semantic_fts(rowid, title, content, keywords) VALUES (new.rowid, new.title, new.content, new.keywords);
                END
            """)
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS5 initialization failed (likely missing module): {e}")

        self._conn.commit()

    def get_version(self) -> str:
        return self.get_config("version", "0.0.0")

    def set_version(self, version: str):
        self.set_config("version", version)

    def get_config(self, key: str, default: Any = None) -> Any:
        cursor = self._conn.execute("SELECT value FROM semantic_config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

    def _execute_with_retry(self, sql: str, params: tuple = (), commit: bool = False, is_write: bool = False):
        """Executes a query with retry logic for locked databases."""
        max_retries = 5
        retry_delay = 0.1
        
        for attempt in range(max_retries):
            try:
                if is_write and not self._conn.in_transaction:
                    self._conn.execute("BEGIN IMMEDIATE")
                
                cursor = self._conn.execute(sql, params)
                
                if is_write and not self._conn.in_transaction:
                    self._conn.execute("COMMIT")
                elif commit:
                    self._conn.commit()
                    
                return cursor
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < max_retries - 1:
                    if is_write and not self._conn.in_transaction:
                        try: self._conn.execute("ROLLBACK")
                        except: pass
                    time.sleep(retry_delay * (2 ** attempt))
                    continue
                raise
            except Exception as e:
                if is_write and not self._conn.in_transaction:
                    try: self._conn.execute("ROLLBACK")
                    except: pass
                raise

    def set_config(self, key: str, value: str):
        self._execute_with_retry("INSERT OR REPLACE INTO semantic_config (key, value) VALUES (?, ?)", (key, str(value)), commit=True, is_write=True)

    def upsert(self, fid: str, target: str, title: str, status: str, kind: str, 
               timestamp: datetime, content: str, context_json: str, namespace: str = "default", 
               **kwargs):
        """Inserts or updates metadata record. No internal commit to support external transactions."""
        ts_str = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp)
        
        fields = {
            'phase': kwargs.get('phase', 'pattern'),
            'vitality': kwargs.get('vitality', 'active'),
            'enrichment_status': kwargs.get('enrichment_status', 'pending'),
            'supersedes': json.dumps(kwargs.get('supersedes', [])) if isinstance(kwargs.get('supersedes'), list) else kwargs.get('supersedes'),
            'superseded_by': kwargs.get('superseded_by'),
            'converted_to': kwargs.get('converted_to'),
            'merge_status': kwargs.get('merge_status', 'idle'),
            'keywords': kwargs.get('keywords', ""),
            'confidence': kwargs.get('confidence', 1.0),
            'last_hit_at': kwargs.get('last_hit_at'),
            'link_count': kwargs.get('link_count', 0),
            'reinforcement_density': kwargs.get('reinforcement_density', 0.0),
            'stability_score': kwargs.get('stability_score', 0.0),
            'coverage': kwargs.get('coverage', 0.0),
            'estimated_removal_cost': kwargs.get('estimated_removal_cost', 0.0),
            'estimated_utility': kwargs.get('estimated_utility', 0.0),
            'content_hash': kwargs.get('content_hash'),
            'compressive_rationale': kwargs.get('compressive_rationale')
        }

        sql = """
            INSERT INTO semantic_meta (
                fid, target, title, status, kind, timestamp, content, context_json, namespace, phase, vitality, enrichment_status,
                supersedes, superseded_by, converted_to, merge_status, keywords, confidence, last_hit_at, link_count, reinforcement_density, stability_score, coverage, 
                estimated_removal_cost, estimated_utility, content_hash, compressive_rationale
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            ) ON CONFLICT(fid) DO UPDATE SET
                target=excluded.target,
                title=excluded.title,
                status=excluded.status,
                kind=excluded.kind,
                timestamp=excluded.timestamp,
                content=excluded.content,
                context_json=excluded.context_json,
                namespace=excluded.namespace,
                phase=excluded.phase,
                vitality=excluded.vitality,
                enrichment_status=excluded.enrichment_status,
                supersedes=excluded.supersedes,
                superseded_by=excluded.superseded_by,
                converted_to=excluded.converted_to,
                merge_status=excluded.merge_status,
                keywords=excluded.keywords,
                confidence=excluded.confidence,
                last_hit_at=excluded.last_hit_at,
                link_count=excluded.link_count,
                reinforcement_density=excluded.reinforcement_density,
                stability_score=excluded.stability_score,
                coverage=excluded.coverage,
                estimated_removal_cost=excluded.estimated_removal_cost,
                estimated_utility=excluded.estimated_utility,
                content_hash=excluded.content_hash,
                compressive_rationale=excluded.compressive_rationale
        """
        params = (
            fid, target, title, status, kind, ts_str, content, context_json, namespace,
            fields['phase'], fields['vitality'], fields['enrichment_status'], 
            fields['supersedes'], fields['superseded_by'], fields['converted_to'], fields['merge_status'], 
            fields['keywords'], fields['confidence'], fields['last_hit_at'], 
            fields['link_count'], fields['reinforcement_density'], fields['stability_score'], 
            fields['coverage'], fields['estimated_removal_cost'], fields['estimated_utility'], 
            fields['content_hash'], fields['compressive_rationale']
        )
        
        if self._conn.in_transaction:
            self._conn.execute(sql, params)
        else:
            self._execute_with_retry(sql, params, is_write=True)


    def delete(self, fid: str):
        self._execute_with_retry("DELETE FROM semantic_meta WHERE fid = ?", (fid,), is_write=True)

    def get_by_fid(self, fid: str) -> Optional[Dict[str, Any]]:
        cursor = self._execute_with_retry("SELECT * FROM semantic_meta WHERE fid = ?", (fid,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_batch_by_fids(self, fids: List[str]) -> List[Dict[str, Any]]:
        """Fetch multiple metadata records in a single query."""
        if not fids: return []
        placeholders = ', '.join(['?'] * len(fids))
        cursor = self._execute_with_retry(f"SELECT * FROM semantic_meta WHERE fid IN ({placeholders})", tuple(fids)) # nosec B608
        return [dict(row) for row in cursor.fetchall()]

    def resolve_to_truth(self, fid: str, depth: int = 0) -> Optional[Dict[str, Any]]:
        """Recursively follows 'superseded_by' links to find the active truth."""
        if depth >= 20: return None
        
        meta = self.get_by_fid(fid)
        if not meta: return None
        
        next_fid = meta.get('superseded_by')
        if meta.get('status') == 'active' or not next_fid:
            return meta
            
        truth = self.resolve_to_truth(next_fid, depth + 1)
        if truth is None:
            if depth > 0 and depth >= 19: return None # Depth limit hit down the chain
            return meta # Next link broken, return last known good
        return truth

    def keyword_search(self, query: str, limit: int = 10, namespace: str = "default", status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Performs full-text search using FTS5 with fallback to LIKE."""
        sanitized = query.replace('"', '""').strip()
        if not sanitized: return []
        
        # 1. Try FTS5 if available
        results = []
        try:
            # Use query as is for standard FTS5 behavior (AND/OR logic)
            fts_query = sanitized
            sql = """
                SELECT m.* FROM semantic_meta m
                JOIN semantic_fts f ON m.rowid = f.rowid
                WHERE semantic_fts MATCH ?
                AND m.namespace = ?
            """
            params = [fts_query, namespace]
            if status:
                sql += " AND m.status = ?"
                params.append(status)
            sql += " LIMIT ?"
            params.append(limit)
            
            cursor = self._conn.execute(sql, params)
            results = [dict(row) for row in cursor.fetchall()]
            
            if not results:
                # Try prefix search for each word
                words = [w for w in sanitized.split() if len(w) > 1]
                if words:
                    fts_query = " ".join([f"{w}*" for w in words])
                    params[0] = fts_query
                    cursor = self._conn.execute(sql, params)
                    results = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            pass
            
        # 2. If no FTS results, or FTS failed, use robust LIKE
        if not results:
            sql_fallback = """
                SELECT * FROM semantic_meta 
                WHERE (title LIKE ? OR content LIKE ? OR target LIKE ? OR keywords LIKE ?) 
                AND namespace = ?
            """
            term = f"%{sanitized}%"
            params_fallback = [term, term, term, term, namespace]
            if status:
                sql_fallback += " AND status = ?"
                params_fallback.append(status)
            sql_fallback += " LIMIT ?"
            params_fallback.append(limit)
            
            cursor = self._conn.execute(sql_fallback, params_fallback)
            results = [dict(row) for row in cursor.fetchall()]
            
        return results

    def list_all(self, target: Optional[str] = None, namespace: str = "default") -> List[Dict[str, Any]]:
        if target:
            cursor = self._conn.execute(
                "SELECT * FROM semantic_meta WHERE target = ? AND namespace = ? ORDER BY timestamp DESC", 
                (target, namespace)
            )
        else:
            cursor = self._conn.execute("SELECT * FROM semantic_meta ORDER BY timestamp DESC")
        return [dict(row) for row in cursor.fetchall()]

    def increment_hit(self, fid: str):
        now = datetime.now().isoformat()
        self._conn.execute(
            "UPDATE semantic_meta SET hit_count = hit_count + 1, last_hit_at = ? WHERE fid = ?", 
            (now, fid)
        )

    def close(self):
        if self._conn:
            try:
                self._conn.commit()
            except sqlite3.OperationalError:
                pass
            self._conn.close()

    @contextmanager
    def batch_update(self):
        """Manual batching support."""
        try:
            yield
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
