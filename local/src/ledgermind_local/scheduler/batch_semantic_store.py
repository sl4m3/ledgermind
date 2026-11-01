"""Durable SQLite state for background semantic batches.

The benchmark may keep ``batch_task_cache.json``; production must survive a
Local restart while a provider batch is still running.  This store keeps the
leased task payload, the provider batch id, the result and the delivery state
in one local SQLite database.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

__all__ = [
    "BatchChunkRecord",
    "BatchJobRecord",
    "BatchSemanticStore",
    "BatchTaskRecord",
]

_ACTIVE_TASK_STATUSES = ("pending", "submitted", "result_ready", "completed")
_TERMINAL_JOB_STATUSES = ("completed", "failed", "expired")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()  # noqa: UP017 - Python 3.10


def _connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


@contextmanager
def _connection(path: str) -> Iterator[sqlite3.Connection]:
    connection = _connect(path)
    try:
        yield connection
    finally:
        connection.close()


@dataclass(frozen=True, slots=True)
class BatchTaskRecord:
    task_id: str
    memory_space_id: str
    custom_id: str
    batch_id: str | None
    status: str
    payload: dict[str, Any]
    result: dict[str, Any] | None
    usage: dict[str, Any] | None
    contract_digest: str | None
    attempts: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class BatchChunkRecord:
    chunk_id: str
    root_task_id: str
    chunk_index: int
    chunk_total: int
    custom_id: str
    batch_id: str | None
    status: str
    payload: dict[str, Any]
    result: dict[str, Any] | None
    usage: dict[str, Any] | None
    attempts: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class BatchJobRecord:
    batch_id: str
    status: str
    submitted_at: str
    next_poll_at: str
    expires_at: str
    poll_errors: int


class BatchSemanticStore:
    """SQLite-backed queue, batch registry and result source."""

    def __init__(self, path: str | Path, *, lock: threading.Lock | None = None) -> None:
        self._path = str(path)
        self._lock = lock if lock is not None else threading.Lock()
        self._initialize()
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    @property
    def path(self) -> str:
        return self._path

    def _initialize(self) -> None:
        with self._lock, _connection(self._path) as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS batch_tasks (
                    task_id TEXT PRIMARY KEY,
                    memory_space_id TEXT NOT NULL,
                    custom_id TEXT NOT NULL UNIQUE,
                    batch_id TEXT,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending','submitted','result_ready','completed','failed')
                    ),
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    usage_json TEXT,
                    contract_digest TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS batch_tasks_status_idx
                ON batch_tasks (status, created_at)
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS batch_jobs (
                    batch_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    next_poll_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    poll_errors INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS batch_task_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    root_task_id TEXT NOT NULL
                        REFERENCES batch_tasks(task_id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    chunk_total INTEGER NOT NULL,
                    custom_id TEXT NOT NULL UNIQUE,
                    batch_id TEXT,
                    status TEXT NOT NULL CHECK (
                        status IN (
                            'pending','submitted','result_ready','completed','failed'
                        )
                    ),
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    usage_json TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (root_task_id, chunk_index)
                )
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS batch_task_chunks_root_idx
                ON batch_task_chunks (root_task_id, chunk_index)
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS batch_task_chunks_status_idx
                ON batch_task_chunks (status, created_at)
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS batch_task_chunks_batch_idx
                ON batch_task_chunks (batch_id)
                """
            )
            db.commit()

    # ------------------------------------------------------------------ queue

    def enqueue(
        self,
        *,
        task_id: str,
        memory_space_id: str,
        custom_id: str,
        payload: Mapping[str, Any],
        contract_digest: str | None = None,
    ) -> bool:
        """Insert a task once; failed tasks may be retried explicitly."""
        now = _now()
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status FROM batch_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is not None and row["status"] in _ACTIVE_TASK_STATUSES:
                return False
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            cursor = db.execute(
                """
                INSERT INTO batch_tasks (
                    task_id, memory_space_id, custom_id, batch_id, status,
                    payload_json, result_json, usage_json, contract_digest,
                    attempts, last_error_code, created_at, updated_at
                ) VALUES (?, ?, ?, NULL, 'pending', ?, NULL, NULL, ?, 0, NULL, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    memory_space_id=excluded.memory_space_id,
                    custom_id=excluded.custom_id,
                    batch_id=NULL,
                    status='pending',
                    payload_json=excluded.payload_json,
                    result_json=NULL,
                    usage_json=NULL,
                    contract_digest=excluded.contract_digest,
                    last_error_code=NULL,
                    updated_at=excluded.updated_at
                WHERE batch_tasks.status = 'failed'
                """,
                (
                    task_id,
                    memory_space_id,
                    custom_id,
                    encoded,
                    contract_digest,
                    now,
                    now,
                ),
            )
            if row is not None and row["status"] == "failed":
                db.execute(
                    "DELETE FROM batch_task_chunks WHERE root_task_id = ?",
                    (task_id,),
                )
            db.commit()
            return cursor.rowcount > 0

    def pending(self, limit: int = 1_000) -> list[BatchTaskRecord]:
        with self._lock, _connection(self._path) as db:
            rows = db.execute(
                """
                SELECT task.* FROM batch_tasks AS task
                WHERE task.status = 'pending'
                  AND NOT EXISTS (
                      SELECT 1 FROM batch_task_chunks AS chunk
                      WHERE chunk.root_task_id = task.task_id
                  )
                ORDER BY task.created_at, task.task_id
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [_task_record(row) for row in rows]

    def get(self, task_id: str) -> BatchTaskRecord | None:
        with self._lock, _connection(self._path) as db:
            row = db.execute(
                "SELECT * FROM batch_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return _task_record(row) if row is not None else None

    def mark_submitted(self, task_ids: Sequence[str], batch_id: str) -> None:
        if not task_ids:
            return
        now = _now()
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.executemany(
                """
                UPDATE batch_tasks
                SET batch_id = ?, status = 'submitted', updated_at = ?
                WHERE task_id = ? AND status = 'pending'
                """,
                [(batch_id, now, task_id) for task_id in task_ids],
            )
            db.commit()

    def record_submission(
        self,
        task_ids: Sequence[str],
        batch_id: str,
        *,
        expires_at: str,
    ) -> None:
        """Atomically mark tasks submitted and register their provider batch."""
        self.record_batch_submission(
            task_ids,
            (),
            batch_id,
            expires_at=expires_at,
        )

    def record_batch_submission(
        self,
        task_ids: Sequence[str],
        chunk_ids: Sequence[str],
        batch_id: str,
        *,
        expires_at: str,
        next_poll_at: str | None = None,
    ) -> None:
        """Register one provider batch for roots and/or their chunks."""
        if not task_ids and not chunk_ids:
            return
        now = _now()
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            if task_ids:
                db.executemany(
                    """
                    UPDATE batch_tasks
                    SET batch_id = ?, status = 'submitted', updated_at = ?
                    WHERE task_id = ? AND status = 'pending'
                    """,
                    [(batch_id, now, task_id) for task_id in task_ids],
                )
            if chunk_ids:
                db.executemany(
                    """
                    UPDATE batch_task_chunks
                    SET batch_id = ?, status = 'submitted', updated_at = ?
                    WHERE chunk_id = ? AND status = 'pending'
                    """,
                    [(batch_id, now, chunk_id) for chunk_id in chunk_ids],
                )
            db.execute(
                """
                INSERT INTO batch_jobs (
                    batch_id, status, submitted_at, next_poll_at, expires_at, poll_errors
                ) VALUES (?, 'submitted', ?, ?, ?, 0)
                ON CONFLICT(batch_id) DO NOTHING
                """,
                (
                    batch_id,
                    now,
                    next_poll_at if next_poll_at is not None else now,
                    expires_at,
                ),
            )
            db.commit()

    def mark_result(
        self,
        task_id: str,
        *,
        output: Any,
        usage: Mapping[str, Any] | None = None,
    ) -> None:
        now = _now()
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                UPDATE batch_tasks
                SET status = 'result_ready', result_json = ?, usage_json = ?,
                    last_error_code = NULL, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    json.dumps(output, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(
                        dict(usage or {}), ensure_ascii=False, separators=(",", ":")
                    ),
                    now,
                    task_id,
                ),
            )
            db.commit()

    def mark_delivered(self, task_id: str) -> None:
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                UPDATE batch_tasks
                SET status = 'completed', updated_at = ?
                WHERE task_id = ? AND status = 'result_ready'
                """,
                (_now(), task_id),
            )
            db.commit()

    def mark_failed(self, task_id: str, error_code: str) -> None:
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                UPDATE batch_tasks
                SET status = 'failed', last_error_code = ?, updated_at = ?
                WHERE task_id = ? AND status != 'completed'
                """,
                (error_code[:200], _now(), task_id),
            )
            db.commit()

    def requeue_batch(self, batch_id: str, error_code: str) -> list[str]:
        """Return a failed/expired batch's tasks to the pending queue."""
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT task_id FROM batch_tasks WHERE batch_id = ? AND status = 'submitted'",
                (batch_id,),
            ).fetchall()
            task_ids = [str(row["task_id"]) for row in rows]
            db.executemany(
                """
                UPDATE batch_tasks
                SET batch_id = NULL, status = 'pending', attempts = attempts + 1,
                    last_error_code = ?, updated_at = ?
                WHERE task_id = ?
                """,
                [(error_code[:200], _now(), task_id) for task_id in task_ids],
            )
            db.commit()
        return task_ids

    def tasks_for_batch(self, batch_id: str) -> list[BatchTaskRecord]:
        with self._lock, _connection(self._path) as db:
            rows = db.execute(
                """
                SELECT * FROM batch_tasks
                WHERE batch_id = ?
                ORDER BY created_at, task_id
                """,
                (batch_id,),
            ).fetchall()
        return [_task_record(row) for row in rows]

    def requeue_task(self, task_id: str, error_code: str) -> None:
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                UPDATE batch_tasks
                SET batch_id = NULL, status = 'pending', attempts = attempts + 1,
                    last_error_code = ?, updated_at = ?
                WHERE task_id = ? AND status = 'submitted'
                """,
                (error_code[:200], _now(), task_id),
            )
            db.commit()

    def result_ready(self, limit: int = 1_000) -> list[BatchTaskRecord]:
        with self._lock, _connection(self._path) as db:
            rows = db.execute(
                """
                SELECT * FROM batch_tasks
                WHERE status = 'result_ready'
                ORDER BY updated_at, task_id
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [_task_record(row) for row in rows]

    # ------------------------------------------------------------------ chunks

    def plan_chunks(
        self,
        root_task_id: str,
        chunks: Sequence[Mapping[str, Any]],
    ) -> bool:
        """Persist one deterministic split for a pending root task."""
        if not chunks:
            return False
        normalized: list[tuple[str, str, str]] = []
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id")
            custom_id = chunk.get("custom_id")
            payload = chunk.get("payload")
            if not isinstance(chunk_id, str) or not chunk_id:
                raise ValueError("chunk_id must be a non-empty string")
            if not isinstance(custom_id, str) or not custom_id:
                raise ValueError("custom_id must be a non-empty string")
            if not isinstance(payload, Mapping):
                raise TypeError("chunk payload must be a mapping")
            normalized.append(
                (
                    chunk_id,
                    custom_id,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                )
            )
        now = _now()
        total = len(normalized)
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            root = db.execute(
                "SELECT status FROM batch_tasks WHERE task_id = ?", (root_task_id,)
            ).fetchone()
            if root is None or root["status"] != "pending":
                return False
            existing = db.execute(
                "SELECT COUNT(*) FROM batch_task_chunks WHERE root_task_id = ?",
                (root_task_id,),
            ).fetchone()[0]
            if existing:
                return False
            db.executemany(
                """
                INSERT INTO batch_task_chunks (
                    chunk_id, root_task_id, chunk_index, chunk_total, custom_id,
                    batch_id, status, payload_json, result_json, usage_json,
                    attempts, last_error_code, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, 'pending', ?, NULL, NULL, 0, NULL, ?, ?)
                """,
                [
                    (chunk_id, root_task_id, index, total, custom_id, payload, now, now)
                    for index, (chunk_id, custom_id, payload) in enumerate(normalized)
                ],
            )
            db.commit()
            return True

    def pending_chunks(self, limit: int = 2_000) -> list[BatchChunkRecord]:
        with self._lock, _connection(self._path) as db:
            rows = db.execute(
                """
                SELECT chunk.* FROM batch_task_chunks AS chunk
                JOIN batch_tasks AS root ON root.task_id = chunk.root_task_id
                WHERE chunk.status = 'pending' AND root.status = 'pending'
                ORDER BY chunk.created_at, chunk.root_task_id, chunk.chunk_index
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [_chunk_record(row) for row in rows]

    def get_chunk(self, chunk_id: str) -> BatchChunkRecord | None:
        with self._lock, _connection(self._path) as db:
            row = db.execute(
                "SELECT * FROM batch_task_chunks WHERE chunk_id = ?", (chunk_id,)
            ).fetchone()
        return _chunk_record(row) if row is not None else None

    def chunks_for_root(self, root_task_id: str) -> list[BatchChunkRecord]:
        with self._lock, _connection(self._path) as db:
            rows = db.execute(
                """
                SELECT * FROM batch_task_chunks
                WHERE root_task_id = ?
                ORDER BY chunk_index
                """,
                (root_task_id,),
            ).fetchall()
        return [_chunk_record(row) for row in rows]

    def chunks_for_batch(self, batch_id: str) -> list[BatchChunkRecord]:
        with self._lock, _connection(self._path) as db:
            rows = db.execute(
                """
                SELECT * FROM batch_task_chunks
                WHERE batch_id = ?
                ORDER BY root_task_id, chunk_index
                """,
                (batch_id,),
            ).fetchall()
        return [_chunk_record(row) for row in rows]

    def chunked_root_ids(self) -> list[str]:
        with self._lock, _connection(self._path) as db:
            rows = db.execute(
                """
                SELECT DISTINCT root_task_id FROM batch_task_chunks
                ORDER BY root_task_id
                """
            ).fetchall()
        return [str(row["root_task_id"]) for row in rows]

    def mark_chunk_result(
        self,
        chunk_id: str,
        *,
        output: Any,
        usage: Mapping[str, Any] | None = None,
    ) -> None:
        now = _now()
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                UPDATE batch_task_chunks
                SET status = 'result_ready', result_json = ?, usage_json = ?,
                    last_error_code = NULL, updated_at = ?
                WHERE chunk_id = ? AND status IN ('pending', 'submitted')
                """,
                (
                    json.dumps(output, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(
                        dict(usage or {}), ensure_ascii=False, separators=(",", ":")
                    ),
                    now,
                    chunk_id,
                ),
            )
            db.commit()

    def requeue_chunk(self, chunk_id: str, error_code: str) -> None:
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                UPDATE batch_task_chunks
                SET batch_id = NULL, status = 'pending', attempts = attempts + 1,
                    last_error_code = ?, updated_at = ?
                WHERE chunk_id = ? AND status = 'submitted'
                """,
                (error_code[:200], _now(), chunk_id),
            )
            db.commit()

    def mark_chunk_failed(self, chunk_id: str, error_code: str) -> None:
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                UPDATE batch_task_chunks
                SET status = 'failed', last_error_code = ?, updated_at = ?
                WHERE chunk_id = ? AND status != 'completed'
                """,
                (error_code[:200], _now(), chunk_id),
            )
            db.commit()

    def requeue_chunks_batch(self, batch_id: str, error_code: str) -> list[str]:
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                """
                SELECT chunk_id FROM batch_task_chunks
                WHERE batch_id = ? AND status = 'submitted'
                """,
                (batch_id,),
            ).fetchall()
            chunk_ids = [str(row["chunk_id"]) for row in rows]
            db.executemany(
                """
                UPDATE batch_task_chunks
                SET batch_id = NULL, status = 'pending', attempts = attempts + 1,
                    last_error_code = ?, updated_at = ?
                WHERE chunk_id = ?
                """,
                [(error_code[:200], _now(), chunk_id) for chunk_id in chunk_ids],
            )
            db.commit()
        return chunk_ids

    def reset_chunked_root(self, root_task_id: str, error_code: str) -> int:
        """Drop failed chunk state and return the root to the pending queue."""
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "DELETE FROM batch_task_chunks WHERE root_task_id = ?",
                (root_task_id,),
            )
            db.execute(
                """
                UPDATE batch_tasks
                SET attempts = attempts + 1, last_error_code = ?, updated_at = ?
                WHERE task_id = ? AND status = 'pending'
                """,
                (error_code[:200], _now(), root_task_id),
            )
            row = db.execute(
                "SELECT attempts FROM batch_tasks WHERE task_id = ?",
                (root_task_id,),
            ).fetchone()
            db.commit()
        return int(row["attempts"]) if row is not None else 0

    def complete_chunked_root(
        self,
        root_task_id: str,
        *,
        output: Any,
        usage: Mapping[str, Any] | None = None,
    ) -> None:
        """Publish the merged result and delete the chunk rows atomically."""
        now = _now()
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                UPDATE batch_tasks
                SET status = 'result_ready', result_json = ?, usage_json = ?,
                    last_error_code = NULL, updated_at = ?
                WHERE task_id = ? AND status = 'pending'
                """,
                (
                    json.dumps(output, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(
                        dict(usage or {}), ensure_ascii=False, separators=(",", ":")
                    ),
                    now,
                    root_task_id,
                ),
            )
            db.execute(
                "DELETE FROM batch_task_chunks WHERE root_task_id = ?",
                (root_task_id,),
            )
            db.commit()

    # ------------------------------------------------------------------- jobs

    def create_job(self, *, batch_id: str, expires_at: str) -> None:
        now = _now()
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                INSERT INTO batch_jobs (
                    batch_id, status, submitted_at, next_poll_at, expires_at, poll_errors
                ) VALUES (?, 'submitted', ?, ?, ?, 0)
                ON CONFLICT(batch_id) DO NOTHING
                """,
                (batch_id, now, now, expires_at),
            )
            db.commit()

    def jobs(self) -> list[BatchJobRecord]:
        placeholders = ",".join("?" for _ in _TERMINAL_JOB_STATUSES)
        with self._lock, _connection(self._path) as db:
            rows = db.execute(
                f"""
                SELECT * FROM batch_jobs
                WHERE status NOT IN ({placeholders})
                ORDER BY submitted_at, batch_id
                """,
                _TERMINAL_JOB_STATUSES,
            ).fetchall()
        return [_job_record(row) for row in rows]

    def wake_batch(self, batch_id: str, *, delay_seconds: float = 2.0) -> bool:
        """Make a webhook-notified batch due immediately (shortly after now)."""
        target = (
            datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10
            + timedelta(seconds=max(0.0, delay_seconds))
        ).isoformat()
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                "UPDATE batch_jobs SET next_poll_at = ? WHERE batch_id = ?",
                (target, batch_id),
            )
            db.commit()
            return cursor.rowcount > 0

    def update_job(
        self,
        batch_id: str,
        *,
        status: str,
        next_poll_at: str,
        poll_errors: int,
    ) -> None:
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """
                UPDATE batch_jobs
                SET status = ?, next_poll_at = ?, poll_errors = ?
                WHERE batch_id = ?
                """,
                (status, next_poll_at, max(0, int(poll_errors)), batch_id),
            )
            db.commit()

    def delete_job(self, batch_id: str) -> None:
        with self._lock, _connection(self._path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM batch_jobs WHERE batch_id = ?", (batch_id,))
            db.commit()

    # ------------------------------------------------------- result source API

    def lookup(self, *, task_id: str, keys: Sequence[str]) -> Mapping[str, Any] | None:
        """Return a completed executor-cache entry for a task id or legacy key."""
        candidates = [task_id, *keys]
        placeholders = ",".join("?" for _ in candidates)
        with self._lock, _connection(self._path) as db:
            rows = db.execute(
                f"""
                SELECT * FROM batch_tasks
                WHERE task_id IN ({placeholders}) OR custom_id IN ({placeholders})
                """,
                (*candidates, *candidates),
            ).fetchall()
        if not rows:
            return None
        # Prefer a delivered/ready row over a failed duplicate.
        ordered = sorted(
            rows,
            key=lambda row: 0 if row["status"] in ("result_ready", "completed") else 1,
        )
        row = ordered[0]
        if (
            row["status"] in ("result_ready", "completed")
            and row["result_json"] is not None
        ):
            return {
                "status": "completed",
                "output": json.loads(row["result_json"]),
                "usage": json.loads(row["usage_json"] or "{}"),
                "batch_id": row["batch_id"],
                "contract_digest": row["contract_digest"],
            }
        return {
            "status": "failed",
            "error_code": row["last_error_code"] or "batch_result_unavailable",
        }


def _task_record(row: sqlite3.Row) -> BatchTaskRecord:
    return BatchTaskRecord(
        task_id=str(row["task_id"]),
        memory_space_id=str(row["memory_space_id"]),
        custom_id=str(row["custom_id"]),
        batch_id=str(row["batch_id"]) if row["batch_id"] is not None else None,
        status=str(row["status"]),
        payload=json.loads(row["payload_json"]),
        result=json.loads(row["result_json"])
        if row["result_json"] is not None
        else None,
        usage=json.loads(row["usage_json"]) if row["usage_json"] is not None else None,
        contract_digest=(
            str(row["contract_digest"]) if row["contract_digest"] is not None else None
        ),
        attempts=int(row["attempts"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _chunk_record(row: sqlite3.Row) -> BatchChunkRecord:
    return BatchChunkRecord(
        chunk_id=str(row["chunk_id"]),
        root_task_id=str(row["root_task_id"]),
        chunk_index=int(row["chunk_index"]),
        chunk_total=int(row["chunk_total"]),
        custom_id=str(row["custom_id"]),
        batch_id=str(row["batch_id"]) if row["batch_id"] is not None else None,
        status=str(row["status"]),
        payload=json.loads(row["payload_json"]),
        result=json.loads(row["result_json"])
        if row["result_json"] is not None
        else None,
        usage=json.loads(row["usage_json"]) if row["usage_json"] is not None else None,
        attempts=int(row["attempts"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _job_record(row: sqlite3.Row) -> BatchJobRecord:
    return BatchJobRecord(
        batch_id=str(row["batch_id"]),
        status=str(row["status"]),
        submitted_at=str(row["submitted_at"]),
        next_poll_at=str(row["next_poll_at"]),
        expires_at=str(row["expires_at"]),
        poll_errors=int(row["poll_errors"]),
    )
