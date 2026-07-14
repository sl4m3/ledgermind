"""FastAPI server for LedgerMind — HTTP bridge for agent plugins."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ledgermind.core.api.memory import Memory
from ledgermind.server.background import BackgroundWorker

# Configure logging to file
LOG_DIR = Path.home() / ".ledgermind"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "server.log"

# Clear existing handlers and add fresh ones
logging.root.handlers.clear()
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
logging.root.addHandler(file_handler)
logging.root.setLevel(logging.INFO)

logger = logging.getLogger("ledgermind.api")

app = FastAPI(title="LedgerMind", version="3.3.6")

STORAGE_DIR = Path.home() / ".ledgermind" / "hermes"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

_memory: Optional[Memory] = None
_worker: Optional[BackgroundWorker] = None


class SearchRequest(BaseModel):
    query: str
    limit: int = 5
    profile: str = "default"


class WriteRequest(BaseModel):
    source: str
    kind: str
    content: str
    context: Optional[Dict[str, Any]] = None
    profile: str = "default"


class ImportRequest(BaseModel):
    profile: str = "default"
    limit: Optional[int] = None  # None = use config, 0 = skip, -1 = all, N = last N


class HealthResponse(BaseModel):
    status: str
    worker_running: bool


def _get_memory() -> Memory:
    global _memory
    if _memory is None:
        model_path = str(LOG_DIR / "hermes" / "models" / "v5-small-text-matching-Q4_K_M.gguf")
        _memory = Memory(
            storage_path=str(STORAGE_DIR),
            namespace="default",
            vector_model=model_path,
        )
    return _memory


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        worker_running=_worker is not None and _worker.running,
    )


@app.post("/memory/search")
def search(req: SearchRequest):
    memory = _get_memory()
    results = memory.search_decisions(
        req.query,
        limit=req.limit,
        namespace=req.profile,
        mode="lite",
    )
    return {"results": results}


@app.post("/memory/write")
def write(req: WriteRequest):
    memory = _get_memory()
    memory.process_event(
        source=req.source,
        kind=req.kind,
        content=req.content,
        context=req.context or {},
        namespace=req.profile,
    )
    return {"status": "ok"}


@app.post("/worker/start")
def worker_start():
    global _worker
    if _worker is not None and _worker.running:
        return {"status": "already running"}
    memory = _get_memory()
    _worker = BackgroundWorker(memory=memory, client="api")
    _worker.start()
    return {"status": "started"}


@app.post("/worker/stop")
def worker_stop():
    global _worker
    if _worker is None or not _worker.running:
        return {"status": "not running"}
    _worker.stop()
    _worker = None
    return {"status": "stopped"}


@app.post("/reflection/run")
def run_reflection():
    memory = _get_memory()
    # Reset watermark
    config_path = STORAGE_DIR / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    config["last_reflection_event_id"] = 0
    config_path.write_text(json.dumps(config, indent=2))
    result = memory.run_maintenance()
    return result


@app.post("/import/state-db")
def import_state_db(req: ImportRequest):
    state_db = Path.home() / ".hermes" / "state.db"
    if not state_db.exists():
        return {"status": "no state.db found"}

    try:
        import sqlite3

        # Resolve import limit: request param > config.json > 0 (skip)
        config_path = STORAGE_DIR / "config.json"
        config = json.loads(config_path.read_text()) if config_path.exists() else {}
        limit = req.limit if req.limit is not None else config.get("import_limit", 0)

        if limit == 0:
            return {"status": "ok", "imported": 0, "message": "Import skipped (limit=0)"}

        conn = sqlite3.connect(str(state_db))
        conn.row_factory = sqlite3.Row

        # Fetch all messages across sessions, then apply limit
        all_messages = conn.execute("""
            SELECT m.*, s.id as sid FROM messages m
            JOIN sessions s ON m.session_id = s.id
            ORDER BY m.timestamp DESC
        """).fetchall()
        conn.close()

        if limit > 0:
            all_messages = all_messages[:limit]

        all_messages.reverse()  # Restore chronological order

        memory = _get_memory()
        imported = 0
        for m in all_messages:
            if not m["content"]:
                continue
            if m["role"] == "user":
                source, kind = "user", "prompt"
                ctx = {"session_id": m["sid"]}
            else:
                source, kind = "agent", "result"
                ctx = {"session_id": m["sid"], "success": True}
            memory.process_event(
                source=source,
                kind=kind,
                content=m["content"][:2000],
                context=ctx,
                namespace=req.profile,
            )
            imported += 1

        # Reset watermark in config.json
        config["last_reflection_event_id"] = 0
        config.setdefault("initial_import_done", {})[req.profile] = True
        config_path.write_text(json.dumps(config, indent=2))

        return {"status": "ok", "imported": imported, "limit": limit}
    except Exception as e:
        logger.error("Import failed: %s", e)
        return {"status": "error", "message": str(e)}


def run_server(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_config=None)
