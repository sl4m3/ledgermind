from __future__ import annotations

from dataclasses import replace

from ledgermind_integrations.adapters.lifecycle.config import LifecycleConfig
from ledgermind_integrations.adapters.lifecycle.visibility import (
    MAX_AGE_TOKENS,
    advance_epoch,
    assume_hook_returned,
    note_content,
    visible_ids,
)


def _config(tmp_path, target="codex", space="space"):
    return LifecycleConfig(
        target=target, endpoint="http://127.0.0.1:3001", token_file="",
        memory_space_id=space, source_instance_id="instance", profile_id="profile",
        spool_dir=str(tmp_path), runtime_command="/bin/true",
    )


def test_visibility_survives_restart_and_is_scoped(tmp_path) -> None:
    config = _config(tmp_path)
    assume_hook_returned(config, "session", "request-1", ["value-1"])
    assert visible_ids(_config(tmp_path), "session") == ["value-1"]
    assert visible_ids(replace(config, memory_space_id="other"), "session") == []
    assert visible_ids(replace(config, target="claude-code"), "session") == []
    assert visible_ids(config, "other-session") == []
    assert visible_ids(replace(config, endpoint="https://api.example.test"), "session") == []
    assume_hook_returned(config, "session", "request-1", ["value-1"])
    assert visible_ids(config, "session") == ["value-1"]


def test_unique_content_age_and_compaction(tmp_path) -> None:
    config = _config(tmp_path)
    assume_hook_returned(config, "session", "request", ["value"])
    note_content(config, "session", "event", "x" * (MAX_AGE_TOKENS * 4 - 4))
    note_content(config, "session", "event", "x" * 100)
    assert visible_ids(config, "session") == ["value"]
    note_content(config, "session", "next", "xxxx")
    assert visible_ids(config, "session") == []
    assume_hook_returned(config, "session", "new-request", ["value"])
    advance_epoch(config, "session")
    assert visible_ids(config, "session") == []
