import sqlite3
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from ledgermind.core.stores.interfaces import MetadataStore

logger = logging.getLogger(__name__)

def _clean_query(query: str) -> str:
    """Sanitizes search query for FTS5."""
    return "".join(c for c in query if c.isalnum() or c.isspace()).strip()

class SemanticMetaStore(MetadataStore):
    """
    Persistent metadata storage for semantic decisions using SQLite.
    Architecture:
    - Autocommit mode (isolation_level=None) to allow external SAVEPOINTs.
    - Flat metadata structure for rapid filtering.
    - Intelligent FTS5 search with adaptive LIKE fallback.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        # isolation_level=None allows external transaction management (SAVEPOINTs)
        self._conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_meta (
                fid TEXT PRIMARY KEY,
                target TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                kind TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                namespace TEXT DEFAULT 'default',
                phase TEXT DEFAULT 'pattern',
                vitality TEXT DEFAULT 'active',
                link_count INTEGER DEFAULT 0,
                content TEXT,
                content_hash TEXT,
                context_json TEXT,
                enrichment_status TEXT DEFAULT 'pending',
                compressive_rationale TEXT,
                hit_count INTEGER DEFAULT 0,
                superseded_by TEXT,
                keywords TEXT,
                confidence REAL DEFAULT 1.0,
                last_hit_at TEXT,
                reinforcement_density REAL DEFAULT 0.0,
                stability_score REAL DEFAULT 0.0,
                coverage REAL DEFAULT 0.0,
                estimated_removal_cost REAL DEFAULT 0.0,
                estimated_utility REAL DEFAULT 0.0
            )
        """)
        
        self._conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_active_target_ns 
            ON semantic_meta(target, namespace) WHERE status = 'active' AND kind = 'decision'
        """)

        try:
            cursor = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='semantic_fts'")
            if not cursor.fetchone():
                self._conn.execute("CREATE VIRTUAL TABLE semantic_fts USING fts5(fid, title, content, tokenize='porter unicode61')")
                self._conn.execute("INSERT INTO semantic_fts(fid, title, content) SELECT fid, title, content FROM semantic_meta")
        except sqlite3.OperationalError as e:
            logger.error(f"FTS5 Error: {e}")

    def get_version(self) -> str:
        return self.get_config("schema_version", "1.0.0")

    def set_version(self, version: str):
        self.set_config("schema_version", version)

    def upsert(self, fid: str, target: str, title: str = "Untitled", status: str = "active", kind: str = "decision", 
               timestamp: Any = None, content: str = "", context_json: str = "{}", 
               namespace: str = "default", phase: str = "pattern", 
               vitality: str = "active", enrichment_status: str = "pending",
               **kwargs):
        """Atomic upsert of metadata and FTS sync."""
        now = datetime.now()
        ts_str = timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp or now.isoformat())
        
        fields = {
            'superseded_by': kwargs.get('superseded_by'),
            'keywords': kwargs.get('keywords', ""),
            'confidence': kwargs.get('confidence', 1.0),
            'last_hit_at': kwargs.get('last_hit_at'),
            'reinforcement_density': kwargs.get('reinforcement_density', 0.0),
            'stability_score': kwargs.get('stability_score', 0.0),
            'coverage': kwargs.get('coverage', 0.0),
            'estimated_removal_cost': kwargs.get('estimated_removal_cost', 0.0),
            'estimated_utility': kwargs.get('estimated_utility', 0.0),
            'content_hash': kwargs.get('content_hash'),
            'compressive_rationale': kwargs.get('compressive_rationale')
        }

        self._conn.execute("""
            INSERT INTO semantic_meta (
                fid, target, title, status, kind, timestamp, namespace, phase, vitality, 
                content, context_json, enrichment_status, content_hash, compressive_rationale,
                superseded_by, keywords, confidence, last_hit_at, reinforcement_density,
                stability_score, coverage, estimated_removal_cost, estimated_utility
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fid) DO UPDATE SET
                target=excluded.target, title=excluded.title, status=excluded.status,
                kind=excluded.kind, timestamp=excluded.timestamp, namespace=excluded.namespace,
                phase=excluded.phase, vitality=excluded.vitality, content=excluded.content,
                context_json=excluded.context_json, enrichment_status=excluded.enrichment_status,
                content_hash=excluded.content_hash, compressive_rationale=excluded.compressive_rationale,
                superseded_by=excluded.superseded_by, keywords=excluded.keywords,
                confidence=excluded.confidence, last_hit_at=excluded.last_hit_at,
                reinforcement_density=excluded.reinforcement_density,
                stability_score=excluded.stability_score, coverage=excluded.coverage,
                estimated_removal_cost=excluded.estimated_removal_cost, 
                estimated_utility=excluded.estimated_utility
        """, (fid, target, title, status, kind, ts_str, namespace, phase, vitality, 
              content, context_json, enrichment_status, fields['content_hash'], fields['compressive_rationale'],
              fields['superseded_by'], fields['keywords'], fields['confidence'], fields['last_hit_at'], 
              fields['reinforcement_density'], fields['stability_score'], fields['coverage'],
              fields['estimated_removal_cost'], fields['estimated_utility']))
        
        try:
            self._conn.execute("DELETE FROM semantic_fts WHERE fid = ?", (fid,))
            self._conn.execute("INSERT INTO semantic_fts(fid, title, content) VALUES (?, ?, ?)", (fid, title, content))
        except sqlite3.OperationalError: pass

    def batch_update(self, updates: Optional[List[Tuple[str, Dict[str, Any]]]] = None):
        if updates is None:
            class DBContext:
                def __init__(self, conn): self.conn = conn
                def __enter__(self): 
                    if not self.conn.in_transaction: self.conn.execute("BEGIN")
                    return self.conn
                def __exit__(self, et, ev, eb):
                    if not et and self.conn.in_transaction: self.conn.execute("COMMIT")
                    elif et and self.conn.in_transaction: self.conn.execute("ROLLBACK")
            return DBContext(self._conn)
            
        if not updates: return
        own_tx = not self._conn.in_transaction
        if own_tx: self._conn.execute("BEGIN")
        try:
            for fid, data in updates:
                fields = []
                values = []
                for k, v in data.items():
                    fields.append(k + " = ?")
                    values.append(v if not isinstance(v, (dict, list)) else json.dumps(v))
                if fields:
                    values.append(fid)
                    sql = "UPDATE semantic_meta SET " + ", ".join(fields) + " WHERE fid = ?" # nosec B608
                    self._conn.execute(sql, values)
            if own_tx: self._conn.execute("COMMIT")
        except Exception:
            if own_tx: self._conn.execute("ROLLBACK")
            raise

    def update_status(self, fid: str, status: str):
        self._conn.execute("UPDATE semantic_meta SET status = ? WHERE fid = ?", (status, fid))

    def delete(self, fid: str):
        self._conn.execute("DELETE FROM semantic_meta WHERE fid = ?", (fid,))
        try: self._conn.execute("DELETE FROM semantic_fts WHERE fid = ?", (fid,))
        except sqlite3.OperationalError: pass

    def clear(self):
        self._conn.execute("DELETE FROM semantic_meta")
        try: self._conn.execute("DELETE FROM semantic_fts")
        except sqlite3.OperationalError: pass

    def get_by_fid(self, fid: str, **kwargs) -> Optional[Dict[str, Any]]:
        row = self._conn.execute("SELECT * FROM semantic_meta WHERE fid = ?", (fid,)).fetchone()
        if not row: return None
        res = dict(row)
        if kwargs.get('unpack_context') and res.get('context_json'):
            try:
                ctx = json.loads(res['context_json'])
                res.update(ctx)
            except: pass
        return res

    def get_active_fid(self, target: str, namespace: str = "default") -> Optional[str]:
        sql = "SELECT fid FROM semantic_meta WHERE target = ? AND namespace = ? AND status = 'active' AND kind = 'decision'"
        row = self._conn.execute(sql, (target, namespace)).fetchone()
        return row[0] if row else None

    def get_active_fids_by_base_target(self, base_target: str, namespace: str = "default") -> List[str]:
        pattern = base_target + "%"
        sql = "SELECT fid FROM semantic_meta WHERE target LIKE ? AND namespace = ? AND status = 'active' AND kind = 'decision'"
        rows = self._conn.execute(sql, (pattern, namespace)).fetchall()
        return [row[0] for row in rows]

    def resolve_to_truth(self, doc_id: str, cache: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        visited = {doc_id}
        current_id = doc_id
        depth = 0
        last_valid = None
        while depth < 20:
            meta = cache[current_id] if cache and current_id in cache else self.get_by_fid(current_id)
            if not meta: return last_valid 
            last_valid = meta
            if meta.get('status') == 'active': return meta
            next_id = meta.get('superseded_by')
            if not next_id or next_id in visited:
                if next_id in visited: return None
                return meta
            visited.add(next_id)
            current_id = next_id
            depth += 1
        return None

    def get_batch_by_fids(self, fids: List[str]) -> List[Dict[str, Any]]:
        if not fids: return []
        self._conn.execute("CREATE TEMPORARY TABLE IF NOT EXISTS _filter_fids (fid TEXT)")
        self._conn.execute("DELETE FROM _filter_fids")
        self._conn.executemany("INSERT INTO _filter_fids VALUES (?)", [(f,) for f in fids])
        sql = "SELECT * FROM semantic_meta WHERE fid IN (SELECT fid FROM _filter_fids)"
        return [dict(r) for r in self._conn.execute(sql).fetchall()]

    def list_all(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM semantic_meta"
        params = []
        if namespace:
            sql += " WHERE namespace = ?"
            params.append(namespace)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def keyword_search(self, query: str, limit: int = 10, namespace: str = "default", status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search using FTS5 with an adaptive LIKE fallback."""
        if not query.strip(): return []
        clean_query = _clean_query(query)
        if not clean_query: return []
        words = clean_query.split()
        fts_query = clean_query + "*" if len(words) == 1 else clean_query
        try:
            sql_base = [
                "SELECT m.*, (CASE m.phase WHEN 'canonical' THEN 1.5 WHEN 'emergent' THEN 1.2 ELSE 1.0 END *",
                " CASE m.vitality WHEN 'active' THEN 1.0 WHEN 'decaying' THEN 0.5 ELSE 0.2 END) as calculated_score",
                "FROM semantic_meta m JOIN semantic_fts f ON m.fid = f.fid",
                "WHERE semantic_fts MATCH ? AND m.namespace = ?"
            ]
            params = [fts_query, namespace]
            if status:
                sql_base.append("AND m.status = ?")
                params.append(status)
            sql_base.append("ORDER BY f.rank LIMIT ?")
            params.append(limit)
            rows = self._conn.execute(" ".join(sql_base), params).fetchall()
            if rows: return [dict(r) for r in rows]
        except sqlite3.OperationalError: pass

        for logic in ["AND", "OR"]:
            where_clauses = ["m.namespace = ?"]
            params = [namespace]
            for word in words:
                where_clauses.append("(LOWER(m.title) LIKE ? OR LOWER(m.content) LIKE ? OR LOWER(m.keywords) LIKE ? OR LOWER(m.target) LIKE ?)")
                w_pat = f"%{word.lower()}%"
                params.extend([w_pat, w_pat, w_pat, w_pat])
            if status:
                where_clauses.append("m.status = ?")
                params.append(status)
            sql = "SELECT *, 1.0 as calculated_score FROM semantic_meta m WHERE " + f" {logic} ".join(where_clauses) + " LIMIT ?" # nosec B608
            params.append(limit)
            rows = self._conn.execute(sql, params).fetchall()
            if rows: return [dict(r) for r in rows]
        return []

    def get_config(self, key: str, default: Any = None) -> Any:
        try:
            row = self._conn.execute("SELECT value FROM sys_config WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default
        except sqlite3.OperationalError:
            self._conn.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
            return default

    def set_config(self, key: str, value: Any):
        self._conn.execute("CREATE TABLE IF NOT EXISTS sys_config (key TEXT PRIMARY KEY, value TEXT)")
        self._conn.execute("INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)", (key, str(value)))

    def increment_hit(self, fid: str):
        self._conn.execute("UPDATE semantic_meta SET hit_count = hit_count + 1 WHERE fid = ?", (fid,))

    def close(self):
        self._conn.close()
