from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ledgermind_integrations.adapters.hermes.config import HermesConfig
from ledgermind_integrations.adapters.hermes.hooks import HermesRoundCapture, PendingCaptureWorker
from ledgermind_integrations.adapters.hermes.round_capture import build_raw_round
from ledgermind_integrations.adapters.hermes.state_db import HermesStateReader
from ledgermind_integrations.runtime.spool import FileSpool


def _config(tmp_path: Path) -> HermesConfig:
    return HermesConfig(
        endpoint="http://127.0.0.1:8765",
        token_file=str(tmp_path / "token"),
        memory_space_id="workspace_01",
        source_instance_id="src_hermes_local",
        profile_id="default",
        state_db_path=str(tmp_path / "state.db"),
        spool_dir=str(tmp_path / "spool"),
    )


def _events(final: bool = True) -> list[dict[str, object]]:
    return [
        {
            "event_id": "1001",
            "kind": "message",
            "role": "user",
            "content": "Use the repository conventions.",
        },
        {
            "event_id": "1002",
            "kind": "tool_call",
            "tool_call_id": "call_1",
            "tool_name": "read_file",
            "arguments": {"path": "README.md"},
        },
        {
            "event_id": "1003",
            "kind": "message",
            "role": "assistant",
            "final": final,
            "content": "The conventions are applied.",
        },
    ]


def test_hermes_capture_matches_reference_digest() -> None:
    payload = build_raw_round(
        memory_space_id="workspace_01",
        source_system="hermes",
        source_instance_id="src_hermes_local",
        profile_id="default",
        session_id="session_01",
        round_id="1001:1003",
        started_at="2026-08-02T20:00:00Z",
        completed_at="2026-08-02T20:01:05Z",
        events=_events(),
        resolution={"project_id": "aliadoai", "repository_id": "aliadoai-next"},
    )
    fixture = json.loads(
        (Path(__file__).resolve().parents[3] / "protocol/conformance/valid/hermes_complete.json").read_text()
    )
    assert payload["payload_digest"] == fixture["payload_digest"]
    assert {"title", "statement", "rationale"}.isdisjoint(payload)


def test_capture_waits_for_final_event_then_promotes(tmp_path: Path) -> None:
    capture = HermesRoundCapture(_config(tmp_path), FileSpool(tmp_path / "spool"))
    pending = capture.capture_or_defer(
        session_id="session_01",
        round_id="round-1",
        started_at="2026-08-02T20:00:00Z",
        completed_at="2026-08-02T20:01:05Z",
        events=_events(False),
    )
    assert pending.parent.name == "pending-capture"
    worker = PendingCaptureWorker(capture)
    assert worker.run_once(lambda _: _events(True)) == 1
    assert capture.spool.stats().pending_capture == 0
    assert capture.spool.stats().ready_delivery == 1


