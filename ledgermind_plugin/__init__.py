"""
LedgerMind Plugin for Hermes Agent

HTTP bridge to LedgerMind server. No direct imports — just HTTP calls.
"""

import atexit
import os
import json
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ledgermind.plugin")

CONFIG_DIR = Path.home() / ".ledgermind" / "hermes"
PLUGIN_DIR = Path(__file__).parent
DEFAULT_PORT = 8000
SERVER_URL = f"http://127.0.0.1:{DEFAULT_PORT}"


def _load_config() -> Dict[str, Any]:
    config_path = CONFIG_DIR / "config.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {}


def _get_profile_name() -> str:
    try:
        hermes_cli = __import__("hermes_cli", fromlist=["plugins"])
        return getattr(hermes_cli.plugins, "current_profile", None) or "default"
    except Exception:
        return "default"


def _api(method: str, path: str, data: dict = None) -> Optional[dict]:
    import urllib.request
    import urllib.error

    url = f"{SERVER_URL}{path}"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode() if data else None,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError:
        return None
    except Exception as e:
        logger.debug("API error: %s", e)
        return None


_server_process = None


def _kill_server():
    global _server_process
    if _server_process is not None and _server_process.poll() is None:
        try:
            _server_process.terminate()
            _server_process.wait(timeout=5)
        except Exception:
            _server_process.kill()
        logger.info("LedgerMind server stopped")


def _ensure_server_running():
    global _server_process

    resp = _api("GET", "/health")
    if resp:
        return

    venv_python = Path.home() / ".ledgermind" / "venv" / "bin" / "python3"
    if not venv_python.exists():
        venv_python = Path(sys.executable)

    try:
        log_file = Path.home() / ".ledgermind" / "server.log"
        _server_process = subprocess.Popen(
            [str(venv_python), "-m", "ledgermind.server.cli", "serve",
             "--port", str(DEFAULT_PORT)],
            stdout=log_file.open("a"),
            stderr=subprocess.STDOUT,
        )

        atexit.register(_kill_server)

        def _signal_handler(signum, frame):
            _kill_server()
            sys.exit(0)

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        for _ in range(10):
            time.sleep(0.5)
            if _api("GET", "/health"):
                logger.info("LedgerMind server started on port %d", DEFAULT_PORT)
                return
        logger.warning("LedgerMind server failed to start")
    except Exception as e:
        logger.error("Failed to start LedgerMind server: %s", e)


def _on_pre_llm_call(
    session_id: str,
    user_message: str,
    conversation_history: list,
    is_first_turn: bool,
    model: str,
    platform: str,
    **kwargs,
):
    if not user_message:
        return None

    profile = _get_profile_name()
    resp = _api("POST", "/memory/search", {
        "query": user_message,
        "limit": 5,
        "profile": profile,
    })
    if not resp or not resp.get("results"):
        return None

    lines = ["[LEDGERMIND KNOWLEDGE BASE ACTIVE]"]
    for m in resp["results"]:
        lines.append(
            f"- {m.get('title', '')} ({m.get('target', '')}): "
            f"{m.get('rationale', '')} [score: {m.get('score', 0)}]"
        )
    return {"context": "\n".join(lines)}


def _on_post_llm_call(
    session_id: str,
    user_message: str,
    assistant_response: str,
    conversation_history: list,
    model: str,
    platform: str,
    **kwargs,
):
    if not assistant_response:
        return

    profile = _get_profile_name()

    _api("POST", "/memory/write", {
        "source": "user",
        "kind": "prompt",
        "content": user_message,
        "context": {"session_id": session_id},
        "profile": profile,
    })

    _api("POST", "/memory/write", {
        "source": "agent",
        "kind": "result",
        "content": assistant_response,
        "context": {"session_id": session_id, "model": model},
        "profile": profile,
    })


def _on_session_start(session_id: str, model: str, platform: str, **kwargs):
    try:
        config = _load_config()
        profile_name = _get_profile_name()
        done = config.get("initial_import_done", {})
        if done.get(profile_name):
            return

        state_db = Path.home() / ".hermes" / "state.db"
        if not state_db.exists():
            return

        logger.info("Importing state.db for profile: %s", profile_name)
        _api("POST", "/import/state-db", {"profile": profile_name})
    except Exception as e:
        logger.error("on_session_start error: %s", e)


def register(ctx):
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("post_llm_call", _on_post_llm_call)
    ctx.register_hook("on_session_start", _on_session_start)

    _ensure_server_running()
    _api("POST", "/worker/start")

    try:
        config = _load_config()
        profile_name = _get_profile_name()
        done = config.get("initial_import_done", {})
        if not done.get(profile_name):
            state_db = Path.home() / ".hermes" / "state.db"
            if state_db.exists():
                logger.info("Importing state.db for profile: %s", profile_name)
                _api("POST", "/import/state-db", {"profile": profile_name})
    except Exception as e:
        logger.error("Import error: %s", e)
