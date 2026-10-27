from __future__ import annotations

import json
from pathlib import Path

from ledgermind_integrations.runtime.endpoint import resolve_runtime_endpoint


def test_runtime_endpoint_uses_last_supervisor_choice(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps(
            {
                "running": False,
                "endpoint": None,
                "preferred_endpoint": "http://127.0.0.1:8767",
            }
        ),
        encoding="utf-8",
    )
    assert resolve_runtime_endpoint("http://127.0.0.1:8765", str(state)) == (
        "http://127.0.0.1:8767"
    )


def test_runtime_endpoint_rejects_remote_state_value(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps({"preferred_endpoint": "https://example.org:443"}),
        encoding="utf-8",
    )
    assert resolve_runtime_endpoint("http://127.0.0.1:8765", str(state)) == (
        "http://127.0.0.1:8765"
    )


def test_custom_local_endpoint_is_not_overridden_by_implicit_state(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    state = tmp_path / "ledgermind" / "runtime" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text(
        json.dumps({"preferred_endpoint": "http://127.0.0.1:8767"}),
        encoding="utf-8",
    )
    assert resolve_runtime_endpoint("http://127.0.0.1:12345") == (
        "http://127.0.0.1:12345"
    )