def test_state_reader_recovers_only_requested_round_and_structured_tools(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_call_id TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL NOT NULL,
            api_content TEXT
        );
        """
    )
    rows = [
        (1, "s1", "user", "first", None, None, None, 10.0),
        (2, "s1", "assistant", "first answer", None, None, None, 11.0),
        (3, "s1", "user", "middle", None, None, None, 20.0),
        (
            4,
            "s1",
            "assistant",
            "",
            None,
            json.dumps(
                [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":"README.md"}'},
                    }
                ]
            ),
            None,
            21.0,
        ),
        (5, "s1", "tool", "contents", "call-1", None, "read_file", 22.0),
        (6, "s1", "assistant", "middle answer", None, None, None, 23.0),
        (7, "s1", "user", "last", None, None, None, 30.0),
        (8, "s1", "assistant", "last answer", None, None, None, 31.0),
    ]
    connection.executemany(
        "INSERT INTO messages "
        "(id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    connection.commit()
    connection.close()

    events = HermesStateReader(db_path).round_events(
        "s1", first_message_id=3, last_message_id=6
    )

    assert [event["kind"] for event in events] == [
        "message",
        "tool_call",
        "tool_result",
        "message",
    ]
    assert [event.get("role") for event in events] == ["user", None, None, "assistant"]
    assert events[1]["tool_call_id"] == "call-1"
    assert events[1]["tool_name"] == "read_file"
    assert events[1]["arguments"] == {"path": "README.md"}
    assert events[2]["tool_call_id"] == "call-1"
    assert events[-1]["final"] is True
    assert [event["event_id"] for event in events] == ["3", "4:tool_call:0", "5", "6"]


def test_state_reader_time_range_trims_previous_and_later_rounds(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
        "content TEXT, timestamp REAL)"
    )
    connection.executemany(
        "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "s1", "user", "first", 10.0),
            (2, "s1", "assistant", "first answer", 11.0),
            (3, "s1", "user", "middle", 20.0),
            (4, "s1", "assistant", "middle answer", 21.0),
            (5, "s1", "user", "last", 30.0),
            (6, "s1", "assistant", "last answer", 31.0),
        ],
    )
    connection.commit()
    connection.close()

    events = HermesStateReader(db_path).round_events(
        "s1", started_at="1970-01-01T00:00:19Z", completed_at="1970-01-01T00:00:22Z"
    )

    assert [event["content"] for event in events] == ["middle", "middle answer"]
    assert events[-1]["final"] is True


def test_state_reader_combines_partial_id_and_time_boundaries(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
        "content TEXT, timestamp REAL)"
    )
    connection.executemany(
        "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        [
            (1, "s1", "user", "first", 10.0),
            (2, "s1", "assistant", "first answer", 11.0),
            (3, "s1", "user", "middle", 20.0),
            (4, "s1", "assistant", "middle answer", 21.0),
            (5, "s1", "user", "last", 30.0),
            (6, "s1", "assistant", "last answer", 31.0),
        ],
    )
    connection.commit()
    connection.close()

    events = HermesStateReader(db_path).round_events(
        "s1",
        first_message_id=3,
        completed_at="1970-01-01T00:00:29Z",
    )

    assert [event["content"] for event in events] == ["middle", "middle answer"]
    assert events[-1]["final"] is True


def test_state_reader_links_tool_result_when_legacy_call_has_no_id(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
        "content TEXT, tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, timestamp REAL)"
    )
    connection.executemany(
        "INSERT INTO messages "
        "(id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "s1", "user", "run it", None, None, None, 10.0),
            (
                2,
                "s1",
                "assistant",
                "",
                None,
                json.dumps({"function": {"name": "read_file", "arguments": "{}"}}),
                None,
                11.0,
            ),
            (3, "s1", "tool", "done", "call-legacy", None, "read_file", 12.0),
            (4, "s1", "assistant", "finished", None, None, None, 13.0),
        ],
    )
    connection.commit()
    connection.close()

    events = HermesStateReader(db_path).round_events("s1", first_message_id=1, last_message_id=4)

    assert [event["kind"] for event in events] == [
        "message",
        "tool_call",
        "tool_result",
        "message",
    ]
    assert events[1]["tool_call_id"] == "call-legacy"
    assert events[2]["tool_call_id"] == "call-legacy"
    assert events[-1]["final"] is True


def test_state_reader_does_not_mark_tool_call_narration_as_final(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, "
        "content TEXT, tool_calls TEXT, timestamp REAL)"
    )
    connection.executemany(
        "INSERT INTO messages (id, session_id, role, content, tool_calls, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "s1", "user", "run it", None, 10.0),
            (
                2,
                "s1",
                "assistant",
                "I will check that.",
                json.dumps({"id": "call-1", "function": {"name": "read_file"}}),
                11.0,
            ),
        ],
    )
    connection.commit()
    connection.close()

    events = HermesStateReader(db_path).round_events("s1", first_message_id=1, last_message_id=2)

    assert [event["kind"] for event in events] == ["message", "message", "tool_call"]
    assert not any(event.get("final") for event in events)

def test_load_config_reads_failed_promotion_limits(tmp_path: Path) -> None:
    from ledgermind_integrations.adapters.hermes.config import load_config
    from ledgermind_integrations.runtime.spool import (
        DEFAULT_RETRYABLE_FAILED_MAX_AGE_SECONDS,
        DEFAULT_RETRYABLE_FAILED_MAX_ATTEMPTS,
    )

    path = tmp_path / "hermes.json"
    payload: dict[str, object] = {
        "endpoint": "http://127.0.0.1:8765",
        "memory_space_id": "workspace_01",
        "source_instance_id": "src_hermes_local",
        "profile_id": "default",
        "retryable_failed_max_attempts": 7,
        "retryable_failed_max_age_seconds": 60,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    config = load_config(path)
    assert config.retryable_failed_max_attempts == 7
    assert config.retryable_failed_max_age_seconds == 60.0

    del payload["retryable_failed_max_attempts"]
    del payload["retryable_failed_max_age_seconds"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    defaults = load_config(path)
    assert defaults.retryable_failed_max_attempts == DEFAULT_RETRYABLE_FAILED_MAX_ATTEMPTS
    assert (
        defaults.retryable_failed_max_age_seconds
        == DEFAULT_RETRYABLE_FAILED_MAX_AGE_SECONDS
    )


def test_load_config_reads_pending_capture_backoff(tmp_path: Path) -> None:
    import pytest

    from ledgermind_integrations.adapters.hermes.config import load_config
    from ledgermind_integrations.runtime.defaults import (
        DEFAULT_PENDING_CAPTURE_BACKOFF_SECONDS,
    )

    path = tmp_path / "hermes-backoff.json"
    payload: dict[str, object] = {
        "endpoint": "http://127.0.0.1:8765",
        "memory_space_id": "workspace_01",
        "source_instance_id": "src_hermes_local",
        "profile_id": "default",
        "pending_capture_backoff_seconds": [0.5, 2],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_config(path).pending_capture_backoff_seconds == (0.5, 2.0)

    del payload["pending_capture_backoff_seconds"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert (
        load_config(path).pending_capture_backoff_seconds
        == DEFAULT_PENDING_CAPTURE_BACKOFF_SECONDS
    )

    for invalid in ([], [-1], ["x"]):
        payload["pending_capture_backoff_seconds"] = invalid
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="pending_capture_backoff_seconds"):
            load_config(path)


def test_load_config_accepts_cloud_spool_aliases(tmp_path: Path) -> None:
    from ledgermind_integrations.adapters.hermes.config import load_config

    path = tmp_path / "hermes-cloud-aliases.json"
    path.write_text(
        json.dumps(
            {
                "endpoint": "https://api.ledgermind.org",
                "memory_space_id": "default",
                "source_instance_id": "hermes-cloud-1",
                "profile_id": "generation-operational",
                "runtime_command": "/opt/venv/bin/ledgermind-cloud",
                "spool_max_bytes": 123_456,
                "spool_max_files": 42,
                "max_round_payload_bytes": 65_432,
            }
        ),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.max_spool_bytes == 123_456
    assert config.max_spool_files == 42
    assert config.max_raw_round_bytes == 65_432
