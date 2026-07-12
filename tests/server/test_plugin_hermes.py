"""Tests for LedgerMind Hermes plugin."""
import sys
import os
import json
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture
def plugin_dir(tmp_path):
    """Create a plugin directory with config."""
    plugin = tmp_path / "plugin"
    plugin.mkdir()

    config = {
        "default_mode": "agent",
        "enrichment": {
            "provider": "openrouter",
            "model": "meta-llama/llama-3-8b-instruct:free",
            "api_key": "test-key",
            "base_url": "https://openrouter.ai/api/v1",
        },
        "initial_import_done": {},
    }
    (plugin / "config.json").write_text(json.dumps(config))

    return plugin


@pytest.fixture
def state_db(tmp_path):
    """Create a fake Hermes state.db."""
    db_path = tmp_path / "state.db"
    conn = sqlite3.connect(str(db_path))

    conn.execute("""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT,
            model TEXT,
            title TEXT,
            started_at REAL,
            ended_at REAL,
            message_count INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            tool_calls TEXT,
            tool_name TEXT,
            timestamp REAL
        )
    """)

    # Insert test data
    conn.execute(
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("test_session_1", "cli", "test-model", "Test Session", 1000, 2000, 4, 1000, 500),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        ("test_session_1", "user", "Hello, how are you?", 1001),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        ("test_session_1", "assistant", "I'm doing well, thanks!", 1002),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        ("test_session_1", "user", "What is Python?", 1003),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        ("test_session_1", "assistant", "Python is a programming language.", 1004),
    )

    conn.commit()
    conn.close()

    return db_path


class TestExtractKeywords:
    def test_extract_keywords(self):
        """Test keyword extraction."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "ledgermind_plugin"))
        from __init__ import _extract_keywords

        keywords = _extract_keywords("What is the best database for Python?")
        assert "database" in keywords
        assert "python" in keywords
        assert "best" in keywords
        assert "what" not in keywords  # stop word
        assert "the" not in keywords  # stop word
        assert "is" not in keywords   # stop word


class TestRegister:
    def test_register_hooks(self):
        """Test that register() registers all hooks."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "ledgermind_plugin"))
        from __init__ import register

        mock_ctx = MagicMock()
        register(mock_ctx)

        # Check that hooks were registered
        hook_calls = [call[0][0] for call in mock_ctx.register_hook.call_args_list]
        assert "pre_llm_call" in hook_calls
        assert "post_llm_call" in hook_calls
        assert "on_session_start" in hook_calls
