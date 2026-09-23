from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ledgermind_integrations.adapters.hermes.config import HermesConfig
from ledgermind_integrations.adapters.hermes.hooks import HermesRoundCapture
from ledgermind_integrations.adapters.hermes.runtime import HermesPluginRuntime
from ledgermind_integrations.adapters.hermes.state_db import HermesStateReader
from ledgermind_integrations.runtime.spool import FileSpool


def _events() -> list[dict[str, Any]]:
    return [
        {"event_id": "user", "kind": "message", "role": "user", "content": "hello"},
        {
            "event_id": "assistant",
            "kind": "message",
            "role": "assistant",
            "content": "done",
            "final": True,
        },
    ]


def test_capture_adds_canonical_resolution_without_round_task(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    nested = repository / "src"
    nested.mkdir(parents=True)
    (repository / ".git").mkdir()
    config = HermesConfig(
        endpoint="http://127.0.0.1:8765",
        token_file=str(tmp_path / "token"),
        memory_space_id="space-1",
        source_instance_id="instance-1",
        profile_id="default",
        state_db_path=str(tmp_path / "state.db"),
        spool_dir=str(tmp_path / "spool"),
        working_directory=str(nested),
    )
    spool = FileSpool(tmp_path / "spool")
    capture = HermesRoundCapture(config, spool)

    capture.capture_or_defer(
        session_id="session-real",
        round_id="round-derived-id",
        started_at="2026-08-10T10:00:00Z",
        completed_at="2026-08-10T10:00:01Z",
        events=_events(),
    )

    envelope = json.loads(next(spool.ready_dir.glob("*.json")).read_text(encoding="utf-8"))
    resolution = envelope["request"]["source"]["extensions"]["ledgermind_resolution"]
    assert resolution["conversation_id"] == "session-real"
    assert resolution["repository_id"] == repository.resolve().as_posix()
    assert resolution["project_id"] is None
    assert resolution["task_id"] is None


def test_state_reader_replay_uses_metadata_and_session_fallback(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    nested = repository / "src"
    nested.mkdir(parents=True)
    (repository / ".git").mkdir()
    state_db = tmp_path / "state.db"
    connection = sqlite3.connect(state_db)
    connection.execute(
        "CREATE TABLE messages ("
        "id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, "
        "working_directory TEXT, timestamp REAL)"
    )
    connection.execute(
        "INSERT INTO messages "
        "(id, session_id, role, content, working_directory, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "session-real", "user", "hello", str(nested), 10.0),
    )
    connection.commit()
    connection.close()

    resolution = HermesStateReader(state_db).resolution_extension(
        "session-real",
        first_message_id=1,
        last_message_id=1,
    )

    assert resolution["conversation_id"] == "session-real"
    assert resolution["repository_id"] == repository.resolve().as_posix()
    assert resolution["task_id"] is None


def test_runtime_keeps_explicit_task_and_never_uses_round_id(tmp_path: Path) -> None:
    class Client:
        def retrieve_context(self, **_: Any) -> None:
            return None

    config = HermesConfig(
        endpoint="http://127.0.0.1:8765",
        token_file=str(tmp_path / "token"),
        memory_space_id="space-1",
        source_instance_id="instance-1",
        profile_id="default",
        state_db_path=str(tmp_path / "state.db"),
        spool_dir=str(tmp_path / "spool"),
    )
    spool = FileSpool(tmp_path / "spool")
    runtime = HermesPluginRuntime(config=config, client=Client(), spool=spool)  # type: ignore[arg-type]
    try:
        runtime.on_pre_llm_call(
            session_id="session-real",
            turn_id="round-derived-id",
            task_id="task-real",
            user_message="hello",
        )
        runtime.on_post_llm_call(
            session_id="session-real",
            turn_id="round-derived-id",
            task_id="task-real",
            user_message="hello",
            assistant_response="done",
        )
        envelope = json.loads(next(spool.ready_dir.glob("*.json")).read_text(encoding="utf-8"))
        resolution = envelope["request"]["source"]["extensions"]["ledgermind_resolution"]
        assert resolution["conversation_id"] == "session-real"
        assert resolution["task_id"] == "task-real"
    finally:
        runtime.shutdown()
